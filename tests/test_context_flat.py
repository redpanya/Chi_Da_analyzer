"""단일 문맥·부분 실패·이어하기·취소·실제 실행 오류의 분리."""
import copy,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from archive import context_full as full,context_job as jobs,context_flat_model as model,analysis
from archive.storage import ProjectLock,read_json,save_json
from test_context_full import source

SUMMARY={'title':'신청 규칙','context':'신청 순서와 이용 규칙을 설명한다.','chat':''}

class FlatTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name);self.source=source(12,360000);self.calls=[]
        for p in [patch.object(full,'VERSION',6),patch('archive.context_input.source',side_effect=lambda *a:copy.deepcopy(self.source)),
                  patch('archive.context_events.settings',return_value=analysis.settings({}))]:
            p.start();self.addCleanup(p.stop)
    def job(self,action='whole'):
        return jobs.ContextJob(self.path,'1',ProjectLock(self.path),action,full.prepare(self.path,'1',action,{}))
    def infer(self,value,folder,prompt,schema):
        self.calls.append(folder.name)
        if folder.name.startswith('join-'):return {'merge':True,'summary':dict(SUMMARY)},1
        return {'opening':dict(SUMMARY),'changes':[]},1
    def execute(self,job,infer=None):
        with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=infer or self.infer):job.run()
        return jobs.result(self.path,'1')
    def test_same_story_merges_and_preserves_original_versions(self):
        old=self.path/'context/runs'/('a'*32)/'result.json';save_json(old,{'version':5,'complete':False})
        save_json(self.path/'context/state.json',{'state':'paused','runs':[{'id':'a'*32,'scope':'full'}]})
        before=old.read_bytes();result=self.execute(self.job())
        self.assertTrue(result['complete']);self.assertEqual(result['version'],6);self.assertEqual(len(result['items']),1)
        self.assertEqual((result['items'][0]['start_ms'],result['items'][0]['end_ms']),(0,340000))
        self.assertNotIn('parent_id',result['items'][0]);self.assertEqual(result['items'][0]['summary']['relation'],[])
        self.assertIn('reaction_analysis',result);self.assertEqual(old.read_bytes(),before)
    def test_summary_failure_continues_and_resume_only_retries_failed_part(self):
        def bad(*args):
            if args[1].name.startswith('flat-1-'):self.calls.append(args[1].name);return {'opening':{'title':'잘못된 응답'},'changes':[]},1
            return self.infer(*args)
        result=self.execute(self.job(),bad)
        self.assertEqual(jobs.state(self.path)['state'],'review');self.assertEqual(result['done'],3)
        self.assertEqual([bool(r.get('failed')) for r in result['items']],[False,True,False]);self.assertEqual(result['item_failures'],1)
        folder=self.path/'context/runs'/result['id'];checkpoint=folder/'flat-0.json';before=checkpoint.read_bytes()
        self.calls.clear();result=self.execute(self.job('resume'))
        self.assertTrue(result['complete']);self.assertEqual(result['item_failures'],0)
        self.assertEqual(sum(n.startswith('flat-') for n in self.calls),1);self.assertEqual(checkpoint.read_bytes(),before)
    def test_boundary_failure_keeps_both_summaries_and_retries(self):
        def bad(*args):
            if args[1].name.startswith('join-'):return {'merge':False,'summary':dict(SUMMARY)},1
            return self.infer(*args)
        result=self.execute(self.job(),bad)
        self.assertEqual(result['done'],3);self.assertEqual(len(result['items']),3);self.assertEqual(result['boundary_failures'],2)
        self.calls.clear();result=self.execute(self.job('resume'))
        self.assertTrue(result['complete']);self.assertTrue(all(n.startswith('join-') for n in self.calls))
    def test_engine_error_stops_without_being_marked_response_failure(self):
        def broken(*args):
            if args[1].name.startswith('flat-1-'):raise ValueError('로컬 요약 엔진 오류')
            return self.infer(*args)
        result=self.execute(self.job(),broken)
        self.assertEqual(jobs.state(self.path)['state'],'error');self.assertEqual(result['done'],1)
        self.assertEqual(result['item_failures'],0)
    def test_cancel_and_input_change(self):
        job=self.job()
        def cancel(*args):
            if args[1].name.startswith('flat-1-'):job.cancel()
            return self.infer(*args)
        result=self.execute(job,cancel)
        self.assertEqual(jobs.state(self.path)['state'],'paused');self.assertEqual(result['done'],1)
        self.calls.clear();result=self.execute(self.job('resume'));self.assertTrue(result['complete'])
        self.assertFalse(any(n.startswith('flat-0-') for n in self.calls))
        self.source['speech'][0]['text']='교정된 발언'
        self.assertTrue(jobs.result(self.path,'1')['stale'])
    def test_new_topic_and_gap_and_no_chat(self):
        self.source['chat']=[];self.source['speech']=self.source['speech'][:8]
        def separate(*args):
            if args[1].name.startswith('join-'):return {'merge':False,'summary':None},1
            return self.infer(*args)
        result=self.execute(self.job(),separate)
        self.assertTrue(result['complete']);self.assertEqual(len(result['items']),3);self.assertTrue(result['items'][-1]['gap'])
        self.assertEqual(result['items'][0]['summary']['chat'],[])
    def test_fake_boundary_id_rejected(self):
        value=full.inputs.window(self.source,full.plan(self.source)[0]['range'],whole=True)
        raw={'opening':SUMMARY,'changes':[{'start':'없는발언','summary':SUMMARY}]}
        with self.assertRaises(ValueError):model.convert(raw,value)
    def test_cancel_during_retry_keeps_existing_later_summaries(self):
        def bad(*args):
            if args[1].name.startswith('flat-1-'):return {},1
            return self.infer(*args)
        first=self.execute(self.job(),bad)
        resumed=self.job('resume')
        def cancel(*args):
            if args[1].name.startswith('join-'):resumed.cancel()
            return self.infer(*args)
        partial=self.execute(resumed,cancel)
        self.assertEqual(jobs.state(self.path)['state'],'paused')
        self.assertEqual(partial['done'],first['done']);self.assertEqual(partial['items'],first['items'])
        self.calls.clear();result=self.execute(self.job('resume'));self.assertTrue(result['complete'])
        self.assertFalse(any(n.startswith('flat-') for n in self.calls))

