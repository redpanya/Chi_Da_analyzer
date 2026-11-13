"""외부 수신 상태의 정확한 귀속과 상세 조회 중 보존을 검사한다."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_context_exchange
from archive import context_exchange as exchange, job_detail_external
from archive.storage import Conflict, read_json, save_json


class ExternalDetailTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_context_exchange.ExchangeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.path = self.fixture.path
        self.bundle = self.fixture.create()
        self.entries = self.fixture.responses(self.bundle)
        self.manager = SimpleNamespace(guard=threading.RLock())
        for target, value in [('archive.job_detail_external.project_path', self.path),
                              ('archive.job_detail_external.load_project', {'metadata': {'title': '검사 영상'}})]:
            mock = patch(target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def query(self, **extra):
        request = {'root': str(self.path.parent), 'vod_id': '1', 'kind': 'external', 'id': self.bundle['id']} | extra
        return job_detail_external.detail(self.manager, request, {'kind': 'external', 'fields': [], 'actions': [], 'result': None})

    def snapshot(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.path.rglob('*') if p.is_file()}

    def test_partial_and_complete_are_independent_of_old_gemma_state(self):
        run = self.fixture.receive(self.entries[:1])['run']
        before = self.snapshot()
        value = self.query()
        self.assertEqual(value['state'], 'partial')
        self.assertEqual(value['received'], 1)
        self.assertEqual(value['total'], len(self.entries))
        self.assertEqual(value['result']['run'], run)
        self.assertEqual(value['result']['mode'], 'timestamps')
        self.assertEqual(value['workspace']['export_id'], self.bundle['id'])
        self.assertIsNone(value['timing'])
        self.assertEqual(value['actions'], [])
        self.assertEqual(before, self.snapshot())
        final = self.fixture.receive(self.entries[1:])['run']
        self.assertEqual(self.query()['state'], 'complete')
        self.assertEqual(self.query()['result']['run'], final)

    def test_cancelled_partial_only_offers_external_resume_with_unchanged_input(self):
        self.fixture.receive(self.entries[:1])
        exchange.cancel(self.path, self.bundle['id'])
        before = self.snapshot()
        value = self.query()
        self.assertEqual(value['state'], 'cancelled')
        self.assertEqual(value['actions'], [{'label': '외부 결과 대기 재개', 'action': 'context-exchange-resume',
            'data': {'root': str(self.path.parent), 'vod_id': '1', 'export_id': self.bundle['id']}}])
        self.assertEqual(before, self.snapshot())
        self.fixture.source['rows'][0]['text'] = '수정한 전사'
        self.assertEqual(self.query()['actions'], [])

    def test_missing_corrupt_or_foreign_result_never_falls_back(self):
        run = self.fixture.receive(self.entries)['run']
        file = self.path / f'context/runs/{run}/result.json'
        original = file.read_bytes()
        for data in (b'{', b'{}'):
            file.write_bytes(data)
            value = self.query()
            self.assertIsNone(value['result'])
            self.assertEqual(value['state'], 'review')
        file.write_bytes(original)
        save_json(file, read_json(file) | {'complete': False})
        self.assertEqual(self.query()['state'], 'review')
        file.write_bytes(original)
        save_json(file, read_json(file) | {'export_id': 'f' * 32})
        self.assertIsNone(self.query()['result'])
        file.unlink()
        self.assertIsNone(self.query()['result'])

    def test_corrupt_saved_responses_cannot_open_a_different_result(self):
        run = self.fixture.receive(self.entries)['run']
        file = self.path / f'context/runs/{run}/work.json'
        work = read_json(file)
        work['replies'].pop(next(iter(work['replies'])))
        save_json(file, work)
        value = self.query()
        self.assertIsNone(value['result'])
        self.assertEqual(value['state'], 'review')

    def test_exact_export_id_and_manifest_identity_are_required(self):
        for value in ('../escape', 'f' * 32, None):
            with self.assertRaises(ValueError):
                self.query(id=value)
        with self.assertRaises(Conflict):
            self.query(export_id='f' * 32)
        file = exchange.folder(self.path, self.bundle['id']) / 'manifest.json'
        save_json(file, read_json(file) | {'id': 'f' * 32})
        with self.assertRaises(ValueError):
            self.query()


if __name__ == '__main__':
    unittest.main()
