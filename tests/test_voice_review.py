"""실패 검토의 대상 범위·묶음 근거·원본 보존을 검사한다. 실제 AI 추론은 하지 않는다."""
import unittest
from pathlib import Path
from unittest.mock import patch

import test_voices as fixture
from archive import voice_store as store, speech_store
from archive.storage import Conflict, save_json


class ReviewTests(unittest.TestCase):
    setUp=fixture.VoiceTests.setUp
    tearDown=fixture.VoiceTests.tearDown
    audio=fixture.VoiceTests.audio
    fake_engine=fixture.VoiceTests.fake_engine
    transcribe=fixture.VoiceTests.transcribe
    prepare=fixture.VoiceTests.prepare
    change=fixture.VoiceTests.change

    def failures(self):
        ids=list(self.prepare());result=store.result(self.path)
        result['turns']=[{'speaker':0,'start_ms':100,'end_ms':500},{'speaker':0,'start_ms':1100,'end_ms':1500},
                         {'speaker':1,'start_ms':2000,'end_ms':2450}]
        result['speakers'],result['assignments']=store.assign(store.rows(self.path),result['turns'],'test')
        result['assignments'][store.rows(self.path)[-1]['id']]={'speaker':ids[1],'status':'confirmed','reason':None}
        save_json(store.local(self.path,'runs/test/result.json'),result)
        return ids

    def test_separate_lists_search_and_exact_assignment_preserve_originals(self):
        ids=self.failures();before={str(p):p.read_bytes() for p in self.path.rglob('*') if p.is_file()}
        result=store.browse(self.path,review=True)
        self.assertEqual(result['total_rows'],3);self.assertEqual(result['total'],1)
        self.assertEqual(result['failed_review']['total'],2)
        self.assertEqual(store.browse(self.path,query='없는 문장',review=True)['failed_review']['total'],2)
        self.assertEqual(store.browse(self.path,failed_query='없는 문장',review=True)['total'],1)
        target=result['failed_review']['items'][0]['id'];other=result['failed_review']['items'][1]['id']
        current=store.rows(self.path)
        # 겹치는 다른 발언이 있어도 ID 선택은 이웃을 변경하지 않는다.
        with patch.object(store,'rows',return_value=[row|{'start_ms':0,'end_ms':1500} for row in current]):
            self.change('assign',segment_id=target,speaker=ids[1])
        self.assertEqual(set(store.edits(self.path,'test')['assignments']),{target})
        result=store.browse(self.path,review=True)
        self.assertEqual([row['id'] for row in result['failed_review']['items']],[other])
        self.assertEqual(next(row for row in result['items'] if row['id']==target)['status'],'confirmed')
        self.assertTrue(all(Path(name).read_bytes()==content for name,content in before.items()))
        self.change('undo');self.assertEqual(store.browse(self.path,review=True)['failed_review']['total'],2)
        self.change('split',segment_id=target)
        self.assertNotIn(next(row for row in store.rows(self.path) if row['id']==target)['speaker'],ids)

    def test_candidate_batch_uses_existing_id_and_excludes_manual_decisions(self):
        ids=self.failures();result=store.browse(self.path,review=True,failed_group=ids[0])
        self.assertEqual(result['failed_review']['groups'],[{'id':ids[0],'name':'A화자','count':2}])
        self.assertEqual(result['failed_review']['total'],2)
        self.assertNotIn('confidence',result['failed_review'])
        original=store.local(self.path,'runs/test/result.json').read_bytes()
        self.change('assign',candidate_speaker=ids[0],speaker=ids[1])
        result=store.browse(self.path,review=True,failed_group=ids[0]);self.assertEqual(result['failed'],0)
        self.assertEqual(result['failed_review']['group'],'');self.assertEqual(result['total'],3)
        self.assertEqual(store.local(self.path,'runs/test/result.json').read_bytes(),original)
        self.change('undo');target=store.rows(self.path)[0]['id']
        self.change('assign',segment_id=target,speaker=None,reason='ambiguous')
        self.assertEqual(store.browse(self.path,review=True)['failed_review']['groups'],[])
        self.change('assign',candidate_speaker=ids[0],speaker=ids[1])
        self.assertEqual(next(row for row in store.rows(self.path) if row['id']==target)['status'],'failed')

    def test_no_group_for_multiple_unknown_missing_or_tiny_turns(self):
        row={'id':'x','start_ms':0,'end_ms':2000,'status':'failed','reason':'short'}
        for turns in ([],[{'speaker':0,'start_ms':0,'end_ms':199}],
                      [{'speaker':0,'start_ms':0,'end_ms':500},{'speaker':1,'start_ms':500,'end_ms':800}],
                      [{'speaker':0,'start_ms':0,'end_ms':500},{'speaker':None,'start_ms':600,'end_ms':900}]):
            self.assertEqual(store.failure_candidates({'speakers':{'a':'A','b':'B'},'turns':turns},[row]),{})

    def test_http_review_and_batch_assignment(self):
        import json, threading
        from http.client import HTTPConnection
        from urllib.parse import urlsplit
        from archive.jobs import Manager
        from archive.server import make_server
        ids=self.failures();manager=Manager(self.root);server,url=make_server(manager)
        thread=threading.Thread(target=server.serve_forever);thread.start();address=urlsplit(url)
        client=HTTPConnection(address.hostname,address.port,timeout=5)
        def post(action,values):
            client.request('POST',address.path+'api/'+action,json.dumps({'root':str(self.root),'vod_id':'1'}|values),{'Content-Type':'application/json'})
            response=client.getresponse();data=json.loads(response.read());self.assertEqual(response.status,200,data);return data
        try:
            data=post('voices-result',{'review':True,'failed_group':ids[0]})
            self.assertEqual(data['failed_review']['total'],2);self.assertEqual(data['total'],1)
            post('voices-edit',{'action':'assign','options':{'run':'test','revision':data['revision'],'candidate_speaker':ids[0],'speaker':ids[1]}})
            data=post('voices-result',{'review':True});self.assertEqual(data['failed_review']['total'],0);self.assertEqual(data['total'],3)
            post('voices-edit',{'action':'undo','options':{'run':'test','revision':data['revision']}})
            self.assertEqual(post('voices-result',{'review':True})['failed_review']['total'],2)
        finally:
            client.close();server.shutdown();server.server_close();thread.join();manager.close()

    def test_paging_search_batch_and_invalid_requests(self):
        ids=self.failures();row=store.rows(self.path)[0]
        rows=[row|{'id':str(i),'text':'선택' if i%2 else '보류'} for i in range(101)]
        with patch.object(store,'rows',return_value=rows):
            self.assertEqual(store.browse(self.path,review=True,failed_cursor=100)['failed_review']['cursor'],100)
            self.change('assign',candidate_speaker=ids[0],query='선택',speaker=ids[1])
            self.assertEqual(set(store.edits(self.path,'test')['assignments']),{str(i) for i in range(101) if i%2})
        with patch.object(store,'rows',return_value=rows[:100]):
            page=store.browse(self.path,review=True,failed_cursor=100)['failed_review']
            self.assertEqual(page['cursor'],0);self.assertEqual(len(page['items']),100)
        before=store.local(self.path,'runs/test/edits.json').read_bytes()
        for options in ({'segment_id':None},{'segment_id':'없는 발언'},{'candidate_speaker':'없는 화자'},
                        {'candidate_speaker':ids[0],'query':['잘못된 형식']}):
            with self.assertRaises(ValueError):self.change('assign',speaker=ids[1],**options)
        self.assertEqual(store.local(self.path,'runs/test/edits.json').read_bytes(),before)
        with self.assertRaises(Conflict):store.edit(self.path,'test',0,'assign',segment_id=row['id'],speaker=ids[1])
        for options in ({'review':'true'},{'failed_query':[]},{'failed_cursor':True},{'failed_cursor':-1},{'failed_group':[]}):
            with self.assertRaises(ValueError):store.browse(self.path,**options)
        speech_store.update(self.path,run=None)
        self.assertEqual(store.browse(self.path,review=True)['failed_review']['total'],0)
        with self.assertRaises(Conflict):self.change('assign',segment_id=row['id'],speaker=ids[1])


if __name__=='__main__':unittest.main()
