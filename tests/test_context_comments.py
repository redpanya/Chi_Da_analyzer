"""댓글 목록 저장과 이전 메모·원본 보호."""
import copy
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlsplit
from archive import context_comments as comments
from archive.storage import save_json, read_json, Conflict

class CommentListTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'vod-1';self.run='a'*32
        save_json(self.path/'context/state.json',{'runs':[{'id':self.run}],'run':self.run})
        self.original=self.path/f'context/runs/{self.run}/result.json';save_json(self.original,{'원본':'보존'})
        self.row={'id':'1','source_id':'1','start_ms':1000,'end_ms':2000,'title':'편집 제목'}
        self.value={'revision':0,'format':2,'rows':[self.row],'legacy_text':''}
    def test_roundtrip_conflict_reset_and_original(self):
        before=self.original.read_bytes();saved=comments.save(self.path,self.run,self.value)
        self.assertEqual(comments.read(self.path,self.run),saved)
        with self.assertRaises(Conflict):comments.save(self.path,self.run,self.value)
        empty=comments.save(self.path,self.run,saved|{'rows':[]});self.assertEqual(empty['rows'],[])
        self.assertEqual(self.original.read_bytes(),before)
    def test_legacy_backup_and_downgrade_blocked(self):
        old={'revision':0,'text':'00:00:01 직접 고친 제목\n자유 문장','selected':['1'],'edited':True,'basis':'원래 제목'}
        previous=comments.save(self.path,self.run,old);file=comments.target(self.path,self.run);original=file.read_bytes()
        new=comments.save(self.path,self.run,self.value|{'revision':1,'legacy_text':old['text']})
        backup=file.with_name(self.run+'.legacy.json');self.assertEqual(backup.read_bytes(),original)
        comments.save(self.path,self.run,new|{'rows':[]});self.assertEqual(backup.read_bytes(),original)
        with self.assertRaises(Conflict):comments.save(self.path,self.run,old|{'revision':3})
    def test_bad_rows_and_symlink_rejected(self):
        for patch in ({'start_ms':-1},{'end_ms':float('nan')},{'start_ms':True},{'end_ms':1000},{'title':'둘\n줄'},{'start_ms':None}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):comments.save(self.path,self.run,self.value|{'rows':[self.row|patch]})
        for rows in ([self.row,self.row], [self.row,self.row|{'id':'2'}]):
            with self.assertRaises(ValueError):comments.save(self.path,self.run,self.value|{'rows':rows})
        with self.assertRaises(ValueError):comments.save(self.path,'../다른결과',self.value)
        folder=self.path/'context/comments';folder.mkdir(exist_ok=True)
        backup=folder/(self.run+'.legacy.json');backup.symlink_to(self.original)
        old={'revision':0,'text':'원문','selected':[],'edited':True,'basis':''};comments.save(self.path,self.run,old)
        with self.assertRaises(ValueError):comments.save(self.path,self.run,self.value|{'revision':1})
    def test_unmatched_text_can_be_preserved(self):
        saved=comments.save(self.path,self.run,self.value|{'rows':[self.row|{'source_id':None,'start_ms':None,'end_ms':None,'title':'자유 문장'}]})
        self.assertIsNone(saved['rows'][0]['end_ms'])

    def test_clip_and_summary_drafts_are_separate(self):
        clip_run='b'*32
        save_json(self.path/'context/state.json',{'runs':[{'id':self.run,'mode':'detail'},{'id':clip_run,'mode':'clips'}],'run':self.run,'clip_run':clip_run})
        clip_result=self.path/f'context/runs/{clip_run}/result.json';save_json(clip_result,{'mode':'clips','원본':'보존'})
        before={p:p.read_bytes() for p in (self.original,clip_result)}
        detail=comments.save(self.path,self.run,self.value)
        clip=comments.save(self.path,clip_run,self.value|{'rows':[self.row|{'id':'clip-a','source_id':'clip-a','title':'클립 제목'}]})
        self.assertEqual(comments.read(self.path,self.run),detail)
        self.assertEqual(comments.read(self.path,clip_run),clip)
        comments.save(self.path,clip_run,clip|{'rows':[]})
        self.assertEqual(comments.read(self.path,self.run),detail)
        for p,raw in before.items():self.assertEqual(p.read_bytes(),raw)

    def speech_run(self, run=None):
        file=self.path/f"speech/runs/{run or self.run}/manifest.json"
        save_json(file,{'id':run or self.run,'complete':True,'segment_count':1,'language':'ko'})
        return file

    def test_speech_and_context_comments_are_independent_and_keep_sources(self):
        speech=self.speech_run();before=speech.read_bytes()
        context=comments.save(self.path,self.run,self.value)
        transcript=comments.save(self.path,self.run,self.value|{'rows':[self.row|{'title':'전사 댓글'}]},source='speech')
        self.assertEqual(comments.read(self.path,self.run),context)
        self.assertEqual(comments.read(self.path,self.run,source='speech'),transcript)
        self.assertEqual(comments.target(self.path,self.run,'speech').name,f'speech-{self.run}.json')
        with self.assertRaises(Conflict):comments.save(self.path,self.run,self.value,source='speech')
        self.assertEqual(speech.read_bytes(),before)
        self.assertEqual(read_json(self.original),{'원본':'보존'})

    def test_speech_source_validation_and_deleted_run_protection(self):
        for source in (None, '', 'voices', '../speech'):
            with self.subTest(source=source),self.assertRaises(ValueError):
                comments.read(self.path,self.run,source=source)
        with self.assertRaises(ValueError):comments.read(self.path,self.run,source='speech')
        speech=self.speech_run();saved=comments.save(self.path,self.run,self.value,source='speech')
        file=comments.target(self.path,self.run,source='speech');before=file.read_bytes()
        save_json(self.path/'speech/state.json',{'deleted_runs':[self.run]})
        with self.assertRaises(ValueError):comments.save(self.path,self.run,saved,source='speech')
        self.assertEqual(file.read_bytes(),before)
        self.assertTrue(speech.exists())

    def test_speech_legacy_backup_uses_its_own_namespace(self):
        self.speech_run()
        old={'revision':0,'text':'00:00:01 이전 전사 댓글','selected':[],'edited':True,'basis':''}
        comments.save(self.path,self.run,old,source='speech')
        file=comments.target(self.path,self.run,source='speech');before=file.read_bytes()
        comments.save(self.path,self.run,self.value|{'revision':1},source='speech')
        self.assertEqual(file.with_name(f'speech-{self.run}.legacy.json').read_bytes(),before)
        self.assertFalse(file.with_name(self.run+'.legacy.json').exists())

    def test_comment_api_routes_optional_source(self):
        from archive.server import make_server
        self.speech_run()
        server,url=make_server(None);thread=threading.Thread(target=server.serve_forever);thread.start()
        parsed=urlsplit(url);client=HTTPConnection(parsed.hostname,parsed.port,timeout=5)
        try:
            for source in (None,'speech'):
                request={'root':str(self.path.parent),'vod_id':'1','run':self.run}
                if source:request['source']=source
                for action in ('context-comment-save','context-comment'):
                    data=request|({'draft':self.value} if action.endswith('-save') else {})
                    client.request('POST',parsed.path+'api/'+action,body=json.dumps(data),
                                   headers={'Origin':f'http://{parsed.netloc}','Content-Type':'application/json'})
                    response=client.getresponse();payload=json.loads(response.read())
                    self.assertEqual(response.status,200,payload)
                    self.assertEqual(payload,self.value|{'revision':1})
        finally:
            client.close();server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
