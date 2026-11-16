"""전사 작업과 모델 준비의 실제 파일 잠금 경계를 검사한다."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from archive import model_paths, speaker_tools, speech_model, speech_vad
from archive.jobs import Manager
from archive.source import Cancelled
from archive.storage import ProjectLock, ResourceBusy


class SpeechModelLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.cache = self.root / 'models'
        self.cache.mkdir()
        self.manager = Manager.__new__(Manager)
        self.payload = b'model fixture'
        self.stop = threading.Event()
        for item in (patch.object(model_paths, 'root', return_value=self.cache),
                     patch.object(speaker_tools, 'status', return_value={'ready': True}),
                     patch.object(speech_model, 'SIZE', len(self.payload)),
                     patch.object(speech_model, 'SHA256', hashlib.sha256(self.payload).hexdigest()),
                     patch.object(speech_vad, 'SIZE', len(self.payload)),
                     patch.object(speech_vad, 'SHA256', hashlib.sha256(self.payload).hexdigest()),
                     patch.object(speech_model, 'urlopen', side_effect=AssertionError('모델 재다운로드')),
                     patch.object(speech_vad, 'urlopen', side_effect=AssertionError('발화 모델 재다운로드'))):
            item.start()
            self.addCleanup(item.stop)

    def test_cached_vad_under_transcription_lock(self):
        target = self.cache / 'silero-vad.onnx'
        target.write_bytes(self.payload)
        with self.manager.work_lock(self.root / 'vod-1', 'speech', 'transcribe'):
            self.assertEqual(speech_vad.prepare(self.stop, lambda **_: None), target)
        self.assertEqual(target.read_bytes(), self.payload)

    def test_cached_model_under_model_job_lock(self):
        speech_model.model_path().write_bytes(self.payload)
        with self.manager.work_lock(self.root / 'vod-1', 'speech', 'model'):
            speech_model.prepare(self.stop, lambda **_: None)
        self.assertTrue(speech_model.status()['ready'])
        self.assertEqual(speech_model.model_path().read_bytes(), self.payload)

    def test_two_transcriptions_share_one_vad_download(self):
        downloading, release, waiting = (threading.Event() for _ in range(3))

        def download(*args, **kwargs):
            downloading.set()
            if not release.wait(5):
                raise AssertionError('다운로드 해제 시간 초과')
            return io.BytesIO(self.payload)

        with self.manager.work_lock(self.root / 'vod-1', 'speech', 'transcribe'), \
                self.manager.work_lock(self.root / 'vod-2', 'speech', 'transcribe'), \
                patch.object(speech_vad, 'urlopen', side_effect=download) as fetch, \
                ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(speech_vad.prepare, self.stop, lambda **_: None)
            try:
                self.assertTrue(downloading.wait(3))
                second = pool.submit(speech_vad.prepare, self.stop, lambda **_: waiting.set())
                self.assertTrue(waiting.wait(3))
                self.assertFalse(second.done())
            finally:
                release.set()
            self.assertEqual(first.result(3), second.result(3))
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual((self.cache / 'silero-vad.onnx').read_bytes(), self.payload)

    def test_model_preparation_waits_for_inference_and_can_cancel(self):
        target = speech_model.model_path()
        target.write_bytes(self.payload)
        waiting = threading.Event()
        with self.manager.work_lock(self.root / 'vod-1', 'speech', 'transcribe'), \
                self.manager.work_lock(self.root / 'vod-2', 'speech', 'model'), \
                ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(speech_model.prepare, self.stop, lambda **_: waiting.set())
            try:
                self.assertTrue(waiting.wait(3))
                self.assertFalse(future.done())
                self.assertFalse((self.cache / 'verified.json').exists())
            finally:
                self.stop.set()
            with self.assertRaises(Cancelled):
                future.result(3)
        self.assertEqual(target.read_bytes(), self.payload)
        with self.manager.work_lock(self.root / 'vod-2', 'speech', 'model'):
            speech_model.prepare(threading.Event(), lambda **_: None)
        self.assertTrue(speech_model.status()['ready'])

    def test_waiting_vad_cancel_preserves_cached_files_and_releases_locks(self):
        target = self.cache / 'silero-vad.onnx'
        target.write_bytes(self.payload)
        with ProjectLock(self.cache, write=['speech-vad']):
            with self.manager.work_lock(self.root / 'vod-1', 'speech', 'transcribe'):
                with self.assertRaises(Cancelled):
                    speech_vad.prepare(self.stop, lambda **_: self.stop.set())
        self.assertEqual(target.read_bytes(), self.payload)
        with ProjectLock(self.cache):
            pass

    def test_voice_and_context_model_preparation_with_other_transcription(self):
        with self.manager.work_lock(self.root / 'vod-1', 'voices', 'prepare'), ProjectLock(self.cache / 'voices'), \
                self.manager.work_lock(self.root / 'vod-2', 'context', 'model'), ProjectLock(self.cache / 'context'), \
                self.manager.work_lock(self.root / 'vod-3', 'speech', 'transcribe'):
            with self.assertRaises(ResourceBusy):
                self.manager.work_lock(self.root / 'vod-4', 'context', 'full')
            with self.manager.work_lock(self.root / 'vod-1', 'speech', 'transcribe'):
                with self.assertRaises(ResourceBusy):
                    self.manager.work_lock(self.root / 'vod-1', 'speech', 'audio')
            with self.assertRaises(ResourceBusy):
                self.manager.work_lock(self.root / 'vod-4', 'voices', 'diarize')

    def test_retranscription_shares_transcription_limit_and_model(self):
        with self.manager.work_lock(self.root / 'vod-1', 'voices', 'retranscribe-original'), \
                self.manager.work_lock(self.root / 'vod-2', 'speech', 'transcribe'), \
                self.manager.work_lock(self.root / 'vod-3', 'speech', 'transcribe'):
            with self.assertRaises(ResourceBusy):
                self.manager.work_lock(self.root / 'vod-4', 'speech', 'transcribe')
            with self.assertRaises(ResourceBusy):
                ProjectLock(self.cache, write=['speech-models'])
        with self.manager.work_lock(self.root / 'vod-1', 'voices', 'suggest'):
            with self.assertRaises(ResourceBusy):
                self.manager.work_lock(self.root / 'vod-2', 'context', 'full')

    def test_other_model_families_do_not_block_and_corrupt_vad_is_preserved(self):
        target = self.cache / 'silero-vad.onnx'
        target.write_bytes(b'invalid model')
        with ProjectLock(self.cache, write=['voices-models']), \
                self.manager.work_lock(self.root / 'vod-1', 'speech', 'transcribe'):
            with self.assertRaisesRegex(ValueError, '손상'):
                speech_vad.prepare(self.stop, lambda **_: None)
            with self.assertRaises(ResourceBusy):
                ProjectLock(self.cache)
        self.assertEqual(target.read_bytes(), b'invalid model')
