"""특정 방송과 무관한 외부 클립 후보·파일 경계·원본 보존 계약."""
import base64
import copy
import io
import json
import unittest
import zipfile
from unittest.mock import patch
import test_context_exchange
from test_context_exchange_zip import zipped
from archive import context_clips as clips, context_exchange as exchange, context_exchange_data as data
from archive import context_exchange_batch as batch, context_exchange_zip as zipper, context_job
from archive.storage import read_json


class ClipTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_context_exchange.ExchangeTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.path=self.fixture.path;self.bundle=self.fixture.create('clips',True)
        self.saved=read_json(exchange.folder(self.path,self.bundle['id'])/'manifest.json')
        self.source=read_json(exchange.folder(self.path,self.bundle['id'])/'source.json')
        self.entries=[content['output_example'] for _,content in exchange.documents(self.saved,self.source)]

    def receive(self,entries):return self.fixture.receive(entries)

    def test_zip_contract_adjacent_context_and_no_extra_private_data(self):
        packed=zipper.pack(self.path,self.bundle['id'])
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(packed['base64']))) as z:
            order=z.read('작업서.txt').decode();self.assertIn('클립 후보 찾기',order);self.assertIn('clips=[]',order)
            for chunk,doc in exchange.documents(self.saved,self.source):
                ids={r['id'] for r in doc['previous_reference']+doc['utterances']+doc['following_reference']}
                self.assertEqual(ids,{r['id'] for r in clips.window(self.source,self.saved['chunks'],chunk)})
                text=json.dumps(doc,ensure_ascii=False);self.assertNotIn('로컬 실명',text);self.assertNotIn('source_id',text)
                self.assertNotIn('continues_previous',doc['output_example']);self.assertNotIn('topics',doc['output_example'])

    def test_cross_chunk_clip_uses_source_times_and_separate_version(self):
        entry=copy.deepcopy(self.entries[1]);chunk=self.saved['chunks'][1]
        rows=clips.window(self.source,self.saved['chunks'],chunk);peak=self.source['rows'][chunk['first']]
        candidate=clips.example(peak)|{'start_id':rows[0]['id'],'end_id':rows[-1]['id'],
            'evidence_ids':[rows[0]['id'],peak['id'],rows[-1]['id']],
            'chat_summary':'시청자가 웃음을 보인다.','chat_evidence_ids':[self.source['chat'][chunk['chat_first']]['id']]}
        entry['clips']=[candidate];result=self.receive([entry]);value=context_job.result(self.path,'1',result['run'])
        item=value['items'][0]
        self.assertEqual((item['start_ms'],item['peak_ms'],item['end_ms']),(rows[0]['start_ms'],peak['start_ms'],rows[-1]['end_ms']))
        self.assertEqual(value['mode'],'clips');self.assertEqual(value['phase'],'clips');self.assertFalse(value['complete']);self.assertFalse(value['stale'])
        self.assertTrue(item['chat_evidence']);self.assertTrue(item['evidence'])
        state=context_job.state(self.path);self.assertEqual(state['run'],'b'*32);self.assertEqual(state['clip_run'],result['run'])
        self.assertEqual(self.fixture.old.read_bytes(),self.fixture.before)

    def test_partial_zip_bad_item_later_recovery_and_empty_candidates(self):
        bad=copy.deepcopy(self.entries[1]);bad['clips'][0]['peak_id']='C0'
        payload={'archive':zipped([('good.json',json.dumps(self.entries[0])),('bad.json',json.dumps(bad))])}
        p=batch.preview(self.path,'1',payload);self.assertEqual(p['accepted'],1);self.assertEqual(len(p['errors']),1)
        self.assertEqual(p['mode'],'clips');self.assertEqual(p['topics'],[]);self.assertTrue(p['clips'][0]['video_checks'])
        with self.assertRaisesRegex(ValueError,'부분 저장'):batch.receive(self.path,'1',payload|{'token':p['token']})
        first=batch.receive(self.path,'1',payload|{'token':p['token'],'allow_partial':True})
        old=self.path/'context/runs'/first['run']/'work.json';before=old.read_bytes()
        remaining=[e|{'clips':[]} for e in self.entries[1:]]
        final=self.receive(remaining);value=context_job.result(self.path,'1',final['run'])
        self.assertTrue(value['complete']);self.assertEqual(len(value['items']),1);self.assertEqual(old.read_bytes(),before)
        self.assertTrue(self.receive(remaining)['duplicate'])
        empty=self.receive([e|{'clips':[]} for e in self.entries]);value=context_job.result(self.path,'1',empty['run'])
        self.assertTrue(value['complete']);self.assertEqual(value['items'],[])

    def test_wrong_ids_ranges_fields_ownership_and_evidence_are_rejected(self):
        entry=copy.deepcopy(self.entries[1]);part=entry['clips'][0]
        changes=[{'start_id':'made-up'},{'peak_id':'S0'},{'end_id':'S0'},{'title':''},
                 {'reason':4},{'video_checks':[]},{'review_needed':'true'},{'uncertainties':['발화 확인 필요']},
                 {'evidence_ids':['C0']},{'chat_summary':'없는 반응'},{'chat_evidence_ids':['C0'],'chat_summary':'다른 시각 반응'},
                 {'start_ms':0},{'end_id':[]},{'evidence_ids':[{}]},{'video_checks':['x'*501]}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):
                exchange.preview(self.path,'1',json.dumps(entry|{'clips':[part|change]}))
        for changed in [entry|{'mode':'detail'},entry|{'topics':[]},entry|{'clips':[part,part]}]:
            with self.assertRaises(ValueError):exchange.preview(self.path,'1',json.dumps(changed))
        self.fixture.source['rows'][0]['text']='수동 교정 변경'
        with self.assertRaisesRegex(ValueError,'입력'):exchange.preview(self.path,'1',json.dumps(entry))

    def test_long_video_same_time_overlap_and_chronological_order(self):
        for row in self.fixture.source['rows']:
            row['start_ms']+=18*3600000;row['end_ms']+=18*3600000
        self.fixture.source['rows'][1]['start_ms']=self.fixture.source['rows'][0]['start_ms']
        self.fixture.source['duration_ms']=20*3600000
        with patch.object(exchange,'PACKET_BYTES',100000):
            bundle=exchange.create(self.path,'1',{'selection':self.source['input_selection'],'mode':'clips'})
        saved=read_json(exchange.folder(self.path,bundle['id'])/'manifest.json')
        source=read_json(exchange.folder(self.path,bundle['id'])/'source.json')
        _,doc=next(exchange.documents(saved,source));entry=doc['output_example']
        entry['clips']=[clips.example(source['rows'][4]),clips.example(source['rows'][1]),clips.example(source['rows'][0])]
        result=self.receive([entry]);items=context_job.result(self.path,'1',result['run'])['items']
        self.assertEqual([i['start_id'] for i in items],['S0','S1','S4'])
        self.assertEqual(items[0]['start_ms'],18*3600000)


if __name__=='__main__':unittest.main()
