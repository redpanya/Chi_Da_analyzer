"""계층 문맥의 경계·원문 근거·버전 격리·중단 복구 검사."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from archive import context_full as full,context_job as jobs,context_evidence as ev,context_events as events,context_hierarchy as hierarchy
from archive.storage import ProjectLock,read_json,save_json
from archive.source import Cancelled
from test_context_full import source


class HierarchyTests(unittest.TestCase):
    def setUp(self):
        self.version=patch.object(full,'VERSION',5);self.version.start();self.addCleanup(self.version.stop)
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.source=source(10,300000)
        self.source['chat']=[]
        self.inputs=patch('archive.context_input.source',side_effect=lambda *args:copy.deepcopy(self.source));self.inputs.start()
        self.settings=patch('archive.context_events.settings',return_value=events.analysis.settings({}));self.settings.start()
    def tearDown(self):self.inputs.stop();self.settings.stop();self.temp.cleanup()
    def job(self,action='whole'):
        return jobs.ContextJob(self.path,'1',ProjectLock(self.path),action,full.prepare(self.path,'1',action,{}))
    def infer(self,value,folder,prompt,schema):
        props=schema['properties'];ids=[r['id'] for r in value['evidence'] if r['kind']=='speech']
        if 'stories' in props:return {'stories':[{'start':ids[0],'title':'작품 해석','detail':'작품을 설명한다.'},{'start':ids[5],'title':'구매 경험','detail':'구매 비용을 비교한다.'}]},1
        if set(props)=={'decision','reason'}:return {'decision':'keep','reason':'독립된 이야기'},1
        if set(props)=={'decision','reason','title'}:return {'decision':'same','reason':'같은 대상의 감상과 경험','title':'작품 감상과 경험'},1
        if 'decision' in props:return {'decision':'new','start':'S5','title':'구매 경험','detail':'구매 비용을 비교한다.','reason':'별도의 구매 경험이 시작된다.'},1
        return {'title':'이야기 요약','context':[{'text':'구체적인 이야기의 내용을 설명한다.','evidence':[ids[0]]}],
                'chat':[],'relation':[],'uncertainties':[]},1
    def execute(self,job,infer=None):
        with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=infer or self.infer):job.run()
        self.assertNotEqual(jobs.state(self.path)['state'],'error',jobs.state(self.path))
        return jobs.result(self.path,'1')
    def test_hierarchy_preserves_quiet_stories_and_grounded_ranges(self):
        result=self.execute(self.job());self.assertTrue(result['complete']);self.assertEqual(result['version'],5)
        stories=[i for i in result['items'] if i['kind']=='story'];parents=[i for i in result['items'] if i['kind']=='topic']
        self.assertEqual([(s['start_ms'],s['end_ms']) for s in stories],[(0,150000),(150000,300000)])
        self.assertEqual(len(parents),1);self.assertTrue(all(s['parent_id']==parents[0]['id'] for s in stories))
        self.assertEqual(sum(s['input']['stats']['speech_used'] for s in stories),10)
        self.assertFalse(result['stale']);hierarchy.validate(result['items'],300000)
    def test_cancel_reuses_outline_and_summary_without_duplicate_events(self):
        job=self.job();count=0
        def fail(*args):
            nonlocal count
            if 'context' in args[3]['properties']:
                count+=1
                if count==2:job.cancel();raise Cancelled()
            return self.infer(*args)
        partial=self.execute(job,fail);self.assertFalse(partial['complete']);self.assertEqual(partial['done'],1)
        folder=self.path/'context/runs'/partial['id'];before=(folder/'outline.json').read_bytes()
        calls=[]
        def resume(*args):calls.append(args[3]);return self.infer(*args)
        result=self.execute(self.job('resume'),resume);self.assertTrue(result['complete'])
        self.assertEqual(before,(folder/'outline.json').read_bytes());self.assertTrue(all('context' in s['properties'] for s in calls))
        self.assertEqual(len(result['items']),3)
    def test_source_or_pipeline_change_cannot_resume(self):
        job=self.job()
        with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=Cancelled()):job.run()
        id=jobs.state(self.path)['run'];file=self.path/f'context/runs/{id}/result.json';saved=read_json(file)
        save_json(file,saved|{'pipeline_revision':-1})
        with self.assertRaisesRegex(ValueError,'방식'):full.prepare(self.path,'1','resume',{})
        save_json(file,saved);self.source['speech'][0]['text']='새 발언'
        with self.assertRaisesRegex(ValueError,'바뀌어'):full.prepare(self.path,'1','resume',{})
    def test_legacy_resume_forks_and_preserves_all_old_files(self):
        job=self.job();count=0
        def interrupt(*args):
            nonlocal count
            if 'context' in args[3]['properties']:
                count+=1
                if count==2:raise Cancelled()
            return self.infer(*args)
        result=self.execute(job,interrupt);old=result['id'];folder=self.path/'context/runs'/old
        save_json(folder/'result.json',read_json(folder/'result.json')|{'pipeline_revision':4})
        before={str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        calls=[]
        def resume(*args):calls.append(args);return self.infer(*args)
        recovered=self.execute(self.job('resume'),resume)
        self.assertNotEqual(recovered['id'],old);self.assertEqual(recovered['recovered_from'],old)
        self.assertEqual(recovered['pipeline_revision'],5);self.assertTrue(recovered['complete'])
        self.assertEqual(before,{str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*') if p.is_file()})
        self.assertTrue(all('context' in a[3]['properties'] for a in calls))
        self.assertEqual(len(calls),2)

    def test_reaction_failure_keeps_finished_summaries_and_can_retry(self):
        job=self.job();calls=[]
        failed={'id':'reaction-0','kind':'reaction','story_id':None,'parent_id':None,'start_ms':0,'end_ms':1000,
            'relation_status':'failed','summary':{'title':'반응 분석 실패','context':[],'chat':[],'relation':[],'uncertainties':['검토 필요']},
            'input':ev.window(self.source,ev.speech(self.source),0,1000)}
        def inspect(*args,**kwargs):
            current=jobs.result(self.path,'1');calls.append(current['done'])
            self.assertEqual(current['done'],3);self.assertFalse(current['complete'])
            self.assertEqual(len([i for i in current['items'] if i['kind']=='story']),2)
            kwargs['publish']([failed]);return [failed]
        with patch.object(events,'inspect',side_effect=inspect):result=self.execute(job)
        self.assertFalse(result['complete']);self.assertEqual(result['reaction_failures'],1)
        self.assertEqual(jobs.state(self.path)['state'],'review');self.assertEqual(calls,[3])
        with patch.object(events,'inspect',return_value=[]):
            resumed=self.execute(self.job('resume'),lambda *args:self.fail('완료 요약 재생성'))
        self.assertTrue(resumed['complete']);self.assertEqual(resumed['reaction_failures'],0)
    def test_resume_after_timeline_written_does_not_repeat_attached_event(self):
        event={'id':'reaction-0','kind':'moment','story_id':'story-0','parent_id':'topic-0','start_ms':0,'end_ms':150000,
               'relation_status':'linked','summary':{'title':'검증 반응','context':[],'chat':[],'relation':[],'uncertainties':[]},
               'input':ev.window(self.source,ev.speech(self.source),0,150000)}
        job=self.job()
        def stop_before_manifest(file,value):
            if file.name=='result.json' and value.get('complete'):raise OSError('저장 직전 종료')
            save_json(file,value)
        with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=self.infer),patch.object(events,'inspect',return_value=[event]),patch.object(hierarchy,'save_json',side_effect=stop_before_manifest):job.run()
        self.assertEqual(jobs.state(self.path)['state'],'error')
        self.assertEqual(len(jobs.result(self.path,'1')['items'][0]['reactions']),1)
        result=self.execute(self.job('resume'))
        self.assertTrue(result['complete']);self.assertEqual(len(result['items'][0]['reactions']),1)
    def test_passages_retain_ids_and_exclude_review_without_changing_source(self):
        self.source['speech'][1].update(repeat_review=True)
        before=copy.deepcopy(self.source);rows=ev.speech(self.source)
        self.assertNotIn('S1',[r['id'] for r in rows]);self.assertEqual(rows[1]['id'],'S2')
        rows=[{'id':f'S{i}','kind':'speech','start_ms':i*1000,'end_ms':i*1000+900,'text':text,'speaker':'화자인식 실패'} for i,text in enumerate(['친구가','그렇게','당했다면','어떨까'])]
        passages=ev.passages(rows);self.assertEqual(len(passages),1);self.assertEqual(passages[0]['source_ids'],['S0','S1','S2','S3'])
        self.assertEqual(self.source,before)
    def test_invalid_parent_and_missing_evidence_rejected(self):
        result=self.execute(self.job());bad=copy.deepcopy(result['items']);bad[0]['parent_id']='missing'
        with self.assertRaises(ValueError):hierarchy.validate(bad,300000)
        bad=copy.deepcopy(result['items']);bad[0]['summary']['context'][0]['evidence']=['S9999']
        with self.assertRaises(ValueError):hierarchy.validate(bad,300000)
    def test_reaction_peaks_use_all_chat_and_offset_once(self):
        src=source(10,300000);src['chat']=[{'offset_ms':t,'text':'ㅋㅋ','user_id_hash':str(i%3)} for i,t in enumerate([41000,42000,43000,44000,101000,102000,103000,104000])]
        a=events.candidates(src,events.analysis.settings({}));self.assertGreaterEqual(len(a),2)
        src['chat_offset_ms']=2000;b=events.candidates(src,events.analysis.settings({}))
        self.assertEqual([e['peak_ms']+2000 for e in a],[e['peak_ms'] for e in b]);self.assertEqual(a[0]['known_authors'],3)


if __name__=='__main__':unittest.main()
