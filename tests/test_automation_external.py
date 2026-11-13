"""완전히 받은 외부 결과만 같은 자동화 입력에 재사용하고 원본은 보존한다."""
import copy
import unittest
from unittest.mock import patch

import test_context_exchange
from archive import automation_summary, context_exchange as exchange
from archive.storage import read_json, save_json


class ExternalReuseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_context_exchange.ExchangeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.path = self.fixture.path
        self.settings = {'thinking': True, 'speakers_enabled': False, 'background': '', 'custom_request': ''}
        for target, value in [('archive.speech_store.state', {'run': 'a' * 32}), ('archive.voice_store.result', None)]:
            mock = patch(target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def create(self, mode='timestamps', partial=False):
        bundle = self.fixture.create(mode, chat=mode != 'timestamps')
        if mode == 'clips':
            manifest = read_json(exchange.folder(self.path, bundle['id']) / 'manifest.json')
            source = read_json(exchange.folder(self.path, bundle['id']) / 'source.json')
            entries = [dict(schema_version=1, export_id=bundle['id'], chunk_id=c['id'], mode=mode, clips=[],
                            coverage={'first_id': source['rows'][c['first']]['id'], 'last_id': source['rows'][c['last'] - 1]['id']})
                       for c in manifest['chunks']]
        else:
            entries = self.fixture.responses(bundle)
        run = self.fixture.receive(entries[:1] if partial else entries)['run']
        return run

    def request(self, mode='timestamps'):
        return automation_summary.request(self.path, '1', 'summary' if mode == 'detail' else mode, self.settings)[0]

    def snapshot(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.path.rglob('*') if p.is_file()}

    def test_all_modes_reuse_without_model_or_file_changes(self):
        for mode in ('timestamps', 'detail', 'clips'):
            with self.subTest(mode=mode):
                self.create(mode)
                before = self.snapshot()
                self.assertIsNone(self.request(mode))
                self.assertEqual(before, self.snapshot())
        self.settings['thinking'] = False
        self.assertIsNone(self.request('clips'))

    def test_partial_external_is_not_resumed_by_gemma(self):
        self.create(partial=True)
        before = self.snapshot()
        self.assertEqual(self.request(), 'timestamps')
        self.assertEqual(before, self.snapshot())

    def test_changed_settings_and_unverified_result_are_not_reused(self):
        run = self.create()
        file = self.path / f'context/runs/{run}/result.json'
        original = read_json(file)
        changes = [{'complete': False}, {'mode': 'detail'}, {'origin': 'local'}, {'scope': 'full'},
                   {'analysis_guidance': {}}, {'fingerprint': 'changed'}, {'include_chat': True},
                   {'chat_offset_ms': 1000}, {'input_selection': {'transcript_run': 'other', 'speaker_run': None}}]
        for change in changes:
            with self.subTest(change=change):
                save_json(file, original | change)
                before = self.snapshot()
                self.assertEqual(self.request(), 'timestamps')
                self.assertEqual(before, self.snapshot())
        save_json(file, [])
        self.assertEqual(self.request(), 'timestamps')
        save_json(file, original)
        self.settings['custom_request'] = '새 기준'
        self.assertEqual(self.request(), 'timestamps')

    def test_missing_reply_review_and_invalid_evidence_are_not_reused(self):
        run = self.create()
        file = self.path / f'context/runs/{run}/work.json'
        original = read_json(file)
        missing = copy.deepcopy(original)
        missing['replies'].pop(next(iter(missing['replies'])))
        review = copy.deepcopy(original)
        next(iter(review['replies'].values()))['topics'][0]['review_needed'] = True
        invalid = copy.deepcopy(original)
        next(iter(invalid['replies'].values()))['topics'][0]['evidence_ids'] = ['S999']
        gap = copy.deepcopy(original)
        gap['chunks'][0]['first'] = 1
        for value in (missing, review, invalid, gap):
            save_json(file, value)
            before = self.snapshot()
            self.assertEqual(self.request(), 'timestamps')
            self.assertEqual(before, self.snapshot())
        file.unlink()
        self.assertEqual(self.request(), 'timestamps')

    def test_corrected_input_and_changed_export_source_are_not_reused(self):
        run = self.create()
        self.fixture.source['rows'][0]['text'] = '수정한 전사'
        self.assertEqual(self.request(), 'timestamps')
        self.fixture.source['rows'][0]['text'] = '독립 검증 발언 0'
        self.assertIsNone(self.request())
        file = self.path / f'context/runs/{run}/source.json'
        source = read_json(file)
        source['rows'][0]['text'] = '바뀐 보존 자료'
        save_json(file, source)
        self.assertEqual(self.request(), 'timestamps')


if __name__ == '__main__':
    unittest.main()
