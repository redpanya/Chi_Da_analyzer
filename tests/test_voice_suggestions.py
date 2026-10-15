"""후보는 원본과 수동 배정을 보존하고 음향·문맥 두 근거만으로 제안한다."""
import copy
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
import test_voices as fixture
from archive import voice_store as store, voice_suggestions as suggestions, voices, speech_store, speech_media
from archive import context_job, voice_retranscription, speech_model, voice_models
from archive.storage import Conflict,ProjectLock,save_json,read_json
from archive.source import Cancelled


class SuggestionTests(unittest.TestCase):
    setUp=fixture.VoiceTests.setUp
    tearDown=fixture.VoiceTests.tearDown
    audio=fixture.VoiceTests.audio
    transcribe=fixture.VoiceTests.transcribe
    fake_engine=fixture.VoiceTests.fake_engine
    prepare=fixture.VoiceTests.prepare
    change=fixture.VoiceTests.change

    def setup_rows(self):
        self.ids=list(self.prepare())
        self.options={'run':'test','revision':0,'start_ms':0,'end_ms':1000}
        self.segment=store.rows(self.path)[0]['id']
        return suggestions.prepare(self.path,self.options)

    def test_selection_limits_and_manual_assignments(self):
        value=self.setup_rows();self.assertEqual([r['id'] for r in value['rows']],[self.segment])
        for options in ({'start_ms':-1},{'revision':False},{'end_ms':300001},{'segment_id':'없는 발언'}):
            with self.assertRaises((ValueError,Conflict)):suggestions.prepare(self.path,self.options|options)
        self.change('assign',segment_id=self.segment,speaker=self.ids[0])
        with self.assertRaisesRegex(ValueError,'수동 배정'):suggestions.prepare(self.path,self.options|{'revision':1})

    def test_references_exclude_selection_overlap_and_prefer_confirmed(self):
        self.setup_rows();a,b=self.ids
        def row(id,speaker,start,end,status='automatic'):
            return {'id':id,'speaker':speaker,'speaker_name':speaker,'start_ms':start,'end_ms':end,'text':id,'status':status,'reason':None}
        rows=[row('target',None,0,1000,'failed'),row('a',a,1000,4000),row('overlap',b,3000,4500),
              row('clean',a,5000,8000,'confirmed'),row('other',b,9000,12000)]
        with patch.object(store,'rows',return_value=rows):
            value=suggestions.prepare(self.path,self.options)
        self.assertEqual({r['source_id'] for r in value['references']},{'clean','other'})

    def test_prompt_validation_rejects_invented_speaker_and_evidence(self):
        value=self.setup_rows();row=value['rows'][0]
        data,text,schema=suggestions.prompt_value(value,row,{'candidates':[{'speaker':self.ids[0],'similarity':.7}]})
        self.assertIn('동일인 확률이 아니며',text)
        raw={'candidate':self.ids[0],'reason':'음향과 앞뒤 발언을 확인해야 합니다.','evidence':[row['id']]}
        suggestions.validate(raw,data)
        for change in ({'candidate':'임의 이름'},{'evidence':['없는 ID']},{'evidence':[]},{'reason':''}):
            with self.assertRaises(ValueError):suggestions.validate(raw|change,data)
        suggestions.validate(raw|{'candidate':'','evidence':[]},data)

    def test_long_or_mixed_rows_defer_and_audio_changes_stale(self):
        value=self.setup_rows();row=value['rows'][0]
        self.assertFalse(suggestions.defer_reason(row))
        self.assertTrue(suggestions.defer_reason(row|{'reason':'mixed'}))
        self.assertTrue(suggestions.defer_reason(row|{'end_ms':10001}))
        self.save_proposal(value)
        source=speech_media.local(self.path,speech_store.state(self.path)['audio']['file'])
        source.write_bytes(source.read_bytes()+b'changed')
        self.assertTrue(suggestions.latest(self.path)['stale'])

    def save_proposal(self,value,id='candidate'):
        r={'id':id,'input':value,'complete':True,'items':[{'id':self.segment,'candidate':self.ids[0]}]}
        save_json(store.local(self.path,f'suggestions/{id}/result.json'),r)
        store.update(self.path,suggestion=id,suggestions=[{'id':id}]);return r

    def test_accept_is_explicit_exact_and_stale_protected(self):
        value=self.setup_rows();r=self.save_proposal(value)
        before={p:p.read_bytes() for p in self.path.rglob('*') if p.is_file() and p.name not in ('state.json','.lock')}
        self.assertFalse(suggestions.latest(self.path)['stale']);self.assertEqual(store.edits(self.path,'test')['assignments'],{})
        args={'suggestion':r['id'],'segment_id':self.segment,'speaker':self.ids[0]}
        with self.assertRaises(ValueError):suggestions.accept(self.path,args|{'speaker':self.ids[1]})
        suggestions.accept(self.path,args)
        self.assertEqual(set(store.edits(self.path,'test')['assignments']),{self.segment})
        self.assertTrue(suggestions.latest(self.path)['stale'])
        with self.assertRaises(Conflict):suggestions.accept(self.path,args)
        self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))

    def run_mock(self,fail=False,cancel=False):
        value=self.setup_rows();before={p:p.read_bytes() for p in self.path.rglob('*') if p.is_file() and p.name not in ('state.json','.lock')}
        def process(args,log,stop,lock):
            req=read_json(Path(args[-1]));save_json(Path(req['output']),{self.segment:{'candidates':[{'speaker':self.ids[0],'similarity':.6,'samples':[]}],'note':'시험 음향 결과'}})
        def infer(data,folder,*args):
            if cancel:job.stop.set();raise Cancelled()
            if fail:raise ValueError('시험 응답 오류')
            return {'candidate':self.ids[0],'reason':'검토용 제안','evidence':[self.segment]},1
        counter=type('Counter',(),{'count':lambda self,text:100})()
        with ProjectLock(self.path) as lock:
            job=voices.VoiceJob(self.path,self.data,lock,'suggest',self.options)
            with patch.object(voice_models,'home',return_value=self.root),patch.object(Path,'is_file',return_value=True),\
                 patch.object(speech_model,'digest',return_value=voice_models.FILES['embedding.onnx'][1]),\
                 patch.object(speech_media,'process',side_effect=process),patch.object(context_job.ContextJob,'check_engine'),\
                 patch.object(context_job.ContextJob,'make_tokenizer',return_value=counter),patch.object(context_job.ContextJob,'infer_value',side_effect=infer):
                job.run()
        self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
        self.assertEqual(store.edits(self.path,'test')['assignments'],{})
        return suggestions.latest(self.path)

    def test_job_preserves_inputs_and_saves_suggestions_only(self):
        result=self.run_mock();self.assertTrue(result['complete']);self.assertEqual(result['items'][0]['candidate'],self.ids[0])
    def test_invalid_context_is_deferred_without_assigning(self):
        result=self.run_mock(fail=True);self.assertTrue(result['complete']);self.assertEqual(result['items'][0]['candidate'],'');self.assertTrue(result['items'][0]['error'])
    def test_cancel_keeps_partial_run(self):
        result=self.run_mock(cancel=True);self.assertFalse(result['complete']);self.assertEqual(store.state(self.path)['state'],'paused')

    def test_original_retranscription_keeps_text_and_global_time(self):
        self.prepare();before={p:p.read_bytes() for p in self.path.rglob('*') if p.is_file() and p.name not in ('state.json','.lock')}
        original_process=speech_media.process
        def process(args,log,stop,lock):
            if '-of' in args:return self.fake_engine(args,log,stop,lock)
            return original_process(args,log,stop,lock)
        with ProjectLock(self.path) as lock:
            job=voices.VoiceJob(self.path,self.data,lock,'retranscribe-original',{'start_ms':1000,'end_ms':2500})
            with patch.object(speech_model,'verify'),patch('archive.voice_retranscription.shutil.which',return_value='test-whisper'),patch.object(speech_media,'process',side_effect=process):job.run()
        result=voice_retranscription.latest(self.path)
        self.assertIsNotNone(result,store.state(self.path));self.assertEqual((result['segments'][0]['start_ms'],result['segments'][0]['end_ms']),(1000,2500))
        self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
        self.assertFalse(result['stale'])

    def test_http_candidate_selection_accept_and_stale(self):
        import json
        from http.client import HTTPConnection
        from urllib.parse import urlsplit
        from archive.jobs import Manager
        from archive.server import make_server
        value=self.setup_rows();self.save_proposal(value)
        manager=Manager(self.root);server,url=make_server(manager)
        thread=threading.Thread(target=server.serve_forever);thread.start();address=urlsplit(url)
        client=HTTPConnection(address.hostname,address.port,timeout=5)
        def post(action,values,status=200):
            client.request('POST',address.path+'api/'+action,json.dumps({'root':str(self.root),'vod_id':'1'}|values),{'Content-Type':'application/json'})
            response=client.getresponse();data=json.loads(response.read());self.assertEqual(response.status,status,data);return data
        try:
            data=post('voices-result',{});self.assertEqual(data['suggestion']['id'],'candidate')
            post('voices-edit',{'action':'select-suggestion','options':{'id':'candidate'}})
            post('voices-edit',{'action':'select-suggestion','options':{'id':'../../bad'}},400)
            options={'suggestion':'candidate','segment_id':self.segment,'speaker':self.ids[0]}
            post('voices-edit',{'action':'accept-suggestion','options':options})
            self.assertTrue(post('voices-result',{})['suggestion']['stale'])
            post('voices-edit',{'action':'accept-suggestion','options':options},409)
        finally:
            client.close();server.shutdown();server.server_close();thread.join();manager.close()


if __name__=='__main__':unittest.main()
