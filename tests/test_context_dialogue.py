"""대사 중심 입력의 범위 소유·부분 실패·복구·독립 채팅·호환성 계약."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from archive import context_full as full,context_job as jobs,context_dialogue as dialogue
from archive import context_dialogue_input as di,context_dialogue_model as dm,context_tokens as tokens,analysis
from archive.storage import ProjectLock,read_json
from test_context_full import source

class FakeTokenizer:
    seconds=0
    def __init__(self,*args):pass
    def count(self,text):return len(text)//3

class DialogueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name);self.source=source(9,270000);self.calls=[]
        for p in [patch.object(full,'VERSION',7),patch.object(full,'current_source',side_effect=lambda *a:copy.deepcopy(self.source)),
                  patch('archive.context_events.settings',return_value=analysis.settings({})),
                  patch.object(tokens,'Tokenizer',FakeTokenizer),patch.object(tokens,'fit',side_effect=lambda rows,*a:rows[:3])]:
            p.start();self.addCleanup(p.stop)
    def job(self,action='whole',options=None):
        return jobs.ContextJob(self.path,'1',ProjectLock(self.path),action,full.prepare(self.path,'1',action,options or {}))
    def infer(self,value,folder,*args):
        self.calls.append(folder.name)
        folder.mkdir(parents=True)
        if 'items' in value:return {'items':[{'id':r['id'],'chat':'웃음 표현이 관측된다.','relation':''} for r in value['items']]},1
        rows=value['rows']
        return {'continues':bool(value['active']),'topics':[{'start_id':rows[0]['id'],'end_id':rows[-1]['id'],'title':'이어지는 이야기','context':'준비 사항과 규칙을 설명한다.'}]},1
    def execute(self,job,infer=None):
        with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=infer or self.infer):job.run()
        return jobs.result(self.path,'1')
    def test_same_story_across_batches_and_id_coverage(self):
        result=self.execute(self.job())
        self.assertTrue(result['complete'],jobs.state(self.path));self.assertEqual(result['version'],7)
        items=[r for r in result['items'] if not r.get('gap')]
        self.assertEqual(len(items),1);self.assertEqual((items[0]['start_id'],items[0]['end_id']),('S0','S8'))
        self.assertEqual(len([r for r in items[0]['input']['evidence'] if r['kind']=='speech']),9)
        self.assertEqual(sum(r.get('count',0) for r in items[0]['input']['evidence']),9)
        self.assertEqual(items[0]['chat_state'],'complete');self.assertEqual(result['done'],9)
        self.assertEqual(sum(s.startswith('dialogue-') for s in self.calls),3)
        self.assertEqual(sum(s.startswith('chat-') for s in self.calls),1)
    def test_topic_changes_inside_one_batch(self):
        def split(value,folder,*args):
            if 'items' in value:return self.infer(value,folder,*args)
            folder.mkdir(parents=True)
            return {'continues':False,'topics':[{'start_id':r['id'],'end_id':r['id'],'title':'주제 '+r['id'],'context':'서로 다른 내용을 설명한다.'} for r in value['rows']]},1
        result=self.execute(self.job(),split)
        self.assertTrue(result['complete']);self.assertEqual(len([r for r in result['items'] if not r.get('gap')]),9)
    def test_failure_isolated_and_recovery_forks_preserving_old(self):
        def bad(value,folder,*args):
            if 'rows' in value and value['rows'][0]['id']=='S3':folder.mkdir(parents=True);return {},1
            return self.infer(value,folder,*args)
        result=self.execute(self.job(),bad);self.assertFalse(result['complete']);self.assertEqual(result['done'],9)
        self.assertEqual(result['item_failures'],1)
        old=result['id'];file=self.path/'context/runs'/old/'dialogue-state.json';before=file.read_bytes()
        self.calls.clear();recovered=self.execute(self.job('resume'))
        self.assertTrue(recovered['complete'],jobs.state(self.path));self.assertNotEqual(old,recovered['id'])
        self.assertEqual(before,file.read_bytes());self.assertEqual(recovered['recovered_from'],old)
    def test_cancel_resume_keeps_checkpoint_and_source_change_blocks(self):
        job=self.job();count=[0]
        def cancel(*args):
            count[0]+=1
            if count[0]==2:job.cancel()
            return self.infer(*args)
        result=self.execute(job,cancel)
        self.assertEqual(jobs.state(self.path)['state'],'paused');self.assertEqual(result['done'],3)
        self.assertTrue(result['pending_topic']['provisional'])
        self.calls.clear();resumed=self.execute(self.job('resume'));self.assertTrue(resumed['complete'])
        self.assertEqual(sum(s.startswith('dialogue-') for s in self.calls),2)
        self.source['speech'][0]['text']='바뀐 내용'
        self.assertTrue(jobs.result(self.path,'1')['stale'])
    def test_chat_failure_keeps_dialogue_and_retries_without_dialogue(self):
        def bad(value,folder,*args):
            if 'items' in value:folder.mkdir(parents=True);return {'items':[]},1
            return self.infer(value,folder,*args)
        result=self.execute(self.job(),bad);self.assertEqual(result['chat_failures'],1)
        self.assertEqual(result['item_failures'],0);self.assertFalse(result['complete'])
        self.calls.clear();result=self.execute(self.job('resume'));self.assertTrue(result['complete'])
        self.assertFalse(any(s.startswith('dialogue-') for s in self.calls))
    def test_partial_invalid_title_is_not_cached_as_success(self):
        def partial(value,folder,*args):
            if 'items' in value:return self.infer(value,folder,*args)
            folder.mkdir(parents=True)
            rows=value['rows'];a=rows[0]
            return {'continues':False,'topics':[{'start_id':a['id'],'end_id':a['id'],'title':'유효 요약','context':'유효한 내용이다.'},
                {'start_id':rows[1]['id'],'end_id':rows[-1]['id'],'title':'','context':'본문이다.'}]},1
        result=self.execute(self.job(),partial)
        self.assertEqual(result['item_failures'],3);self.assertEqual(sum(not r.get('failed') for r in result['items']),3)
        self.assertTrue(self.execute(self.job('resume'))['complete'])
    def test_chat_absent_and_review_exclusion(self):
        self.source['chat']=[];self.source['speech'][1]['encoding_review']=True
        result=self.execute(self.job());self.assertTrue(result['complete']);self.assertEqual(result['done'],8)
        self.assertFalse(any(s.startswith('chat-') for s in self.calls))
    def test_model_choice_pinned_and_invalid_choice(self):
        with self.assertRaises(ValueError):full.prepare(self.path,'1','whole',{'model':'../임의파일'})
        job=self.job(options={'model':'Qwen3.5-4B-Q4_K_M'})
        result=self.execute(job);self.assertEqual(result['model'],'Qwen3.5-4B-Q4_K_M')
        self.assertEqual(full.prepare(self.path,'1','whole',{'method':'legacy'})['version'],6)
        with self.assertRaises(ValueError):full.prepare(self.path,'1','whole',{'method':'legacy','model':'Qwen3.5-4B-Q4_K_M'})
    def test_id_boundary_validation_and_metadata_removed(self):
        rows=di.rows(self.source);text=dm.dialogue_prompt(rows,None)
        self.assertNotIn('start_ms',text);self.assertNotIn('end_ms',text);self.assertNotIn('text_review',text)
        self.assertEqual(dm.dialogue_schema(rows)['properties']['continues']['enum'],[False])
        self.assertNotIn('enum',dm.dialogue_schema(rows,{'id':'앞문맥'})['properties']['continues'])
        raw={'continues':False,'topics':[{'start_id':'S0','end_id':'S8','title':'제목','context':'본문'}]}
        self.assertTrue(dm.validate_dialogue(raw,rows,None))
        for change in [{'start_id':'S1'},{'end_id':'없는ID'},{'end_id':'S7'}]:
            invalid=copy.deepcopy(raw);invalid['topics'][0].update(change)
            with self.assertRaises(ValueError):dm.validate_dialogue(invalid,rows,None)
    def test_token_fit_uses_whole_prompt_and_long_speech_ids(self):
        self.source['speech'][0]['text']='긴 발언입니다.'*400
        rows=di.rows(self.source)
        fragments=[r for r in rows if r['source_id']=='0']
        self.assertGreater(len(fragments),1);self.assertEqual(''.join(r['text'] for r in fragments),self.source['speech'][0]['text'])
        self.assertEqual(len({r['id'] for r in rows}),len(rows))
    def test_chat_stage_cancel_resume_preserves_finalized_dialogue(self):
        job=self.job();old=[]
        def cancel(value,folder,*args):
            if 'items' in value:
                old.extend(copy.deepcopy(value['items']));job.cancel()
            return self.infer(value,folder,*args)
        result=self.execute(job,cancel)
        self.assertEqual(jobs.state(self.path)['state'],'paused');self.assertIsNone(result['pending_topic'])
        self.assertEqual(result['items'][0]['chat_state'],'pending')
        self.calls.clear();final=self.execute(self.job('resume'))
        self.assertTrue(final['complete']);self.assertFalse(any(s.startswith('dialogue-') for s in self.calls))
        for key in ('id','start_ms','end_ms'):self.assertEqual(result['items'][0][key],final['items'][0][key])
        self.assertEqual(result['items'][0]['summary']['context'],final['items'][0]['summary']['context'])
    def test_all_excluded_keeps_chat_observation_without_dialogue(self):
        for row in self.source['speech']:row['encoding_review']=True
        result=self.execute(self.job());self.assertTrue(result['complete'],jobs.state(self.path))
        self.assertEqual(result['done'],0);self.assertTrue(result['items'][0]['gap'])
        self.assertEqual(result['items'][0]['summary']['context'],[])
        self.assertTrue(result['items'][0]['summary']['chat'])
    def test_overlapping_time_keeps_source_but_blocks_invalid_clip(self):
        rows=di.rows(self.source);item=di.card(self.source,rows[:2],'제목','요약이다.')
        original=item['input']['evidence'][1]['end_ms']
        di.close(item,{'start_ms':40000})
        self.assertEqual(item['end_ms'],40000);self.assertEqual(item['input']['evidence'][1]['end_ms'],original)
        item=di.card(self.source,rows[:1],'제목','요약이다.');di.close(item,{'start_ms':0})
        self.assertTrue(item['time_review'])
    def test_engine_failures_have_finite_retries_and_keep_ranges(self):
        def broken(*args):raise jobs.EngineError('시험 엔진 실패')
        job=self.job();result=self.execute(job,broken)
        self.assertEqual(jobs.state(self.path)['state'],'review');self.assertEqual(result['item_failures'],3)
        self.assertEqual(result['done'],9)
    def test_default_gemma_skips_correction_and_keeps_original(self):
        original=copy.deepcopy(self.source);job=self.job()
        with patch('archive.transcript_correction_job.process',side_effect=AssertionError('보정 경로 호출')):
            result=self.execute(job)
        self.assertEqual(result['model'],'gemma-4-E4B-it-Q4_K_M')
        self.assertTrue(result['inference']['thinking']);self.assertEqual(result['contract']['output'],8192)
        self.assertEqual(self.source,original)
        self.assertEqual(read_json(self.path/'context/runs'/result['id']/'source.json'),original)
        self.assertTrue(result['reaction_analysis']);self.assertEqual(result['chat_failures'],0)
    def test_existing_qwen_resume_keeps_original_engine_contract(self):
        job=self.job(options={'model':'Qwen3-8B-Q4_K_M'});count=[0]
        def cancel(*args):
            count[0]+=1
            if count[0]==2:job.cancel()
            return self.infer(*args)
        old=self.execute(job,cancel)
        resume=self.job('resume',{'model':'gemma-4-E4B-it-Q4_K_M'})
        self.assertIsNone(resume.inference);self.assertEqual(resume.model_info['name'],'Qwen3-8B-Q4_K_M')
        result=self.execute(resume)
        self.assertTrue(result['complete']);self.assertEqual(result['contract'],old['contract'])
        self.assertEqual(result['contract']['output'],3600)
    def test_modified_thinking_profile_cannot_resume(self):
        job=self.job();job.cancel();self.execute(job)
        file=self.path/'context/runs'/jobs.state(self.path)['run']/'result.json'
        value=read_json(file);value['inference']['thinking']=False
        file.write_text(json.dumps(value));before=file.read_bytes()
        with self.assertRaisesRegex(ValueError,'실행 설정'):full.prepare(self.path,'1','resume',{})
        self.assertEqual(before,file.read_bytes())

class BudgetTests(unittest.TestCase):
    def test_whole_prompt_and_reserve(self):
        class Counter:
            def count(self,text):return len(text)
        self.assertEqual(tokens.fit(['abc']*10,lambda r:'header'+''.join(r),Counter(),15),['abc']*3)
        with self.assertRaises(ValueError):tokens.fit(['very long'],lambda r:''.join(r),Counter(),2)
