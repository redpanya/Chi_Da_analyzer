"""새 경계 경로의 참고 소유권·한도·부분 오류·체크포인트·구형 계약 회귀 검사."""
import copy
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from archive import context_boundary as boundary, context_full as full, context_job as jobs
from archive import context_dialogue_input as di, context_dialogue_model as model, analysis
from archive.context_server import Server, profile, boundary_profile, supported
from archive.context_metrics import collect
from archive.storage import ProjectLock, read_json, save_json
from test_context_full import source


class Counter:
    seconds=0
    def count(self,text):return len(text)//3


def response(plan, continues=False, refs=None):
    rows=plan['rows']
    return {'continues':continues,'topics':[{'start_id':rows[0]['id'],'end_id':rows[-1]['id'],
        'title':'이어지는 준비 이야기','context':'준비 사항과 규칙을 설명한다.',
        'evidence_ids':refs if refs is not None else [rows[0]['id']]}]}


class InputTests(unittest.TestCase):
    def test_omitted_reference_is_not_silence(self):
        rows=boundary.rows(source(12,400000))
        self.assertIn('참고 발언 사이 생략',boundary.lines(rows[:1]+rows[-1:]))
        self.assertNotIn('시각 간격',boundary.lines(rows[:1]+rows[-1:]))
        rows[1]['start_ms']=50000;rows[1]['end_ms']=51000
        self.assertIn('무음 여부 미확인',boundary.lines(rows[:2]))
        value=source(3);value['speech'][1]['repeat_review']=True
        self.assertIn('검토 대상 전사 제외',boundary.lines(boundary.rows(value)))

    def test_middle_references_and_fragments_keep_original_mapping(self):
        value=source(30,1000000);original=copy.deepcopy(value)
        rows=boundary.rows(value);active=di.card(value,rows,'제목','중요한 사실')
        refs=boundary.references(active,Counter())['rows']
        self.assertEqual([r['id'] for r in refs],['S0','S10','S20','S27','S28','S29'])
        self.assertEqual(value,original)
        value['speech'][0]['text']='가'*2600
        parts=boundary.rows(value)[:3]
        self.assertEqual({r['source_ordinal'] for r in parts},{0})
        self.assertEqual(len({r['ordinal'] for r in parts}),3)

    def test_long_candidate_search_never_starts_at_half_video(self):
        sizes=[]
        class Count:
            def count(self,text):sizes.append(len(text));return len(text)
        rows=['가']*100000
        fitted=boundary.fit(rows,lambda r:''.join(r),Count(),budget=100)
        self.assertEqual(len(fitted),100);self.assertLessEqual(max(sizes),128)
        with self.assertRaises(model.SplitRequired):boundary.fit(rows,lambda r:'가'*101,Count(),budget=100)

    def test_lookahead_is_reference_only_and_final_budget_exact(self):
        rows=boundary.rows(source(30,1000000))
        plan=boundary.plan(rows,None,Counter(),limit=3)
        self.assertEqual(len(plan['rows']),3);self.assertLessEqual(len(plan['following']),4)
        self.assertTrue(plan['following']);self.assertLessEqual(Counter().count(plan['text']),4800)
        raw=response(plan);raw['topics'][0]['end_id']=plan['following'][0]['id']
        with self.assertRaises(ValueError):boundary.validate(raw,plan)
        following=boundary.plan(rows[3:],None,Counter(),limit=3)
        self.assertEqual(following['rows'][0]['id'],plan['following'][0]['id'])

    def test_other_topic_and_unsent_evidence_is_review_not_range_success(self):
        value=source(30,1000000);rows=boundary.rows(value)
        active=di.card(value,rows[:27],'주제','앞 이야기')
        plan=boundary.plan(rows[27:],active,Counter())
        state={'active':active,'items':[]}
        raw=response(plan,True,['S5'])  # 실제 전달한 이전 참고에 없는 ID
        self.assertTrue(boundary.validate(raw,plan));boundary.apply(value,plan,raw,state)
        self.assertTrue(state['active']['evidence_review'])
        self.assertEqual(state['active']['summary']['context'][0]['evidence'],[])
        plan=boundary.plan(rows[:3],None,Counter())
        raw={'continues':False,'topics':[response({'rows':rows[:1]},refs=['S1'])['topics'][0],response({'rows':rows[1:3]})['topics'][0]]}
        state={'active':None,'items':[]};boundary.validate(raw,plan);boundary.apply(value,plan,raw,state)
        self.assertTrue(state['items'][0]['evidence_review']);self.assertFalse(state['active']['evidence_review'])

    def test_server_lru_keeps_only_recent_16_native_prompts(self):
        server=Server.__new__(Server);server.profile=boundary_profile();server.cache={};server.seconds=0
        server.job=SimpleNamespace(stop=threading.Event());server.body=lambda text:{'text':text}
        calls=[]
        def request(endpoint,body,timeout):
            calls.append(endpoint)
            return {'prompt':body['text']} if endpoint=='/apply-template' else {'tokens':[1,2,3]}
        server.request=request
        for i in range(16):server.count(str(i))
        server.count('0');server.count('16')
        self.assertEqual(len(server.cache),16);self.assertIn('0',server.cache);self.assertNotIn('1',server.cache)
        self.assertEqual(server.tokenizer_requests,17);self.assertEqual(server.tokenizer_hits,1)
        self.assertTrue(supported(profile()));self.assertTrue(supported(boundary_profile(False)))
        self.assertFalse(supported(boundary_profile()|{'token_cache_entries':100}))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name);self.source=source(9,270000);self.calls=[]
        plan=boundary.plan
        for patcher in [patch.object(full,'VERSION',8),patch.object(full,'current_source',side_effect=lambda *a:copy.deepcopy(self.source)),
            patch('archive.context_events.settings',return_value=analysis.settings({})),
            patch.object(boundary,'plan',side_effect=lambda r,a,t,limit=None:plan(r,a,t,limit=min(limit or 3,3)))]:
            patcher.start();self.addCleanup(patcher.stop)

    def job(self,action='whole'):
        return jobs.ContextJob(self.path,'1',ProjectLock(self.path),action,full.prepare(self.path,'1',action,{}))

    def infer(self,value,folder,*args):
        self.calls.append(folder.name);folder.mkdir(parents=True)
        if 'items' in value:return {'items':[{'id':r['id'],'chat':'웃음이 관측된다.','relation':''} for r in value['items']]},1
        return response(value,bool(value['previous'])),1

    def execute(self,job,infer=None):
        with patch.object(job,'check_engine'),patch.object(job,'make_tokenizer',return_value=Counter()),patch.object(job,'infer_value',side_effect=infer or self.infer):job.run()
        return jobs.result(self.path,'1')

    def test_owned_cursor_chats_and_old_contract(self):
        job=self.job();contract=job.contract()
        self.assertEqual(contract['pipeline_version'],8)
        self.assertEqual(contract['inference']['thinking_budget'],4096)
        result=self.execute(job)
        self.assertTrue(result['complete'],jobs.state(self.path));self.assertEqual(result['done'],9)
        self.assertEqual(result['evidence_reviews'],0)
        items=[r for r in result['items'] if not r.get('gap')]
        self.assertEqual(len(items),1);self.assertEqual(items[0]['end_id'],'S8')
        self.assertEqual(len([r for r in items[0]['input']['evidence'] if r['kind']=='speech']),9)
        self.assertEqual(sum(r.get('count',0) for r in items[0]['input']['evidence']),9)
        self.assertEqual(items[0]['chat_state'],'complete')
        with patch.object(full,'VERSION',7):
            old=self.job();self.assertEqual(old.contract()['input_revision'],3)
            old.input['speaker_policy']=0;old_contract=old.contract();old.lock.close()
        self.assertEqual(old_contract['prompt_revision'],2);self.assertEqual(old_contract['input_revision'],1)
        self.assertNotIn('pipeline_version',old_contract);self.assertEqual(old_contract['inference'],profile())

    def test_evidence_only_failure_is_finished_review_without_retry_loop(self):
        def bad(value,folder,*args):
            raw,seconds=self.infer(value,folder,*args)
            if 'rows' in value:raw['topics'][0]['evidence_ids']=['없는발언']
            return raw,seconds
        result=self.execute(self.job(),bad)
        self.assertTrue(result['complete']);self.assertEqual(result['evidence_reviews'],1)
        self.assertEqual(jobs.state(self.path)['state'],'review');self.assertEqual(result['quality_state'],'review')
        self.assertEqual(len(self.calls),4)
        with self.assertRaises(ValueError):full.prepare(self.path,'1','resume',{})

    def test_range_failure_forks_old_results_without_overwrite(self):
        def bad(value,folder,*args):
            if 'rows' in value and value['rows'][0]['id']=='S3':folder.mkdir(parents=True);return {},1
            return self.infer(value,folder,*args)
        result=self.execute(self.job(),bad);self.assertEqual(result['item_failures'],1)
        old=self.path/'context/runs'/result['id']
        before={str(f.relative_to(old)):f.read_bytes() for f in old.rglob('*') if f.is_file()}
        resumed=self.execute(self.job('resume'));self.assertTrue(resumed['complete'],jobs.state(self.path))
        self.assertNotEqual(resumed['id'],result['id'])
        self.assertEqual(before,{str(f.relative_to(old)):f.read_bytes() for f in old.rglob('*') if f.is_file()})

    def test_response_before_state_write_reused_and_cancel_preserves_cursor(self):
        job=self.job()
        from archive import context_dialogue as dialogue
        publish=dialogue.publish
        def stop_before_commit(folder,state):
            if state['cursor']==3:raise OSError('상태 저장 전 중단')
            publish(folder,state)
        with patch.object(dialogue,'publish',side_effect=stop_before_commit):result=self.execute(job)
        self.assertEqual(result['done'],0);self.calls.clear()
        resumed=self.execute(self.job('resume'));self.assertTrue(resumed['complete'],jobs.state(self.path))
        self.assertEqual(len(self.calls),3)  # 저장된 첫 응답은 재추론하지 않는다.
        measured=read_json(self.path/'context/runs'/resumed['id']/'measurements.json')
        self.assertEqual(measured['checkpoint_reuses'],1)

    def test_dead_engine_stops_without_marking_failed_range_or_retry(self):
        def dead(value,folder,*args):self.calls.append('실패');raise jobs.FatalEngineError('서버 종료')
        result=self.execute(self.job(),dead)
        self.assertEqual(self.calls,['실패']);self.assertEqual(result['done'],0)
        self.assertEqual(jobs.state(self.path)['state'],'error')
        resumed=self.execute(self.job('resume'));self.assertTrue(resumed['complete'])

    def test_changed_source_and_profile_block_resume(self):
        job=self.job();job.cancel();self.execute(job)
        # 엔진 준비 직후 취소도 새 실행의 계약을 보존한다.
        self.source['speech'][0]['text']='원본 변경'
        with self.assertRaises(ValueError):full.prepare(self.path,'1','resume',{})

    def test_missing_metrics_are_unknown_not_zero(self):
        folder=self.path/'run';folder.mkdir()
        save_json(folder/'dialogue-one/metrics.json',{'timings':{'prompt_ms':10,'predicted_ms':20,'predicted_n':3}})
        save_json(folder/'chat-two/metrics.json',{'timings':None})
        value=collect(folder,Counter(),0)
        self.assertIsNone(value['prompt_ms']);self.assertIsNone(value['generation_ms'])

    def test_interrupted_request_is_counted_without_invented_timing(self):
        folder=self.path/'run';folder.mkdir()
        save_json(folder/'dialogue-one/request.json',{})
        save_json(folder/'dialogue-one/metrics.json',{'timings':{'prompt_ms':10,'predicted_ms':20}})
        save_json(folder/'dialogue-two/request.json',{})
        value=collect(folder,Counter(),0)
        self.assertEqual(value['fresh_attempts'],2);self.assertEqual(value['measured_responses'],1)
        self.assertEqual(value['requests_without_response_metrics'],1)
        self.assertIsNone(value['generation_ms']);self.assertEqual(value['completed_generation_ms'],20)

    def test_cancel_during_inference_resumes_only_uncommitted_rows(self):
        job=self.job()
        def cancel(value,folder,*args):
            if 'rows' in value and value['rows'][0]['id']=='S3':job.cancel()
            return self.infer(value,folder,*args)
        result=self.execute(job,cancel)
        self.assertEqual(result['done'],3);self.assertTrue(result['pending_topic']['provisional'])
        self.assertEqual(jobs.state(self.path)['state'],'paused')
        self.calls.clear();resumed=self.execute(self.job('resume'))
        self.assertTrue(resumed['complete']);self.assertEqual(sum(s.startswith('dialogue-') for s in self.calls),2)

    def test_chat_failure_preserves_speech_and_retries_chat_only(self):
        def fail_chat(value,folder,*args):
            if 'items' in value:folder.mkdir(parents=True);return {'items':[]},1
            return self.infer(value,folder,*args)
        result=self.execute(self.job(),fail_chat)
        self.assertEqual(result['chat_failures'],1);self.assertEqual(result['done'],9)
        self.calls.clear();resumed=self.execute(self.job('resume'))
        self.assertTrue(resumed['complete']);self.assertTrue(all(s.startswith('chat-') for s in self.calls))

    def test_inference_profile_change_does_not_silently_resume(self):
        job=self.job();job.cancel();self.execute(job)
        prepared=full.prepare(self.path,'1','resume',{})
        prepared['inference']=boundary_profile(True,cache_prompt=True)
        other=jobs.ContextJob(self.path,'1',ProjectLock(self.path),'resume',prepared)
        result=self.execute(other)
        self.assertEqual(jobs.state(self.path)['state'],'error')
        self.assertIn('엔진·토큰 예산',jobs.state(self.path)['message'])
        self.assertEqual(result['done'],0)

    def test_topic_limit_halves_until_finite_success_without_losing_rows(self):
        def saturated(value,folder,*args):
            raw,seconds=self.infer(value,folder,*args)
            if 'rows' in value and len(value['rows'])>1:raw['topics']*=model.MAX_TOPICS
            return raw,seconds
        result=self.execute(self.job(),saturated)
        self.assertTrue(result['complete'],jobs.state(self.path));self.assertEqual(result['done'],9)
        self.assertLessEqual(len(self.calls),20)

    def test_oversized_single_chat_does_not_stop_other_cards(self):
        def separate(value,folder,*args):
            raw,seconds=self.infer(value,folder,*args)
            if 'rows' in value:raw['continues']=False
            return raw,seconds
        fit=boundary.fit
        def one_too_big(rows,build,tokenizer,budget=4800):
            if rows and 'summary' in rows[0] and rows[0]['id']=='dialogue-S0':raise model.SplitRequired('단일 채팅 입력 초과')
            return fit(rows,build,tokenizer,budget)
        with patch.object(boundary,'fit',side_effect=one_too_big):result=self.execute(self.job(),separate)
        self.assertEqual(result['chat_failures'],1);self.assertEqual(result['done'],9)
        self.assertEqual([r['chat_state'] for r in result['items']],['failed','complete','complete'])


if __name__=='__main__':unittest.main()
