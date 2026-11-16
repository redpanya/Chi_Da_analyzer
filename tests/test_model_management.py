import hashlib
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from archive import context_model, diarization_backends, model_management, runtime, speaker_tools, speech_model, speech_vad
from archive.jobs import Manager
from archive.storage import Conflict, ProjectLock, save_json


class ModelManagementTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base/'models'
        self.root.mkdir()
        self.enterContext(patch.object(runtime, 'MODEL_ROOT', self.root))
        self.manager = Manager(self.base/'vods')
        self.library = self.manager.model_library
        self.addCleanup(self.manager.close)

    def act(self, key, action, root=None):
        return self.library.request({'root': str(root or self.root), 'id': key, 'action': action})

    def finish(self):
        self.library.thread.join(4)
        self.assertFalse(self.library.thread.is_alive())
        return self.library.request({})['job']

    def row(self, key):
        return next(row for row in self.library.request({})['items'] if row['id'] == key)

    def test_vad_install_progress_resume_delete_and_no_vod(self):
        data = b'silero' * 500
        started, release = threading.Event(), threading.Event()
        def fetch(*args, **kwargs):
            started.set()
            if not release.wait(3):
                raise TimeoutError()
            return io.BytesIO(data)
        self.enterContext(patch.object(speech_vad, 'SIZE', len(data)))
        self.enterContext(patch.object(speech_vad, 'SHA256', hashlib.sha256(data).hexdigest()))
        self.enterContext(patch.object(speech_vad, 'urlopen', side_effect=fetch))
        self.assertFalse(self.row('vad')['present'])
        self.act('vad', 'install')
        try:
            self.assertTrue(started.wait(2))
            with self.assertRaises(Conflict):
                self.manager.model_folder(str(self.base/'other'))
            with self.assertRaises(Conflict):
                self.act('gemma', 'install')
        finally:
            release.set()
        self.assertEqual(self.finish()['state'], 'complete')
        installed = self.row('vad')
        self.assertTrue(installed['ready'])
        self.assertEqual(installed['bytes'], len(data))
        self.assertEqual(installed['expected_bytes'], len(data))
        self.act('vad', 'delete')
        self.assertEqual(self.finish()['state'], 'complete')
        self.assertFalse(self.row('vad')['present'])
        self.assertFalse((self.base/'vods').exists())

    def test_cancel_preserves_partial_and_releases_locks(self):
        entered = threading.Event()
        def downloading(stop, update):
            (self.root/'silero-vad.download').write_bytes(b'x')
            update(message='수신 중', progress={'bytes': 1, 'total_bytes': 2})
            entered.set()
            stop.wait(3)
            model_management.source.check_cancel(stop)
        with patch.object(speech_vad, 'prepare', side_effect=downloading):
            self.act('vad', 'install')
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.library.request({})['job']['progress']['bytes'], 1)
            self.act('vad', 'cancel')
            self.assertEqual(self.finish()['state'], 'stopped')
        self.assertTrue(self.row('vad')['can_delete'])
        with ProjectLock(self.root, write=['model-vad']):
            pass

    def test_model_in_use_and_unrelated_operations(self):
        target = speech_model.model_path().with_suffix('.part')
        target.write_bytes(b'x')
        (self.root/'silero-vad.download').write_bytes(b'y')
        with self.manager.work_lock(self.base/'vod-2', 'speech', 'transcribe', {'vad':'off'}):
            with self.assertRaisesRegex(Conflict, '사용하는 작업'):
                self.act('whisper', 'delete')
            self.act('vad', 'delete')
            self.assertEqual(self.finish()['state'], 'complete')
        with self.manager.work_lock(self.base/'vod-3', 'voices', 'diarize', {'backend':'fluid'}):
            self.act('whisper', 'delete')
            self.assertEqual(self.finish()['state'], 'complete')

    def test_only_selected_owned_files_removable(self):
        original = self.base/'vods/vod-11/video.mp4'
        original.parent.mkdir(parents=True)
        original.write_bytes(b'video')
        marker = self.root/'verified.json'
        save_json(marker, {'other': 'user-file'})
        target = speech_model.model_path().with_suffix('.part')
        broken = target.with_name(target.name + '.invalid-127')
        unrelated = target.with_name(target.name + '.invalid-user')
        for file in (target, broken, unrelated):
            file.write_bytes(b'test')
        self.assertEqual(self.row('whisper')['bytes'], 8)
        self.act('whisper', 'delete')
        self.assertEqual(self.finish()['state'], 'complete')
        self.assertFalse(target.exists())
        self.assertFalse(broken.exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(marker.exists())
        self.assertEqual(original.read_bytes(), b'video')

    def test_symlink_stale_folder_legacy_and_platform_specific_removal(self):
        context_model.home().mkdir()
        legacy = context_model.model_path(context_model.NAME)
        legacy.write_bytes(b'old')
        key = 'legacy-' + context_model.NAME.lower()
        self.assertFalse(self.row(key)['can_install'])
        with self.assertRaises(Conflict):
            self.act(key, 'delete', self.base/'other')
        (self.root/'silero-vad.onnx').symlink_to(legacy)
        with self.assertRaisesRegex(Conflict, '연결'):
            self.act('vad', 'delete')
        self.assertEqual(legacy.read_bytes(), b'old')
        self.act(key, 'delete')
        self.assertEqual(self.finish()['state'], 'complete')
        self.assertTrue((self.root/'silero-vad.onnx').is_symlink())
        self.assertNotIn(key, [row['id'] for row in self.library.request({})['items']])

    def test_gated_partial_cleanup_preserves_unrelated_revision_files(self):
        backend = 'pyannote'
        folder = diarization_backends.home(backend)
        files = model_management.model_files(self.root, backend)
        partial = next(file for file in files if file.name.endswith('.incomplete'))
        partial.parent.mkdir(parents=True)
        partial.write_bytes(b'part')
        note = folder/'notes.txt'
        note.write_bytes(b'my file')
        self.assertEqual(self.row(backend)['bytes'], 4)
        self.act(backend, 'delete')
        self.assertEqual(self.finish()['state'], 'complete')
        self.assertFalse(partial.exists())
        self.assertTrue(note.exists())

    def test_context_download_lock_and_legacy_model_isolation(self):
        gemma = context_model.model_path().with_suffix('.part')
        gemma.parent.mkdir()
        gemma.write_bytes(b'part')
        qwen = context_model.model_path(context_model.NAME)
        qwen.write_bytes(b'qwen')
        resource = model_management.context_resource(context_model.DEFAULT_NAME)
        with ProjectLock(self.root, read=[resource]):
            with self.assertRaises(Conflict):
                self.act('gemma', 'delete')
            self.act('legacy-' + context_model.NAME.lower(), 'delete')
            self.assertEqual(self.finish()['state'], 'complete')
        self.assertTrue(gemma.exists())
        self.assertFalse(qwen.exists())

    def test_catalog_model_locks_are_valid_and_distinct(self):
        keys = model_management.LABELS.keys() | model_management.CONTEXT.keys()
        resources = [model_management.model_resource(key) for key in keys]
        self.assertEqual(len(set(resources)), len(keys))
        with ProjectLock(self.root, read=resources):
            for key, name in model_management.CONTEXT.items():
                self.assertEqual(model_management.context_resource(name), model_management.model_resource(key))

    def test_qwen35_delete_uses_the_same_lock_as_inference(self):
        small = 'Qwen3.5-4B-Q4_K_M'
        large = 'Qwen3.5-9B-Q4_K_M'
        small_key = 'legacy-' + small.lower()
        large_key = 'legacy-' + large.lower()
        context_model.home().mkdir()
        small_file = context_model.model_path(small)
        large_file = context_model.model_path(large)
        small_file.write_bytes(b'4B')
        large_file.write_bytes(b'9B')
        with ProjectLock(self.root, read=[model_management.context_resource(small)]):
            with self.assertRaisesRegex(Conflict, '사용하는 작업'):
                self.act(small_key, 'delete')
            self.act(large_key, 'delete')
            self.assertEqual(self.finish()['state'], 'complete')
            self.assertFalse(large_file.exists())
            self.assertEqual(small_file.read_bytes(), b'4B')
            self.assertTrue(self.row(small_key)['can_delete'])
        self.act(small_key, 'delete')
        self.assertEqual(self.finish()['state'], 'complete')
        self.assertFalse(small_file.exists())
        remaining = {row['id'] for row in self.library.request({})['items']}
        self.assertTrue({small_key, large_key}.isdisjoint(remaining))

    def test_interrupted_runtime_delete_is_visible_and_retryable(self):
        with patch.object(speaker_tools, 'platform_id', return_value='macOS-arm64'):
            home = speaker_tools.home('sherpa')
            version = home/'versions'/('a' * 32)
            version.mkdir(parents=True)
            save_json(version/'tool.json', {'backend':'sherpa', 'platform':'macOS-arm64', 'entry':speaker_tools.entry_name('sherpa')})
            (version/'worker').write_bytes(b'in use')
            neighbor = home/'versions'/('b' * 32)
            neighbor.mkdir()
            (neighbor/'private.txt').write_bytes(b'user')
            def fail_after_manifest(path):
                (path/'tool.json').unlink()
                raise PermissionError('사용 중')
            with patch.object(model_management.speaker_tool_integrity, 'remove_tree', side_effect=fail_after_manifest):
                self.act('tool-sherpa', 'delete')
                self.assertEqual(self.finish()['state'], 'error')
            self.assertTrue(self.row('tool-sherpa')['can_delete'])
            self.act('tool-sherpa', 'delete')
            self.assertEqual(self.finish()['state'], 'complete')
            self.assertFalse(self.row('tool-sherpa')['present'])
            self.assertEqual((neighbor/'private.txt').read_bytes(), b'user')

    def test_runtime_removal_preserves_other_engine_platform_and_local_files(self):
        with patch.object(speaker_tools, 'platform_id', return_value='macOS-arm64'):
            home = speaker_tools.home('sherpa')
            v = home/'versions'/('a'*32)
            v.mkdir(parents=True)
            save_json(v/'tool.json', {'backend':'sherpa', 'platform':'macOS-arm64', 'entry':speaker_tools.entry_name('sherpa')})
            (v/'worker').write_bytes(b'run')
            other = home.parent.parent/'Windows-x64/sherpa/versions/kept.dll'
            other.parent.mkdir(parents=True)
            other.write_bytes(b'keep')
            own = home/'notes.txt'
            own.write_bytes(b'keep')
            self.assertTrue(self.row('tool-sherpa')['present'])
            with self.manager.work_lock(self.base/'vod-4', 'speech', 'transcribe'):
                with self.assertRaises(Conflict):
                    self.act('tool-sherpa', 'delete')
            self.act('tool-sherpa', 'delete')
            self.assertEqual(self.finish()['state'], 'complete')
            self.assertFalse(v.exists())
            self.assertEqual(own.read_bytes(), other.read_bytes())
