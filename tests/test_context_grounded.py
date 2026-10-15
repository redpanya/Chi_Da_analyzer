import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from archive import context_full as full, context_job as jobs, context_grounded as policy
from archive import context_grounding as grounding, context_grounded_chat as chat
from archive import context_dialogue_input as di, context_tokens as tokens, analysis
from archive.storage import ProjectLock, read_json
from test_context_full import source
from test_context_dialogue import FakeTokenizer


class GroundedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name);self.source=source(9,270000);self.calls=[]
        for p in [patch.object(full,'VERSION',9),patch.object(full,'current_source',side_effect=lambda *a:copy.deepcopy(self.source)),
                  patch('archive.context_events.settings',return_value=analysis.settings({})),patch.object(tokens,'Tokenizer',FakeTokenizer)]:
            p.start();self.addCleanup(p.stop)

    def job(self,action='whole'):
        return jobs.ContextJob(self.path,'1',ProjectLock(self.path),action,full.prepare(self.path,'1',action,{}))

    def infer(self,value,folder,*args):
        self.calls.append(folder.name);folder.mkdir(parents=True)
        if 'rows' in value:
            return {'continues':bool(value['active']),'topics':[{'start_id':value['rows'][0]['id'],'title':'준비 이야기','context':'규칙과 준비 사항을 설명한다.'}]},1
        result=[]
        for item in value['items']:
            if folder.name.startswith('grounding'):
                r=next(r for r in item['input']['evidence'] if r['kind']=='speech')
                result.append({'id':item['id'],'title':'원문 대조 요약','context':'준비 사항을 이야기한다.','uncertain':False,'evidence':[{'id':r['id'],'quote':r['text']}]})
            else:
                r=next(r for r in item['input']['evidence'] if r['kind']=='chat')
                result.append({'id':item['id'],'chat':'준비에 관한 채팅이 있다.','evidence':[{'id':r['id'],'quote':r['text']}]})
        return {'items':result},1

    def execute(self,job,infer=None):
        with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=infer or self.infer):job.run()
        return jobs.result(self.path,'1')

    def test_start_only_partition_covers_filler_and_sparse_source_ids(self):
        rows=di.rows(self.source)[:5]
        for row,id in zip(rows,['S498','S506','S507','S508','S509']):row['id']=id
        raw={'continues':False,'topics':[{'start_id':'S498','title':'가','context':'가'}, {'start_id':'S509','title':'나','context':'나'}]}
        parts=policy.ranges(raw,rows,None)
        self.assertEqual([[r['id'] for r in selected] for _,selected in parts],[['S498','S506','S507','S508'],['S509']])
        raw['topics'][1]['start_id']='S498'
        with self.assertRaises(ValueError):policy.ranges(raw,rows,None)

    def test_whole_pipeline_uses_grounding_and_independent_chat(self):
        before=copy.deepcopy(self.source);result=self.execute(self.job())
        self.assertTrue(result['complete'],jobs.state(self.path));self.assertEqual(result['version'],9)
        item=next(r for r in result['items'] if not r.get('gap'))
        self.assertEqual(item['grounding_state'],'complete');self.assertIn('draft_summary',item)
        self.assertEqual(item['summary']['title'],'원문 대조 요약');self.assertFalse(item['range_sources'])
        self.assertEqual(self.source,before)
        text=chat.build([item]);self.assertNotIn('규칙과 준비 사항을 설명한다.',text);self.assertNotIn('원문 대조 요약',text)

    def test_malformed_large_batch_halves_and_only_single_bad_row_fails(self):
        def fail(value,folder,*args):
            if 'rows' in value and any(r['id']=='S4' for r in value['rows']):folder.mkdir(parents=True);return {},1
            return self.infer(value,folder,*args)
        result=self.execute(self.job(),fail)
        self.assertEqual(result['done'],9);self.assertEqual(result['item_failures'],1)
        broken=[r for r in result['items'] if r.get('failed')]
        self.assertEqual(broken[0]['start_id'],broken[0]['end_id']);self.assertEqual(broken[0]['start_id'],'S4')
        old=result['id'];file=self.path/'context/runs'/old/'dialogue-state.json';before=file.read_bytes()
        new=self.execute(self.job('resume'));self.assertTrue(new['complete'],jobs.state(self.path))
        self.assertNotEqual(new['id'],old);self.assertEqual(file.read_bytes(),before)

    def test_invalid_evidence_does_not_publish_draft_or_damage_other_items(self):
        items=[di.card(self.source,di.rows(self.source)[i:i+1],'확정하면 안 되는 초안','먹지 않아서 소화가 안 된다.') for i in range(2)]
        grounding.apply(items[0],{'title':'확정 오류','context':'원문에 없는 말','uncertain':False,'evidence':[{'id':'S999','quote':'없는 말'}]})
        self.assertFalse(items[0]['summary']['context']);self.assertTrue(items[0]['evidence_review'])
        self.assertEqual(items[1]['summary']['title'],'확정하면 안 되는 초안')
        for refs in [None,[None],[{'id':[],'quote':'a'}],[{'id':'S0','quote':'없는 말'}]]:
            self.assertFalse(grounding.quotes_valid(refs,{'S0':'원래 말'}))

    def test_chat_only_punctuation_never_becomes_dialogue_story(self):
        self.source['chat']=[{'offset_ms':0,'text':'?','message_type':1}]
        result=self.execute(self.job());item=result['items'][0]
        self.assertIn('원인은 확인할 수 없습니다',item['summary']['chat'][0]['text'])
        self.assertFalse(any(x.startswith('chat-grounded') for x in self.calls))
        self.assertEqual(item['summary']['relation'],[])

    def test_cancel_during_grounding_resumes_without_repeating_dialogue(self):
        job=self.job()
        def cancel(value,folder,*args):
            answer=self.infer(value,folder,*args)
            if folder.name.startswith('grounding'):job.cancel()
            return answer
        self.execute(job,cancel);self.assertEqual(jobs.state(self.path)['state'],'paused')
        self.calls.clear();result=self.execute(self.job('resume'))
        self.assertTrue(result['complete'],jobs.state(self.path));self.assertFalse(any(x.startswith('dialogue-') for x in self.calls))

    def test_empty_draft_and_three_adjacent_bad_rows_do_not_stop_later_rows(self):
        def infer(value,folder,*args):
            if 'rows' in value:
                if any(r['id'] in ('S2','S3','S4') for r in value['rows']):
                    folder.mkdir(parents=True);return {},1
                raw,seconds=self.infer(value,folder,*args)
                raw['topics'][0]['context']='';return raw,seconds
            return self.infer(value,folder,*args)
        result=self.execute(self.job(),infer)
        self.assertEqual(result['done'],9);self.assertEqual(result['item_failures'],3)
        self.assertTrue(any(x.get('end_id')=='S8' and not x.get('failed') for x in result['items']))

    def test_missing_chat_evidence_is_scoped_and_recovery_preserves_failed_result(self):
        def infer(value,folder,*args):
            raw,seconds=self.infer(value,folder,*args)
            if folder.name.startswith('chat-grounded'):
                raw['items'][0]={'id':raw['items'][0]['id'],'chat':''}
            return raw,seconds
        result=self.execute(self.job(),infer)
        self.assertEqual(result['chat_failures'],1);self.assertFalse(result['complete'])
        file=self.path/'context/runs'/result['id']/'dialogue-state.json';before=file.read_bytes()
        self.calls.clear();new=self.execute(self.job('resume'))
        self.assertTrue(new['complete'],jobs.state(self.path));self.assertNotEqual(new['id'],result['id'])
        self.assertEqual(file.read_bytes(),before)
        self.assertFalse(any(x.startswith('dialogue-') or x.startswith('grounding-') for x in self.calls))


if __name__=='__main__':unittest.main()
