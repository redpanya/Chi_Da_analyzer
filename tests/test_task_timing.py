"""실행·중단·완료·재실행 시간과 기존 상태 호환 검증."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from archive import task_timing as timing, speech_store, voice_store, context_job
from archive.storage import Project, ProjectLock, create_or_load, read_json, recover
from test_archive import metadata


class TimingTests(unittest.TestCase):
    def test_pause_resume_freeze_complete_and_new_run(self):
        with patch.object(timing, 'now_ms', return_value=1000):
            value = {'state': 'running', 'timing': timing.start({})}
        with patch.object(timing, 'now_ms', return_value=4500):
            value = timing.update(value, {'state': 'paused'})
        self.assertEqual(value['timing']['elapsed_ms'], 3500)
        with patch.object(timing, 'now_ms', return_value=100000):
            resumed = value | {'state': 'running', 'timing': timing.start(value, resume=True)}
        with patch.object(timing, 'now_ms', return_value=102000):
            done = timing.update(resumed, {'state': 'complete'})
        self.assertEqual(done['timing']['elapsed_ms'], 5500)
        self.assertIsNone(done['timing']['since_ms'])
        self.assertFalse(done['timing']['partial'])
        with patch.object(timing, 'now_ms', return_value=999999):
            self.assertEqual(timing.update(done, {'exports': {}})['timing'], done['timing'])
            self.assertEqual(timing.start(done, resume=True)['elapsed_ms'], 0)

    def test_abrupt_exit_legacy_and_clock_reversal(self):
        value = {'state': 'running', 'timing': {'elapsed_ms': 5000, 'since_ms': 10000}}
        with patch.object(timing, 'now_ms', return_value=9000):
            self.assertEqual(timing.update(value, {})['timing']['elapsed_ms'], 5000)
        recovered = timing.interrupted(value)
        self.assertEqual(recovered['timing']['elapsed_ms'], 5000)
        self.assertTrue(recovered['timing']['partial'])
        self.assertIsNone(recovered['timing']['since_ms'])
        with patch.object(timing, 'now_ms', return_value=900000):
            self.assertEqual(timing.start(value, resume=True)['elapsed_ms'], 5000)
            self.assertTrue(timing.start({'state': 'error'}, resume=True)['partial'])
        self.assertEqual(timing.update({'state': 'complete'}, {'message': '기존 자료'}), {'state': 'complete', 'message': '기존 자료'})

    def test_download_tasks_independent_and_recovery_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'vod-1'
            with ProjectLock(path) as lock:
                project = Project(path, create_or_load(path, metadata(), '360p'), lock)
                with patch.object(timing, 'now_ms', return_value=1000):
                    for kind in ('video', 'chat'):
                        project.update(kind, state='queued', timing=timing.start({}))
                with patch.object(timing, 'now_ms', return_value=6000):
                    project.update('chat', state='complete')
                    project.update('video', state='downloading')
                with patch.object(timing, 'now_ms', return_value=20000):
                    recovered = recover(path, project.snapshot())
                self.assertEqual(recovered['tasks']['chat']['timing']['elapsed_ms'], 5000)
                self.assertEqual(recovered['tasks']['video']['timing']['elapsed_ms'], 5000)
                self.assertTrue(recovered['tasks']['video']['timing']['partial'])
                self.assertEqual(recovered, read_json(path/'project.json'))

    def test_speech_voice_and_context_updates_preserve_finished_timer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for store in (speech_store, voice_store):
                with patch.object(timing, 'now_ms', return_value=1000):
                    store.update(path, state='running', timing=timing.start({}))
                with patch.object(timing, 'now_ms', return_value=6000):
                    store.update(path, state='error')
                store.update(path, exports={})
                self.assertEqual(store.state(path)['timing']['elapsed_ms'], 5000)
            with patch.object(timing, 'now_ms', return_value=1000):
                job = context_job.ContextJob(path, '1', ProjectLock(path), 'model')
            try:
                with patch.object(timing, 'now_ms', return_value=4000): job.update(state='complete')
                job.update(message='완료 결과 확인')
                self.assertEqual(context_job.state(path)['timing']['elapsed_ms'], 3000)
            finally: job.lock.close()


if __name__ == '__main__': unittest.main()
