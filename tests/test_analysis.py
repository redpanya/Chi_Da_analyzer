"""집계 근거·수집 범위·분석 저장과 기존 작업 격리 검사."""

import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from archive import analysis, analysis_store
from archive.jobs import Manager
from archive.server import make_server
from archive.storage import Conflict, ProjectLock, create_or_load, save_json
from test_archive import metadata


def row(ms, text='ㅋㅋ 와', author=None):
    return {'vod_id': '1', 'offset_ms': ms, 'text': text, 'nickname': '검증', 'user_id_hash': author}


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'vod-1'
        with ProjectLock(self.path):
            self.data = create_or_load(self.path, metadata(), '360p')
        self.data['metadata']['duration'] = 120
        self.export = self.path / 'exports' / 'test'
        self.export.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, values, state='complete'):
        file = self.export / 'chat.jsonl'
        file.write_text(''.join(json.dumps(value, ensure_ascii=False) + '\n' for value in values))
        label = {'complete': '제공 범위 순회·경계 대조 완료', 'empty': '현재 제공된 채팅 없음', 'unavailable': '채팅 미제공'}.get(state, '일부 수집 · 중단됨')
        save_json(self.export / 'summary.json', {'messages': len(values), 'status': label})
        self.data['tasks']['chat'].update(state=state, assets={'jsonl': 'exports/test/chat.jsonl'})
        save_json(self.path / 'project.json', self.data)
        return file

    def test_normalisation_counts_messages_separately_from_characters(self):
        found, chars = analysis.features('ㅋㅋㅋㅋ ㅋ ㅋ ᄒᄒ ＧＧ gg {:secretEmote:} https://example.test/abc')
        self.assertEqual(found, {('consonant', 'ㅋㅋ'), ('consonant', 'ㅎㅎ'), ('word', 'gg')})
        self.assertEqual(chars[('consonant', 'ㅋㅋ')], 6)
        self.assertEqual(chars[('consonant', 'ㅎㅎ')], 2)
        values = [row(41000, 'ㅋ' * 100, 'a'), row(42000, 'ㅋㅋ', 'b'), row(43000, 'ㅋ ㅋ')]
        result = analysis.analyze(values, 60000, True, {})
        item = next(item for item in result['candidates'] if item['term'] == 'ㅋㅋ')
        self.assertEqual((item['matching_messages'], item['character_count']), (3, 104))
        self.assertEqual((item['known_authors'], item['unknown_author_messages']), (2, 1))

    def test_sliding_window_finds_reaction_across_graph_boundary(self):
        result = analysis.analyze([row(9800, '대박'), row(10100, '대박')], 30000, True, {'min_repeats': 2})
        item = next(item for item in result['candidates'] if item['term'] == '대박')
        self.assertEqual((item['window_start_ms'], item['window_end_ms'], item['matching_messages']), (1000, 11000, 2))
        self.assertEqual([bin['messages'] for bin in result['graph']], [1, 1, 0])
        self.assertEqual(len(result['candidates']), 1)

    def test_haha_same_timestamp_and_missing_text_are_preserved(self):
        values = [row(10000, 'ㅎ ㅎ', 'a'), row(10000, 'ㅎㅎㅎ', 'a'), row(10500, 'ㅎㅎ'), row(11000, None)]
        result = analysis.analyze(values, 30000, True, {})
        item = next(item for item in result['candidates'] if item['term'] == 'ㅎㅎ')
        self.assertEqual((result['messages'], result['excluded_text_messages']), (4, 1))
        self.assertEqual((item['matching_messages'], item['character_count'], item['known_authors']), (3, 7, 1))

    def test_burst_reference_and_insufficient_start(self):
        values = [row(t, '일상') for t in range(5000, 60000, 10000)] + [row(60000 + i * 10, '와') for i in range(10)]
        result = analysis.analyze(values, 90000, True, {})
        item = next(item for item in result['candidates'] if item['kind'] == 'burst')
        self.assertEqual((item['peak_ms'], item['messages'], item['ratio']), (60000, 11, 11))
        initial = analysis.analyze([row(1000 + i) for i in range(20)], 20000, True, {})
        self.assertFalse(any(item['kind'] == 'burst' for item in initial['candidates']))
        self.assertTrue(initial['candidates'])
        self.assertEqual(initial['baseline_insufficient_until_ms'], 20000)

    def test_partial_empty_and_unavailable_have_different_coverage(self):
        self.source([row(1000), row(2000), row(13000)], 'paused')
        with self.assertRaisesRegex(ValueError, '일부'):
            analysis_store.run(self.path, self.data, {}, False)
        result = analysis_store.run(self.path, self.data, {}, True)
        self.assertEqual(result['known_until_ms'], 13001)
        self.assertEqual([bin['coverage'] for bin in result['graph'][:3]], ['known', 'partial', 'unknown'])
        self.assertIsNone(result['graph'][2]['messages'])
        self.source([row(1000), row(2000), row(13000)], 'review')
        uncertain = analysis_store.run(self.path, self.data, {}, True)
        self.assertTrue(uncertain['boundary_unverified'])
        self.assertEqual(uncertain['graph'][0]['coverage'], 'unverified')
        self.source([], 'empty')
        empty = analysis_store.run(self.path, self.data, {}, False)
        self.assertTrue(empty['complete_source'])
        self.assertTrue(all(bin['messages'] == 0 for bin in empty['graph']))
        self.source([], 'unavailable')
        disabled = analysis_store.run(self.path, self.data, {}, False)
        self.assertTrue(disabled['unavailable'])
        self.assertTrue(all(bin['messages'] is None for bin in disabled['graph']))

    def test_originals_unchanged_failed_save_keeps_previous_result(self):
        file = self.source([row(41000), row(42000), row(43000)])
        before = {p: p.read_bytes() for p in (file, self.path / 'project.json')}
        result = analysis_store.run(self.path, self.data, {}, False)
        self.assertEqual(result['source_sha256'], hashlib.sha256(before[file]).hexdigest())
        saved = (self.path / 'analysis/result.json').read_bytes()
        with patch('archive.storage.os.replace', side_effect=OSError('공간 부족')):
            with self.assertRaises(OSError):
                analysis_store.run(self.path, self.data, {'min_repeats': 2}, False)
        self.assertEqual((self.path / 'analysis/result.json').read_bytes(), saved)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_invalid_input_staleness_and_search_paging(self):
        values = [row(i, '검증 GG') for i in range(205)]
        file = self.source(values)
        analysis_store.run(self.path, self.data, {}, False)
        self.assertFalse(analysis_store.load(self.path, self.data)['stale'])
        first = analysis_store.search(self.path, self.data, query='gg')
        second = analysis_store.search(self.path, self.data, query='ＧＧ', cursor=first['next_cursor'])
        self.assertEqual(first['items'][-1]['offset_ms'], 99)
        self.assertEqual(second['items'][0]['offset_ms'], 100)
        self.assertEqual(len(analysis_store.search(self.path, self.data, start_ms=50, end_ms=60)['items']), 10)
        saved = (self.path / 'analysis/result.json').read_bytes()
        file.write_text(json.dumps(row(-1)))
        self.assertTrue(analysis_store.load(self.path, self.data)['stale'])
        with self.assertRaises(ValueError):
            analysis_store.run(self.path, self.data, {}, False)
        self.assertEqual((self.path / 'analysis/result.json').read_bytes(), saved)
        for options in ({'repeat_share': float('nan')}, {'window_seconds': True}, {'unknown': 3}):
            with self.assertRaises(ValueError):
                analysis.settings(options)

    def test_source_status_and_external_analysis_path_rejected(self):
        self.source([row(1000)], 'complete')
        save_json(self.export / 'summary.json', {'messages': 1, 'status': '일부 수집 · 중단됨'})
        with self.assertRaisesRegex(ValueError, '수집 상태'):
            analysis_store.run(self.path, self.data, {}, False)
        (self.path / 'analysis').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(Conflict):
            analysis_store.load(self.path, self.data)

    def test_analysis_locks_both_processes_and_downloads(self):
        self.source([row(1000)])
        manager, other = Manager(self.root), Manager(self.root)
        entered, release = threading.Event(), threading.Event()
        def run(*args):
            entered.set()
            release.wait(3)
        with patch('archive.jobs.analysis_store.run', side_effect=run):
            thread = threading.Thread(target=manager.analyze, args=(str(self.root), '1', {}))
            thread.start()
            try:
                self.assertTrue(entered.wait(1))
                self.assertTrue(manager.view(str(self.root), '1')['analysis_running'])
                with self.assertRaises(Conflict):
                    manager.start(str(self.root), '2', '360p', 'all')
                with self.assertRaises(Conflict):
                    other.analyze(str(self.root), '1', {})
            finally:
                release.set()
                thread.join()
        self.assertIsNone(manager.analysis_path)

    def test_http_analysis_and_chat_routes(self):
        self.source([row(41000), row(42000), row(43000)])
        server, url = make_server(Manager(self.root))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        parsed = urlsplit(url)
        connection = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        try:
            for action, extra in [('analyze', {'settings': {}}), ('analysis', {}), ('chats', {'query': 'ㅋㅋ'})]:
                body = json.dumps({'root': str(self.root), 'vod_id': '1'} | extra)
                connection.request('POST', parsed.path + 'api/' + action, body, {'Content-Type': 'application/json'})
                response = connection.getresponse()
                value = json.loads(response.read())
                self.assertEqual(response.status, 200, value)
                self.assertEqual(len(value['items']) if action == 'chats' else value['messages'], 3)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join()
