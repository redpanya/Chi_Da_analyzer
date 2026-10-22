"""실제 저장 형식·HTTP·잠금·리포트 연결을 가상 전사로 검사한다."""
import json
import base64
import io
import zipfile
import threading
import unittest
from unittest.mock import patch
from http.client import HTTPConnection
from types import SimpleNamespace
from urllib.parse import urlsplit

import test_speech
from archive import context_job, reports, speech_store, report_schema
from archive.jobs import Manager
from archive.server import make_server
from archive.storage import ProjectLock, read_json, save_json


class ExchangeHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_speech.SpeechTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.addCleanup(self.fixture.tearDown)
        self.fixture.audio();self.fixture.transcribe()
        self.path=self.fixture.path;self.run=speech_store.manifest(self.path)
        first=speech_store.segments(self.path,self.run)[0]
        speech_store.correct(self.path,self.run['id'],first['id'],'사용자가 교정한 발언')
        self.originals={str(p):p.read_bytes() for p in self.path.rglob('*') if p.is_file()}
        self.manager=Manager(self.fixture.root)
        self.server,url=make_server(self.manager);self.url=urlsplit(url)
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.manager.close()

    def post(self,action,values=None,origin=None):
        body={'root':str(self.fixture.root),'vod_id':'1'}|(values or {})
        client=HTTPConnection(self.url.hostname,self.url.port,timeout=5)
        try:
            client.request('POST',self.url.path+'api/'+action,json.dumps(body),
                {'Content-Type':'application/json','Origin':origin or f'http://{self.url.netloc}'})
            r=client.getresponse();return r.status,json.loads(r.read())
        finally:client.close()

    def prepare(self):
        code,bundle=self.post('context-exchange-create',{'options':{'mode':'timestamps',
            'selection':{'transcript_run':self.run['id'],'speaker_run':None}}})
        self.assertEqual(code,200);self.assertIn('사용자가 교정한 발언',bundle['files'][0]['text'])
        self.assertNotIn(str(self.fixture.root),bundle['files'][0]['text'])
        source=read_json(self.path/'context/exchange'/bundle['id']/'source.json');rows=source['rows']
        reply={'schema_version':1,'export_id':bundle['id'],'chunk_id':'001','mode':'timestamps',
            'coverage':{'first_id':rows[0]['id'],'last_id':rows[-1]['id']},'continues_previous':False,
            'topics':[{'start_id':rows[0]['id'],'title':'일반 기능 검증','evidence_ids':[rows[0]['id']],'review_needed':False}]}
        return reply

    def test_http_roundtrip_large_envelope_lock_origin_and_preservation(self):
        reply=self.prepare();text=json.dumps(reply)+' '*70000
        code,preview=self.post('context-exchange-preview',{'text':text});self.assertEqual(code,200)
        code,_=self.post('context-exchange-preview',{'text':text},'https://example.invalid');self.assertEqual(code,403)
        with ProjectLock(self.path):
            code,_=self.post('context-exchange-receive',{'text':text,'token':preview['token']});self.assertEqual(code,409)
        code,result=self.post('context-exchange-receive',{'text':text,'token':preview['token']});self.assertEqual(code,200)
        code,saved=self.post('context-result',{'run':result['run']});self.assertEqual(code,200)
        self.assertTrue(saved['complete']);self.assertFalse(saved['stale']);self.assertEqual(saved['items'][0]['start_ms'],0)
        code,p=self.post('context-exchange-preview',{'text':text})
        code,again=self.post('context-exchange-receive',{'text':text,'token':p['token']})
        self.assertTrue(again['duplicate']);self.assertEqual(again['run'],result['run'])
        for file,before in self.originals.items():
            from pathlib import Path
            self.assertEqual(Path(file).read_bytes(),before)

    def test_report_reads_quick_input_and_own_run_metrics(self):
        old='a'*32;new='b'*32
        save_json(context_job.local(self.path,'state.json'),{'state':'complete','runs':[],'full_run':old})
        for run,tokens in [(old,999),(new,22)]:save_json(context_job.local(self.path,f'runs/{run}/measurements.json'),{'prompt_tokens':tokens})
        job=SimpleNamespace(input={'saved':{'id':new},'source':{'rows':[{'text':'전사만'}],'chat':[]}})
        value=reports.counts(self.path,'summary',job)
        self.assertEqual(value['prompt_tokens'],22);self.assertEqual(value['summary_input_speech_characters'],3)
        self.assertEqual(value['summary_input_chat_characters'],0)
        from test_automation_reports import HARDWARE
        with patch('archive.report_hardware.collect',return_value=HARDWARE):
            token=self.manager.reports.begin(self.path,'summary',{'summary_mode':'timestamps'})
        saved=self.manager.reports.snapshot(self.fixture.root,'1',token[0])['payload']
        self.assertEqual(saved['stages'][0]['summary_mode'],'timestamps')
        report_schema.validate(saved)

    def test_zip_export_import_http_and_cancel_resume(self):
        reply=self.prepare()
        code,archive=self.post('context-exchange-archive',{'export_id':reply['export_id']});self.assertEqual(code,200)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive['base64']))) as z:self.assertIn('작업서.txt',z.namelist())
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:z.writestr('result.json',json.dumps(reply)+' '*70000)
        payload={'archive':base64.b64encode(buffer.getvalue()).decode()}
        code,p=self.post('context-exchange-check-files',payload);self.assertEqual(code,200);self.assertEqual(p['accepted'],1)
        code,_=self.post('context-exchange-check-files',payload,'https://example.invalid');self.assertEqual(code,403)
        self.post('context-exchange-cancel',{'export_id':reply['export_id']})
        code,_=self.post('context-exchange-check-files',payload);self.assertEqual(code,400)
        code,_=self.post('context-exchange-resume',{'export_id':reply['export_id']});self.assertEqual(code,200)
        code,p=self.post('context-exchange-check-files',payload);self.assertEqual(code,200)
        with ProjectLock(self.path):
            code,_=self.post('context-exchange-import-files',payload|{'token':p['token']});self.assertEqual(code,409)
        code,result=self.post('context-exchange-import-files',payload|{'token':p['token']});self.assertEqual(code,200)
        code,saved=self.post('context-result',{'run':result['run']});self.assertEqual(code,200);self.assertTrue(saved['complete'])
        from pathlib import Path
        for file,before in self.originals.items():self.assertEqual(Path(file).read_bytes(),before)


if __name__=='__main__':unittest.main()
