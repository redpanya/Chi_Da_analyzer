"""전체 범위·AI 문맥 경계·체크포인트·입력 변경·구버전 보존."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from archive import context_full as full, context_input as inputs, context_job as jobs
from archive.storage import ProjectLock,save_json,read_json


def source(count=8,duration=300000):
    return {'duration_ms':duration,'chat_offset_ms':0,'notes':['전체 제공 채팅'],
            'speech':[{'start_ms':i*30000,'end_ms':i*30000+10000,'text':f'주제 {i}의 발언입니다.','speaker_name':'시험 화자'} for i in range(count)],
            'chat':[{'offset_ms':i*30000+1000,'text':'ㅋㅋ' if i%2 else '반응입니다'} for i in range(count)]}

def output(value,split=False):
    rows=[r for r in value['evidence'] if r['kind']=='speech']
    summary={'title':'대화 주제','context':'대화 내용을 정리한다.','chat':'','relation':''}
    return {'opening':summary,'changes':[{'start':rows[1]['id'],'summary':summary}] if split else []}

class FullTests(unittest.TestCase):
    def setUp(self):
        self.version=patch.object(full,'VERSION',3);self.version.start()
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.source=source()
        self.patch=patch('archive.context_input.source',side_effect=lambda *args:self.source);self.patch.start();self.merge=patch('archive.context_merge.merge_pair',return_value=(None,0));self.merge.start()
    def tearDown(self):self.version.stop();self.patch.stop();self.merge.stop();self.temp.cleanup()
    def job(self,action='whole',options=None):
        value=full.prepare(self.path,'1',action,options or {})
        return jobs.ContextJob(self.path,'1',ProjectLock(self.path),action,value)
    def test_entire_range_partition_speech_once_and_gaps(self):
        plan=full.plan(self.source)
        self.assertEqual(plan[0]['range']['start_ms'],0);self.assertEqual(plan[-1]['range']['end_ms'],300000)
        self.assertEqual([r['range']['start_ms'] for r in plan[1:]],[r['range']['end_ms'] for r in plan[:-1]])
        count=sum(inputs.window(self.source,r['range'],whole=True)['stats']['speech_used'] for r in plan)
        self.assertEqual(count,8)
        self.assertEqual(inputs.window(self.source,plan[-1]['range'],whole=True)['stats']['speech_used'],0)
        self.source['speech'][3]['end_ms']=125000
        plan=full.plan(self.source);self.assertEqual(plan[0]['range']['end_ms'],130000)
    def test_adaptive_input_does_not_sample_speech_and_bounds(self):
        self.source=source(100,3000000)
        for row in self.source['speech']:row['text']='매우 긴 발언 '*200
        plan=full.plan(self.source)
        self.assertEqual(sum(inputs.window(self.source,c['range'],whole=True)['stats']['speech_used'] for c in plan),100)
        self.source['speech'][0]['text']='가'*10000
        with self.assertRaises(ValueError):full.plan(self.source)
        with self.assertRaises(ValueError):full.prepare(self.path,'1','whole',{'start_ms':1000})
        with self.assertRaises(ValueError):inputs.explore.options(chat_offset_ms=True)
    def test_encoding_error_excluded_until_user_correction(self):
        self.source['speech'][1].update(text='[문자 인식 오류 · 원음 확인 필요]', encoding_review=True)
        args=inputs.options(0,300000)
        for whole in (False,True):
            value=inputs.window(self.source,args,whole=whole)
            self.assertEqual(value['stats']['speech_used'],7)
            self.assertFalse(any(r['id']=='S2' for r in value['evidence']))
            self.assertTrue(any('문자 인식 오류' in note for note in value['notes']))
        self.source['speech'][1].update(text='사용자가 원음으로 확인한 발언', corrected=True)
        value=inputs.window(self.source,args,whole=True)
        self.assertEqual(value['stats']['speech_used'],8)
        self.assertTrue(any(r['id']=='S2' and r['text']=='사용자가 원음으로 확인한 발언' for r in value['evidence']))
        self.source['speech']=[self.source['speech'][1] | {'corrected':False}]
        with self.assertRaisesRegex(ValueError,'문자 인식 오류'):inputs.window(self.source,args)
        self.assertFalse(any(r['kind']=='speech' for r in inputs.window(self.source,args,whole=True)['evidence']))

    def test_topic_coverage_and_evidence_validation(self):
        value=inputs.window(self.source,full.plan(self.source)[0]['range'],whole=True)
        valid=output(value,True);items=full.validate(valid,value)
        self.assertLessEqual(items[0]['end_ms'],items[1]['start_ms'])
        for mutate in [lambda v:v['changes'][0].update(start='S1'),lambda v:v['changes'][0].update(start='없는발언'),lambda v:v['changes'].append(v['changes'][0]),lambda v:v['opening'].update(context=None)]:
            bad=json.loads(json.dumps(valid));mutate(bad)
            with self.assertRaises(ValueError):full.validate(bad,value)
        self.assertIn('구체적 주제가 바뀌는',full.prompt(value))
        self.assertTrue(all(i['range_sources'] for i in items))
        self.assertEqual(items[-1]['end_ms'],value['evidence'][3]['end_ms'])
    def test_cancel_restart_resume_and_old_version_unchanged(self):
        old={'id':'a'*32,'label':'이전 구간','title':'보존'}
        save_json(jobs.local(self.path,'state.json'),{'state':'complete','run':old['id'],'runs':[old]})
        save_json(jobs.local(self.path,f"runs/{old['id']}/result.json"),{'old':True})
        before=jobs.local(self.path,f"runs/{old['id']}/result.json").read_bytes()
        job=self.job();calls=[]
        def infer(value,*args):
            calls.append(value['label'])
            if len(calls)==2:job.cancel()
            return output(value,True),1
        with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=infer):job.run()
        self.assertEqual(jobs.state(self.path)['state'],'paused')
        id=jobs.state(self.path)['full_run'];partial=jobs.result(self.path,'1',id)
        self.assertEqual(partial['done'],1);self.assertFalse(partial['complete'])
        stored=read_json(jobs.local(self.path,f'runs/{id}/result.json'));first=jobs.local(self.path,f"runs/{id}/{stored['chunks'][0]['file']}").read_bytes()
        # 상태 파일에 비정상 종료가 남아도 새 작업은 완료 조각을 재사용한다.
        state=jobs.state(self.path);state['state']='running';save_json(jobs.local(self.path,'state.json'),state)
        self.assertEqual(jobs.view(self.path)['state'],'paused')
        resumed=self.job('resume',{'run':id});calls.clear()
        with patch.object(resumed,'check_engine'),patch.object(resumed,'infer_value',side_effect=lambda value,*args:(calls.append(value['label']) or output(value),1)):resumed.run()
        result=jobs.result(self.path,'1',id)
        self.assertTrue(result['complete']);self.assertEqual(result['done'],3);self.assertEqual(len(calls),1)
        self.assertEqual(first,jobs.local(self.path,f"runs/{id}/{stored['chunks'][0]['file']}").read_bytes())
        self.assertEqual(before,jobs.local(self.path,f"runs/{old['id']}/result.json").read_bytes())
        self.assertEqual([r['start_ms'] for r in result['items']],sorted(r['start_ms'] for r in result['items']))
    def test_reaction_changes_do_not_invalidate_independent_context(self):
        first=full.prepare(self.path,'1','whole',{})['fingerprint']
        self.source['notes'].append('반응: 지난 채팅 입력의 분석 결과')
        self.assertEqual(first,full.prepare(self.path,'1','whole',{})['fingerprint'])
    def test_failure_keeps_checkpoints_and_source_change_blocks_resume(self):
        job=self.job();calls=[]
        def infer(value,*args):
            calls.append(1)
            if len(calls)>1:raise ValueError('모델 오류')
            return output(value),1
        with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=infer):job.run()
        id=jobs.state(self.path)['run'];self.assertEqual(jobs.state(self.path)['state'],'error')
        self.assertEqual(jobs.result(self.path,'1',id)['done'],1)
        self.source['speech'][0]['speaker_name']='바뀐 이름'
        self.assertTrue(jobs.result(self.path,'1',id)['stale'])
        with self.assertRaisesRegex(ValueError,'바뀌어'):self.job('resume',{'run':id})
