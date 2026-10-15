"""M5 통합 시간 경계·조회 격리·현재 이름·HTTP 검증."""
import json
from http.client import HTTPConnection
import threading
import unittest
from urllib.parse import urlsplit
import test_voices as fixture
import test_analysis as analysis_fixture
from test_analysis import row
from archive import explore, analysis_store, speech_store, voice_store
from archive.storage import save_json
from archive.jobs import Manager
from archive.server import make_server

class ExploreTests(unittest.TestCase):
    setUp = fixture.VoiceTests.setUp
    tearDown = fixture.VoiceTests.tearDown
    audio = fixture.VoiceTests.audio
    fake_engine = fixture.VoiceTests.fake_engine
    transcribe = fixture.VoiceTests.transcribe
    prepare = fixture.VoiceTests.prepare
    change = fixture.VoiceTests.change
    source = analysis_fixture.AnalysisTests.source

    def chats(self, values, state='complete'):
        self.export = self.path / 'exports/test'
        self.export.mkdir(parents=True, exist_ok=True)
        return self.source(values, state)

    def query(self, **args):
        return explore.search(str(self.root), '1', **args)

    def test_order_duplicate_paging_and_preservation(self):
        self.prepare(); self.chats([row(500, 'ㅋㅋ ＧＧ') for _ in range(205)] + [row(1000, '끝')])
        analysis_store.run(self.path, self.data, {}, False)
        before = {str(p): p.read_bytes() for p in self.path.rglob('*') if p.is_file()}
        items = []
        for cursor in [0, 100, 200]:
            page = self.query(cursor=cursor); items += page['items']
        self.assertEqual(len(items), page['total'])
        self.assertEqual(len({(r['kind'], r['id']) for r in items}), len(items))
        self.assertEqual([r['at_ms'] for r in items], sorted(r['at_ms'] for r in items))
        self.assertEqual(self.query(source='chat', query='gg')['total'], 205)
        self.assertEqual(self.query(source='chat', query='ᄏᄏ')['total'], 205)
        explore.info(str(self.root), '1')
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.path.rglob('*') if p.is_file()})

    def test_half_open_overlap_offsets_and_video_tail(self):
        self.prepare(); self.chats([row(0), row(999), row(1000), row(120000)])
        q = self.query(start_ms=1000, end_ms=2000)
        self.assertEqual([(r['kind'], r['start_ms']) for r in q['items']], [('chat', 1000), ('speech', 1000)])
        shifted = self.query(source='chat', chat_offset_ms=1000, start_ms=1000, end_ms=2000)
        self.assertEqual([r['raw_start_ms'] for r in shifted['items']], [0, 999])
        self.assertEqual(self.query(source='chat', chat_offset_ms=-1000)['items'][0]['at_ms'], 0)
        self.assertEqual(self.query(source='chat')['items'][-1]['at_ms'], 120000)
        self.assertEqual(explore.info(str(self.root), '1', 1000)['chat_offset_ms'], 1000)

    def test_current_names_corrections_and_failure_filter(self):
        ids = list(self.prepare()); self.chats([row(1500)])
        self.change('rename', speaker=ids[0], name='김모모')
        self.assertEqual(self.query(query='김모모')['total'], 1)
        self.change('assign', speaker=None, start_ms=1000, end_ms=2000, reason='ambiguous')
        failed = self.query(source='speech', speaker='failed')
        self.assertTrue(failed['items']); self.assertTrue(all(r['status'] == 'failed' for r in failed['items']))
        self.assertEqual(self.query(source='chat', speaker='failed')['total'], 1)
        run = speech_store.manifest(self.path)
        speech_store.correct(self.path, run['id'], self.query(source='speech')['items'][0]['id'], '교정한 말')
        self.assertEqual(self.query(query='교정한 말')['total'], 1)
        self.change('rename', speaker=ids[0], name='새 이름')
        self.assertEqual(self.query(query='김모모')['total'], 0)
        self.assertEqual(self.query(query='새 이름')['total'], 1)

    def test_missing_partial_and_corrupt_sources_are_isolated(self):
        self.chats([row(500)], 'paused'); self.assertEqual(self.query()['total'], 1)
        self.prepare(); manifest = speech_store.manifest(self.path)
        manifest.update(chunks=manifest['chunks'][:1], processed_ms=1000, complete=False)
        save_json(speech_store.local(self.path, f"runs/{manifest['id']}/manifest.json"), manifest)
        info = explore.info(str(self.root), '1')
        self.assertFalse(info['complete']); self.assertEqual(info['processed_ms'], 1000)
        self.assertIn('전사 일부 범위 처리', info['notes'])
        voice_store.local(self.path, 'state.json').write_text('{')
        self.assertEqual(self.query()['total'], 2)
        self.assertTrue(any('화자 파일' in n for n in self.query()['notes']))
        speech_store.local(self.path, 'state.json').write_text('{')
        self.assertEqual(self.query()['total'], 1)
        with (self.export/'chat.jsonl').open('a') as f: f.write('{')
        result = self.query(); self.assertEqual(result['total'], 0)
        self.assertTrue(any('채팅 파일' in n for n in result['notes']))

    def test_stale_speaker_not_reused_and_symlink_not_followed(self):
        self.prepare(); self.chats([row(500)]); self.video.write_bytes(b'changed')
        info = explore.info(str(self.root), '1')
        self.assertEqual(info['speakers'], {})
        self.assertEqual(self.query(source='speech', speaker='unassigned')['total'], 3)
        self.assertTrue(any('지난 영상' in n for n in info['notes']))
        file = self.export/'chat.jsonl'; file.unlink(); file.symlink_to(self.video)
        self.assertEqual(self.query()['total'], 3)
        self.assertTrue(any('채팅 파일' in n for n in self.query()['notes']))

    def test_late_bad_chat_does_not_leave_partial_page(self):
        self.prepare(); file = self.chats([row(0)] * 150)
        with file.open('a') as f: f.write('{')
        result = self.query(); self.assertEqual(result['total'], 3)
        self.assertTrue(all(r['kind'] == 'speech' for r in result['items']))

    def test_bad_reaction_graph_and_no_optional_results(self):
        self.assertEqual(self.query()['total'], 0)
        self.chats([row(500)])
        analysis_store.run(self.path, self.data, {}, False)
        result = json.loads((self.path/'analysis/result.json').read_text())
        result['graph'][0]['messages'] = '손상'
        save_json(self.path/'analysis/result.json', result)
        info = explore.info(str(self.root), '1')
        self.assertEqual(info['graph'], [])
        self.assertTrue(any('반응 분석 파일' in n for n in info['notes']))
        self.assertEqual(self.query()['total'], 1)

    def test_http_validation_and_no_write(self):
        self.prepare(); manager = Manager(self.root); server, url = make_server(manager)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        parsed = urlsplit(url); conn = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        try:
            for action, values, status in [('explore-info', {}, 200), ('explore-search', {'source':'speech'}, 200),
                 ('explore-search', {'cursor':True}, 400), ('explore-search', {'start_ms':1000,'end_ms':0}, 400),
                 ('explore-search', {'chat_offset_ms':600001}, 400), ('explore-search', {'query':'x'*201}, 400),
                 ('explore-search', {'source':'invalid'}, 400), ('explore-search', {'other':'x'}, 400)]:
                conn.request('POST', parsed.path+'api/'+action, json.dumps({'root':str(self.root),'vod_id':'1'} | values), {'Content-Type':'application/json'})
                response = conn.getresponse(); response.read(); self.assertEqual(response.status, status)
        finally:
            conn.close(); server.shutdown(); server.server_close(); thread.join(); manager.close()

if __name__ == '__main__': unittest.main()
