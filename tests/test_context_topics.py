"""주제 전환 때만 요약·긴 주제 원문 보존·취소/실패 재개·이전 방식 호환."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from archive import context_full as full,context_topics as topics,context_topic_summary as summary,context_job as jobs,context_input as inputs
from archive.source import Cancelled
from archive.storage import ProjectLock,read_json
from test_context_full import source

RAW={'title':'참가 신청','context':'신청 방법과 순서를 안내한다.','chat':'시청자들이 반응한다.','relation':''}


class TopicTests(unittest.TestCase):
    def setUp(self):
        self.version=patch.object(full,'VERSION',4);self.version.start()
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.source=source(12,360000)
        self.patch=patch('archive.context_input.source',side_effect=lambda *args:self.source);self.patch.start()
    def tearDown(self):self.version.stop();self.patch.stop();self.temp.cleanup()
    def job(self,action='whole',id=None):
        prepared=full.prepare(self.path,'1',action,{'run':id} if id else {})
        return jobs.ContextJob(self.path,'1',ProjectLock(self.path),action,prepared)
    def infer(self,value,folder,prompt,schema):
        if 'changes' in schema.get('properties',{}):
            first=next(r for r in value['evidence'] if r['kind']=='speech')
            return ({'changes':[],'opening_topic':'참가 신청'} if 'opening_topic' in schema['properties'] else {'changes':[]}),1
        return RAW,2
    def execute(self,job,infer=None):
        with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=infer or self.infer):job.run()
        return jobs.result(self.path,'1',jobs.state(self.path)['run'])
    def test_same_topic_crosses_chunks_and_only_summarizes_at_eof(self):
        job=self.job();events=[]
        def infer(*args):events.append('검출' if 'changes' in args[3].get('properties',{}) else '요약');return self.infer(*args)
        result=self.execute(job,infer)
        self.assertTrue(result['complete']);self.assertEqual(result['version'],4)
        self.assertEqual(events,['검출','검출','검출','요약'])
        self.assertEqual(len(result['items']),1);self.assertIsNone(result['pending_topic'])
        item=result['items'][0];self.assertEqual((item['start_ms'],item['end_ms']),(0,360000));self.assertEqual(item['input']['stats']['speech_used'],12)
    def test_transition_inside_chunk_closes_previous_and_includes_all_speech_once(self):
        job=self.job()
        def infer(value,folder,prompt,schema):
            raw,seconds=self.infer(value,folder,prompt,schema)
            if 'changes' in raw and value['range']['start_ms']==120000:raw['changes']=[{'start':value['evidence'][2]['id'],'topic':'방송 일정'}]
            return raw,seconds
        result=self.execute(job,infer);self.assertTrue(result['complete'])
        self.assertEqual([(r['start_ms'],r['end_ms']) for r in result['items']],[(0,180000),(180000,360000)])
        speech=[r['start_ms'] for item in result['items'] for r in item['input']['evidence'] if r['kind']=='speech']
        self.assertEqual(speech,[r['start_ms'] for r in self.source['speech']])
    def test_pause_keeps_open_topic_without_premature_summary(self):
        job=self.job();calls=[]
        def infer(*args):
            calls.append(1)
            if len(calls)==2:job.cancel()
            return self.infer(*args)
        partial=self.execute(job,infer);id=partial['id']
        self.assertEqual(partial['items'],[]);self.assertEqual(partial['pending_topic']['start_ms'],0);self.assertEqual(partial['done'],1)
        before=(self.path/f'context/runs/{id}/chunk-0.json').read_bytes()
        result=self.execute(self.job('resume',id));self.assertTrue(result['complete']);self.assertEqual(len(result['items']),1)
        self.assertEqual(before,(self.path/f'context/runs/{id}/chunk-0.json').read_bytes())
    def test_failed_summary_reuses_detection_and_successful_partial_summary(self):
        self.source=source(30,900000)
        for r in self.source['speech']:r['text']='신청 방법과 참가 자격을 자세히 안내한다. '*12
        job=self.job();summaries=[]
        def fail(value,folder,prompt,schema):
            if 'changes' not in schema.get('properties',{}):
                summaries.append(1)
                if len(summaries)==2:raise ValueError('통합 시험 오류')
            return self.infer(value,folder,prompt,schema)
        partial=self.execute(job,fail);self.assertFalse(partial['complete']);self.assertIsNotNone(partial['pending_topic']);self.assertEqual(jobs.state(self.path)['state'],'error')
        first=list((self.path/f"context/runs/{partial['id']}/topics").glob('*/part-0.json'))[0];before=first.read_bytes()
        calls=[]
        def resumed(*args):calls.append(args[3]);return self.infer(*args)
        result=self.execute(self.job('resume',partial['id']),resumed)
        self.assertTrue(result['complete']);self.assertEqual(len(result['items']),1);self.assertEqual(first.read_bytes(),before)
        self.assertFalse(any('changes' in s.get('properties',{}) for s in calls))
        self.assertEqual(result['items'][0]['input']['stats']['speech_used'],30)
    def test_invalid_boundaries_and_initial_topic_rejected(self):
        value=inputs.window(self.source,full.plan(self.source)[0]['range'],whole=True)
        for changes in ([{'start':'없는발언','topic':'주제'}],[{'start':'S1','topic':'주제'}],[{'start':'S2','topic':'주제'},{'start':'S2','topic':'중복'}],[{'start':'S2','topic':' '}],[{'start':'S2','topic':12}]):
            with self.assertRaises(ValueError):topics.validate({'opening_topic':'첫 주제','changes':changes},value,None)
        with self.assertRaises(ValueError):topics.validate({'changes':[]},value,None)
        self.assertEqual(topics.validate({'opening_topic':'첫 주제','changes':[]},value,None),[{'start_ms':0,'topic':'첫 주제'}])
        self.assertEqual(topics.validate({'changes':[]},value,{'start_ms':0}),[])
    def test_gap_does_not_force_new_topic_and_missing_speech_not_invented(self):
        self.source['speech']=[self.source['speech'][0],self.source['speech'][-1]]
        result=self.execute(self.job());self.assertTrue(result['complete']);self.assertEqual(len(result['items']),1)
        self.source['speech'][0]['encoding_review']=True;self.source['speech'][-1]['encoding_review']=True
        result=self.execute(self.job());self.assertTrue(result['complete']);self.assertTrue(all(r['gap'] for r in result['items']))
    def test_input_change_blocks_resume_and_old_results_are_retained(self):
        job=self.job()
        def fail(*args):raise Cancelled()
        partial=self.execute(job,fail)
        self.source['speech'][0]['text']='사용자 수정'
        with self.assertRaisesRegex(ValueError,'바뀌어'):full.prepare(self.path,'1','resume',{'run':partial['id']})
        self.assertTrue((self.path/f"context/runs/{partial['id']}/result.json").exists())

