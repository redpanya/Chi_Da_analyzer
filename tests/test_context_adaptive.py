"""문맥 보완의 보존·오류 격리·일반화 계약. 의미 품질 실측과 구분한다."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from archive import context_full as full, context_job as jobs, context_tokens as tokens, analysis
from archive import context_adaptive as policy, context_adaptive_input as inp, context_adaptive_result as result
from archive.storage import ProjectLock, read_json
from test_context_full import source
from test_context_dialogue import FakeTokenizer


def response(rows,key='check'):
    refs=[r['id'] for r in rows[:2]]
    return {'id':key,'interpretations':[],'omissions':[], 'threads':[{'id':'main','title':'작업 일정',
        'title_evidence':refs,'claims':[{'text':'작업의 일정과 조건을 논의한다.','evidence':refs,'interpretations':[],'decision':'supported'}]}]}


class AdaptiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)
        self.source=source(9,270000);self.calls=[]
        for p in [patch.object(full,'VERSION',10),patch.object(full,'current_source',side_effect=lambda *a:copy.deepcopy(self.source)),
                  patch('archive.context_events.settings',return_value=analysis.settings({})),patch.object(tokens,'Tokenizer',FakeTokenizer)]:
            p.start();self.addCleanup(p.stop)

    def job(self,action='whole'):return jobs.ContextJob(self.path,'1',ProjectLock(self.path),action,full.prepare(self.path,'1',action,{}))

    def infer(self,value,folder,*args):
        self.calls.append(folder.name);folder.mkdir(parents=True)
        if 'rows' in value:return {'continues':bool(value['active']),'topics':[{'start_id':value['rows'][0]['id'],'title':'일정 논의','context':'일정을 정한다.'}]},1
        if 'review_tasks' in value:return {'items':[response(t['rows'],t['id']) for t in value['review_tasks']]},1
        return {'items':[{'id':x['id'],'chat':'반응 표현이 있다.','evidence':[next(r['id'] for r in x['input']['evidence'] if r['kind']=='chat')]} for x in value['items']]},1

    def execute(self,job,infer=None):
        with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=infer or self.infer):job.run()
        self.assertNotEqual(jobs.state(self.path)['state'],'error',jobs.state(self.path))
        return jobs.result(self.path,'1')

    def test_new_pipeline_preserves_manual_and_includes_quality_candidates(self):
        self.source['speech'][1].update(quality_review=True,boundary_review=True,repeat_review=True,status='failed')
        self.source['speech'][2].update(corrected=True,text='사용자 교정 문장',speaker_name='확인 화자',status='confirmed')
        before=copy.deepcopy(self.source);value=self.execute(self.job())
        self.assertEqual(self.source,before);self.assertEqual(value['version'],10);self.assertEqual(value['done'],9)
        self.assertTrue(value['complete']);self.assertTrue(value['items'][0]['copy_ready'])
        rows=read_json(self.path/'context/runs'/value['id']/'utterances.json')['rows']
        self.assertEqual(rows[1]['speaker_tag'],'불명');self.assertTrue(rows[2]['corrected'])

    def test_invalid_structure_has_explicit_ledger_not_silent_skip(self):
        self.source['speech'][0]['start_ms']=-1
        self.source['speech'][1].update(encoding_review=True)
        value=self.execute(self.job());self.assertEqual(value['done'],7);self.assertEqual(len(value['input_rejections']),2)

    def test_nonfinite_or_malformed_time_does_not_break_browser_json(self):
        import json
        for invalid in (float('nan'),float('inf'),'시각 오류',None):
            self.source['speech'][0]['start_ms']=invalid
            rows,rejected=inp.prepare(self.source)
            self.assertEqual(len(rows),8);self.assertIsNone(rejected[0]['start_ms'])
            json.dumps(rejected,allow_nan=False)

    def test_only_identical_source_record_is_deduplicated_not_real_repetition(self):
        self.source['speech'][0]['id']='원출력-1'
        self.source['speech'][1]=copy.deepcopy(self.source['speech'][0])
        self.source['speech'][2]=self.source['speech'][0]|{'id':'원출력-2'}
        rows,rejected=inp.prepare(self.source)
        self.assertEqual(len(rows),8);self.assertEqual(len(rejected),1)
        self.assertEqual(rows[0]['text'],rows[1]['text']);self.assertNotEqual(rows[0]['source_id'],rows[1]['source_id'])

    def test_surface_candidate_retains_original_and_manual_cannot_be_overwritten(self):
        rows=inp.rows(self.source);raw=response(rows)
        raw['interpretations']=[{'id':'I1','source_id':'S0','proposed_text':'일정에 관한 표현','evidence':['S0','S1'],'reason':'뒤 발언에서 뜻을 설명함','risk':'surface'}]
        raw['threads'][0]['claims'][0]['interpretations']=['I1'];before=copy.deepcopy(rows)
        checked=result.checked(raw,rows);self.assertEqual(checked['changes'][0]['status'],'applied');self.assertEqual(rows,before)
        rows[0]['corrected']=True;checked=result.checked(raw,rows)
        self.assertEqual(checked['changes'][0]['status'],'review');self.assertFalse(checked['groups'][0]['claims'])
        raw['interpretations'][0]['proposed_text']=rows[0]['text']
        checked=result.checked(raw,rows);self.assertTrue(checked['groups'][0]['claims'])

    def test_meaning_change_is_held_without_losing_other_valid_claim(self):
        rows=inp.rows(self.source);raw=response(rows)
        raw['interpretations']=[{'id':'I1','source_id':'S0','proposed_text':'주체를 바꾼 주장','evidence':['S0','S1'],'reason':'다른 해석 후보','risk':'meaning'}]
        raw['threads'][0]['claims'].append({'text':'확인되지 않은 주체다.','evidence':['S0'],'interpretations':['I1'],'decision':'supported'})
        out=result.checked(raw,rows)['groups'][0];self.assertEqual(len(out['claims']),1);self.assertEqual(len(out['held']),1)

    def test_explicit_restatement_can_support_meaning_but_duplicate_candidates_cannot(self):
        rows=inp.rows(self.source);raw=response(rows)
        candidate={'id':'I1','source_id':'S0','proposed_text':'뒤 발언에서 정정된 내용',
            'evidence':['S0','S1'],'reason':'별도 발언에서 명시적 정정','risk':'meaning','basis':'explicit_restatement'}
        raw['interpretations']=[candidate];raw['threads'][0]['claims'][0]['interpretations']=['I1']
        checked=result.checked(raw,rows);self.assertEqual(checked['changes'][0]['status'],'applied')
        self.assertEqual(len(checked['groups'][0]['claims']),1)
        raw['interpretations'].append(dict(candidate))
        checked=result.checked(raw,rows);self.assertFalse(checked['changes']);self.assertFalse(checked['groups'][0]['claims'])

    def test_interpretation_support_must_be_present_in_claim(self):
        rows=inp.rows(self.source);raw=response(rows)
        raw['interpretations']=[{'id':'I1','source_id':'S0','proposed_text':'보완 문장','evidence':['S0','S2'],
            'reason':'다른 원문에서 재언급','risk':'surface'}]
        raw['threads'][0]['claims'][0]['interpretations']=['I1']
        checked=result.checked(raw,rows);self.assertTrue(checked['groups'][0]['held'])

    def test_held_parallel_claims_are_not_lost(self):
        rows=inp.rows(self.source);raw=response(rows)
        side=response(rows[4:6])['threads'][0];side['id']='parallel_1';side['claims'][0]['decision']='review'
        raw['threads'].append(side)
        from archive.context_dialogue_input import card
        item=card(self.source,rows,'초안','초안');item['review_parts']={'p':result.checked(raw,rows)}
        self.assertEqual(result.publish(item,self.source),[]);self.assertTrue(item['held_claims']);self.assertTrue(item['copy_ready'])

    def test_bad_review_response_has_bounded_retries_and_keeps_raw_inputs(self):
        def fail(value,folder,*args):
            if 'review_tasks' in value:
                folder.mkdir(parents=True);self.calls.append(folder.name);return {},1
            return self.infer(value,folder,*args)
        value=self.execute(self.job(),fail)
        self.assertEqual(value['done'],9);self.assertTrue(value['evidence_reviews'])
        self.assertLessEqual(sum(name.startswith('interpret-') for name in self.calls),10)
        self.assertEqual(sum(r['kind']=='speech' for r in value['items'][0]['input']['evidence']),9)

    def test_reject_interpretation_forks_result_preserving_all_prior_files(self):
        def infer(value,folder,*args):
            raw,seconds=self.infer(value,folder,*args)
            if 'review_tasks' in value:
                for out,task in zip(raw['items'],value['review_tasks']):
                    refs=[r['id'] for r in task['rows'][:2]]
                    out['interpretations']=[{'id':'I1','source_id':refs[0],'proposed_text':'문맥 보완 후보',
                        'evidence':refs,'reason':'명시적 재언급','risk':'surface','basis':'explicit_restatement'}]
                    out['threads'][0]['claims'][0]['interpretations']=['I1']
            return raw,seconds
        value=self.execute(self.job(),infer);folder=self.path/'context/runs'/value['id']
        before={str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        change=value['items'][0]['interpretations'][0]
        from archive.context_interpretation_edit import reject
        new=reject(self.path,'1',value['id'],change['owner_id'],change['part_id'],change['id'])
        self.assertNotEqual(new,value['id'])
        changed=jobs.result(self.path,'1',new);self.assertEqual(changed['derived_from'],value['id'])
        self.assertFalse(changed['items'][0]['copy_ready']);self.assertTrue(changed['items'][0]['held_claims'])
        self.assertEqual(changed['items'][0]['interpretations'][0]['status'],'rejected')
        self.assertEqual(before,{str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*') if p.is_file()})
        with self.assertRaises(ValueError):reject(self.path,'1',new,change['owner_id'],change['part_id'],change['id'])

    def test_missing_review_item_retries_only_that_item(self):
        requests=[]
        def infer(value,folder,*args):
            raw,seconds=self.infer(value,folder,*args)
            if 'rows' in value:
                raw={'continues':False,'topics':[{'start_id':r['id'],'title':'별개 논의','context':'검토 전 초안'} for r in value['rows'][::3]]}
            if 'review_tasks' in value:
                requests.append([t['id'] for t in value['review_tasks']])
                if len(requests)==1:raw['items'].pop(1)
            return raw,seconds
        value=self.execute(self.job(),infer)
        self.assertEqual(len(requests[0]),3);self.assertEqual(requests[1],[requests[0][1]])
        self.assertTrue(value['complete']);self.assertEqual(value['evidence_reviews'],0)

    def test_output_limit_splits_instead_of_retrying_identical_group(self):
        requests=[]
        def infer(value,folder,*args):
            if 'rows' in value:
                requests.append([r['id'] for r in value['rows']])
                if len(value['rows'])>5:raise jobs.OutputLimitError('출력 상한')
            return self.infer(value,folder,*args)
        value=self.execute(self.job(),infer)
        self.assertTrue(value['complete']);self.assertNotEqual(requests[0],requests[1]);self.assertLess(len(requests[1]),len(requests[0]))

    def test_unrelated_utterance_retained_in_input_and_parallel_topic_survives(self):
        rows=inp.rows(self.source);raw=response(rows)
        raw['omissions']=[{'source_id':'S8','role':'aside','reason':'현재 질문과 연결되지 않는 끼어든 말'}]
        side=response(rows[4:6])['threads'][0];side['id']='parallel_1';raw['threads'].append(side)
        item=__import__('archive.context_dialogue_input',fromlist=['card']).card(self.source,rows,'초안','초안')
        item['review_parts']={'part':result.checked(raw,rows)}
        extra=result.publish(item,self.source)
        self.assertEqual(len(extra),1);self.assertTrue(extra[0]['parallel']);self.assertEqual(len(item['input']['evidence']),9)
        self.assertEqual(item['omissions'][0]['status'],'omitted')

    def test_bad_claim_or_unknown_interpretation_does_not_discard_good_sentence(self):
        rows=inp.rows(self.source);raw=response(rows)
        raw['threads'][0]['claims'].extend([{'text':'외부 원문','evidence':['S999'],'interpretations':[],'decision':'supported'},
            {'text':'누락 후보','evidence':['S1'],'interpretations':['missing'],'decision':'supported'}])
        out=result.checked(raw,rows)['groups'][0];self.assertEqual(len(out['claims']),1);self.assertEqual(len(out['held']),2)

    def test_boundary_time_shift_and_identifier_permutation_keep_partition(self):
        for offset in (0,5000,3600000):
            data=copy.deepcopy(self.source);data['duration_ms']+=offset
            for r in data['speech']:r['start_ms']+=offset;r['end_ms']+=offset
            rows=inp.rows(data)
            for i,r in enumerate(rows):r['id']='U'+str(i*7+3)
            raw={'continues':False,'topics':[{'start_id':rows[0]['id']},{'start_id':rows[4]['id']}]}
            parts=policy.ranges(raw,rows,None)
            self.assertEqual([r['id'] for _,rs in parts for r in rs],[r['id'] for r in rows])

    def test_long_single_topic_reads_every_source_once_in_review_parts(self):
        self.source=source(2400,72000000)
        value=self.execute(self.job())
        self.assertEqual(value['done'],2400);self.assertEqual(value['item_failures'],0)
        owner=next(x for x in value['items'] if not x.get('gap'))
        self.assertGreater(len(owner['review_parts']),1)
        folder=self.path/'context/runs'/value['id']
        reviewed=[]
        # 성공 체크포인트의 실제 요청이 원문 전체를 한 번씩 읽었는지 별도 기록을 검사한다.
        from archive.context_adaptive_review import tasks_for
        fresh=copy.deepcopy(owner);fresh.pop('review_parts')
        for task in tasks_for(fresh,FakeTokenizer()):reviewed.extend(r['id'] for r in task['rows'])
        self.assertEqual(len(reviewed),2400);self.assertEqual(len(set(reviewed)),2400)
        self.assertEqual(len(read_json(folder/'utterances.json')['rows']),2400)

    def test_chat_request_contains_no_transcript_or_draft_and_speaker_aliases_are_opaque(self):
        from archive.context_adaptive_chat import build
        from archive.context_dialogue_input import card,value as input_value
        self.source['speech'][0].update(text='전사에만 존재하는 정보',speaker_name='임의 이름')
        rows=inp.rows(self.source);item=card(self.source,rows,'초안 전용 정보','본문 전용 정보')
        item['input']=input_value(self.source,rows,chat_budget=1600)
        request=build([item])
        for content in ('전사에만 존재하는 정보','초안 전용 정보','본문 전용 정보'):
            self.assertNotIn(content,request)
        first=inp.records(rows)
        self.source['speech'][0]['speaker_name']='다른 이름'
        self.assertEqual(first,inp.records(inp.rows(self.source)))

    def test_chat_occurrences_keep_source_identity_across_overlapping_topics(self):
        from archive.context_adaptive_chat import retain_occurrences
        from archive.context_dialogue_input import value as input_value
        items=[]
        for start,end in [(0,100000),(20000,200000)]:
            item={'start_ms':start,'end_ms':end,'input':input_value(self.source,[],start,end,1600)}
            retain_occurrences(self.source,item);items.append(item)
            for row in item['input']['evidence']:self.assertEqual(row['count'],len(row['occurrences']))
        occurrences={at['id'] for item in items for row in item['input']['evidence'] for at in row['occurrences']}
        self.assertEqual(len(occurrences),7)

    def test_cancel_review_reuses_completed_dialogue(self):
        job=self.job()
        def cancel(value,folder,*args):
            raw=self.infer(value,folder,*args)
            if 'review_tasks' in value:job.cancel()
            return raw
        self.execute(job,cancel);self.assertEqual(jobs.state(self.path)['state'],'paused')
        self.calls.clear();value=self.execute(self.job('resume'));self.assertTrue(value['complete'])
        self.assertFalse(any(x.startswith('dialogue-') for x in self.calls))

    def test_failed_chat_forks_old_results_and_reuses_dialogue(self):
        def fail(value,folder,*args):
            raw,secs=self.infer(value,folder,*args)
            if 'items' in value:raw={'items':[]}
            return raw,secs
        value=self.execute(self.job(),fail);self.assertFalse(value['complete'])
        old=self.path/'context/runs'/value['id']/'dialogue-state.json';before=old.read_bytes();self.calls.clear()
        new=self.execute(self.job('resume'));self.assertTrue(new['complete']);self.assertEqual(old.read_bytes(),before)
        self.assertNotEqual(new['id'],value['id']);self.assertFalse(any(x.startswith(('dialogue-','interpret-')) for x in self.calls))

    def test_boundary_failures_have_finite_budget_and_continue(self):
        def fail(value,folder,*args):
            if 'rows' in value:folder.mkdir(parents=True);self.calls.append(folder.name);return {},1
            return self.infer(value,folder,*args)
        value=self.execute(self.job(),fail);self.assertEqual(value['done'],9)
        self.assertLessEqual(len(self.calls),10);self.assertGreater(value['item_failures'],0)


if __name__=='__main__':unittest.main()
