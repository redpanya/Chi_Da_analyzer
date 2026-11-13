"""영상 나누기의 세션 수명과 원본, 완료 파일 보존 검사."""
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from archive import split_contract as contract
from archive.source import Cancelled
from archive.split_jobs import Splitter
from archive.storage import ProjectLock, save_json


class SplitSession(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.old = self.root/'records'
        self.old_id = 'a'*32
        save_json(self.old/self.old_id/'manifest.json', {'state': 'complete', 'id': self.old_id})
        save_json(self.old/'draft.json', {'revision': 4, 'draft': {'old': True}})
        self.old_files = {p: p.read_bytes() for p in self.old.rglob('*.json')}
        self.source = self.root/'원본.mp4'
        self.source.write_bytes(b'original')
        self.manager = SimpleNamespace(guard=threading.RLock())
        self.split = Splitter(self.manager, self.old)
        self.manager.speech_idle = self.split.idle
        self.source_id = 'b'*32
        self.split.sources[self.source_id] = {'name': self.source.name, 'path': str(self.source),
            'identity': contract.identity(self.source), 'duration': 6, 'streams': []}

    def tearDown(self):
        self.split.close()
        self.assertEqual(self.source.read_bytes(), b'original')
        for file, content in self.old_files.items():
            self.assertEqual(file.read_bytes(), content)
        self.temp.cleanup()

    def plan(self):
        with patch('archive.split_jobs.media.boundaries', return_value={'parts': [{}, {}]}):
            self.split.dispatch('plan', {'source_id': self.source_id, 'points': [2]})
            self.split.job.thread.join(5)
        self.assertTrue(self.split.job.closed)
        return self.split.dispatch('current', {})['run']

    def test_new_session_does_not_restore_existing_records(self):
        self.assertEqual(self.split.dispatch('current', {}), {'run': None})
        self.assertEqual(self.split.dispatch('draft-get', {}), {'revision': 0, 'draft': None})
        self.assertEqual(self.split.dispatch('list', {})['runs'], [])
        self.assertIsNone(self.split._temp)
        with self.assertRaises(FileNotFoundError):
            self.split.state(self.old_id)

    def test_register_replaces_current_only_after_success(self):
        state = self.plan()
        with patch('archive.split_jobs.media.inspect', side_effect=ValueError('지원하지 않는 파일')):
            with self.assertRaises(ValueError):
                self.split.dispatch('register', {'path': str(self.source)})
        self.assertEqual(self.split.dispatch('current', {})['run']['id'], state['id'])
        with patch('archive.split_jobs.media.inspect', return_value=state['source']):
            self.split.dispatch('register', {'path': str(self.source)})
        self.assertEqual(self.split.dispatch('current', {}), {'run': None})

    def test_current_state_and_output_link_survive_only_within_session(self):
        state = self.plan()
        self.assertEqual(state['state'], 'ready')
        self.assertEqual(self.split.dispatch('list', {})['runs'], [])

        def render(work):
            output = Path(work.value['folder'])/'part-000.mp4'
            output.write_bytes(b'completed output')
            work.update(outputs={'0': {'name': output.name, 'identity': contract.identity(output)}})

        with patch('archive.split_jobs.split_render.render', side_effect=render):
            self.split.dispatch('start', {'id': state['id'], 'folder': str(self.root)})
            self.split.job.thread.join(5)
        finished = self.split.dispatch('current', {})['run']
        self.assertEqual(finished['state'], 'complete')
        self.assertEqual(finished, self.split.dispatch('current', {})['run'])
        output = self.split.media_file(run=state['id'], index='0')
        work_root = self.split.root
        self.split.close()
        self.assertFalse(work_root.exists())
        self.assertEqual(output.read_bytes(), b'completed output')
        fresh = Splitter(self.manager, self.old)
        try:
            self.assertEqual(fresh.dispatch('current', {}), {'run': None})
            with self.assertRaises(FileNotFoundError):
                fresh.state(state['id'])
        finally:
            fresh.close()
        self.assertEqual(output.read_bytes(), b'completed output')

    def test_close_stops_worker_before_removing_only_internal_files(self):
        state = self.plan()
        started = threading.Event()
        finished = threading.Event()
        output = None

        def render(work):
            nonlocal output
            output = Path(work.value['folder'])/'part-000.mp4'
            output.write_bytes(b'completed output')
            work.update(outputs={'0': {'name': output.name, 'identity': contract.identity(output)}})
            started.set()
            if not work.stop.wait(5):
                raise AssertionError('중단 요청이 도착하지 않았습니다')
            self.assertTrue(work.file.exists())
            finished.set()
            raise Cancelled()

        with patch('archive.split_jobs.split_render.render', side_effect=render):
            self.split.dispatch('start', {'id': state['id'], 'folder': str(self.root)})
            self.assertTrue(started.wait(5))
            work_root = self.split.root
            self.split.close()
        self.assertTrue(finished.is_set())
        self.assertFalse(work_root.exists())
        self.assertEqual(output.read_bytes(), b'completed output')
        self.assertEqual(self.split.dispatch('current', {}), {'run': None})

    def test_output_cannot_be_saved_inside_internal_temp_folder(self):
        state = self.plan()
        for folder in (self.split.root, self.split.file(state['id']).parent):
            with self.assertRaisesRegex(ValueError, '임시 폴더 밖'):
                self.split.dispatch('start', {'id': state['id'], 'folder': str(folder)})
        with ProjectLock(self.split.root):
            pass


if __name__ == '__main__':
    unittest.main()
