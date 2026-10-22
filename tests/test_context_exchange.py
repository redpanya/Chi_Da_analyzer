"""가상 방송으로 빠른 경계·외부 파일 신뢰 경계·기존 자료 보존을 검사한다."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from archive import context_exchange as exchange, context_exchange_data as data, context_timestamps as quick, context_job
from archive.storage import ProjectLock, read_json, save_json
from test_context_dialogue import FakeTokenizer


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.path=Path(tmp.name)
        self.source={'rows':[dict(id=f'S{i}',source_id=f'raw-{i}',kind='speech',start_ms=i*10000,end_ms=i*10000+9000,
            text=f'독립 검증 발언 {i}',speaker='로컬 실명',speaker_tag='추정 P1',corrected=i==0,fragment=False,quality_flags=[]) for i in range(6)],
            'chat':[dict(id=f'C{i}',kind='chat',start_ms=i*10000+500,end_ms=i*10000+500,text=f'채팅 반응 {i}') for i in range(6)],
            'duration_ms':60000,'input_selection':{'transcript_run':'a'*32,'speaker_run':None},'input_label':'한국어 · 수동 교정 포함',
            'include_chat':False,'chat_offset_ms':0,'rejected':[]}
        def snapshot(path,vod,selection,include_chat=False,offset=0):
            return copy.deepcopy(self.source)|{'include_chat':include_chat,'chat_offset_ms':offset,'chat':copy.deepcopy(self.source['chat']) if include_chat else []}
        p=patch.object(data,'snapshot',side_effect=snapshot);p.start();self.addCleanup(p.stop)
        self.old=self.path/'context/runs'/('b'*32)/'result.json';save_json(self.old,{'원본':'기존 결과'})
        self.before=self.old.read_bytes()
        save_json(self.path/'context/state.json',{'state':'complete','run':'b'*32,'runs':[{'id':'b'*32,'scope':'full','label':'기존','title':'상세'}]})

    def create(self,mode='timestamps',chat=False):
        with patch.object(exchange,'PACKET_BYTES',700):
            return exchange.create(self.path,'1',{'selection':self.source['input_selection'],'mode':mode,'include_chat':chat})

    def responses(self,bundle):
        saved=read_json(exchange.folder(self.path,bundle['id'])/'manifest.json');source=read_json(exchange.folder(self.path,bundle['id'])/'source.json')
        result=[]
        for c in saved['chunks']:
            rows=source['rows'][c['first']:c['last']]
            part={'start_id':rows[0]['id'],'title':'진행 중인 같은 이야기','evidence_ids':[rows[0]['id']],'review_needed':False}
            if saved['mode']=='detail':part.update(speech_summary='대화에서 규칙을 논의한다.',chat_summary='',chat_evidence_ids=[])
            result.append({'schema_version':1,'export_id':bundle['id'],'chunk_id':c['id'],'mode':saved['mode'],
                'coverage':{'first_id':rows[0]['id'],'last_id':rows[-1]['id']},'continues_previous':c['first']!=0,'topics':[part]})
        return result

    def receive(self,entries):
        text=json.dumps({'results':entries},ensure_ascii=False);preview=exchange.preview(self.path,'1',text)
        return exchange.receive(self.path,'1',text,preview['token'])

    def test_partial_roundtrip_new_versions_duplicate_and_no_source_leak(self):
        bundle=self.create();raw=''.join(r['text'] for r in bundle['files'])
        self.assertNotIn('로컬 실명',raw);self.assertNotIn('source_id',raw)
        replies=self.responses(bundle);self.assertGreater(len(replies),1)
        first=self.receive(replies[:1]);before=(self.path/'context/runs'/first['run']/'work.json').read_bytes()
        partial=context_job.result(self.path,'1',first['run']);self.assertFalse(partial['complete']);self.assertTrue(partial['items'][-1]['provisional'])
        final=self.receive(replies[1:]);result=context_job.result(self.path,'1',final['run'])
        self.assertTrue(result['complete']);self.assertEqual(len(result['items']),1)
        self.assertEqual(result['items'][0]['start_ms'],0);self.assertEqual(result['items'][0]['end_ms'],59000)
        self.assertTrue(self.receive(replies)['duplicate'])
        self.assertEqual(before,(self.path/'context/runs'/first['run']/'work.json').read_bytes())
        self.assertEqual(self.before,self.old.read_bytes())

    def test_chat_full_export_and_evidence_separation(self):
        bundle=self.create('detail',True);saved=read_json(exchange.folder(self.path,bundle['id'])/'manifest.json')
        self.assertEqual(sum(c['chat_last']-c['chat_first'] for c in saved['chunks']),6)
        entries=self.responses(bundle);entries[0]['topics'][0].update(chat_summary='웃음 반응이 있다.',chat_evidence_ids=['C0'])
        result=context_job.result(self.path,'1',self.receive(entries)['run'])
        self.assertEqual(result['items'][0]['summary']['chat'][0]['evidence'],['C0'])
        entries[0]['topics'][0]['evidence_ids']=['C0']
        with self.assertRaises(ValueError):exchange.preview(self.path,'1',json.dumps(entries[0]))

    def test_wrong_scope_ids_order_and_stale_inputs_are_rejected(self):
        bundle=self.create();entry=self.responses(bundle)[0]
        for mutation in [dict(export_id='f'*32),dict(mode='detail'),dict(coverage={'first_id':'S0','last_id':'S999'}),dict(schema_version=True)]:
            with self.assertRaises(ValueError):exchange.preview(self.path,'1',json.dumps(entry|mutation))
        changed=copy.deepcopy(entry);changed['topics'][0]['evidence_ids']=['S999']
        with self.assertRaises(ValueError):exchange.preview(self.path,'1',json.dumps(changed))
        self.source['rows'][0]['text']='나중에 수동 교정'
        with self.assertRaisesRegex(ValueError,'입력'):exchange.preview(self.path,'1',json.dumps(entry))
        self.assertEqual(self.before,self.old.read_bytes())

    def test_duplicate_keys_nonfinite_size_preview_race_and_cancel(self):
        for text in ['{"a":1,"a":2}','{"a":NaN}','{','[]','"'+('x'*(data.MAX_RESULT_BYTES+1))+'"']:
            with self.assertRaises(ValueError):exchange.preview(self.path,'1',text)
        bundle=self.create();entries=self.responses(bundle);text=json.dumps(entries[0]);preview=exchange.preview(self.path,'1',text)
        self.receive(entries[1:])
        with self.assertRaisesRegex(ValueError,'다시 검사'):exchange.receive(self.path,'1',text,preview['token'])
        with self.assertRaises(ValueError):exchange.protect_input(self.path,'a'*32,'transcript_run')
        exchange.cancel(self.path,bundle['id']);exchange.protect_input(self.path,'a'*32,'transcript_run')
        with self.assertRaises(ValueError):exchange.preview(self.path,'1',text)

    def job(self,action='timestamps',run=None):
        options={'run':run} if run else {'selection':self.source['input_selection']}
        value=quick.prepare(self.path,'1',action,options)
        return context_job.ContextJob(self.path,'1',ProjectLock(self.path),action,value)

    def execute(self,job,bad=None):
        self.calls=[]
        def infer(value,folder,*_):
            folder.mkdir(parents=True);rows=value['rows'];self.calls.append(rows[0]['id'])
            if bad==rows[0]['id']:return {},0
            return {'continues_previous':bool(value['previous']),'topics':[dict(start_id=rows[0]['id'],title='동일 주제',evidence_ids=[rows[0]['id']],review_needed=False)]},0
        with patch.object(job,'check_engine'),patch.object(job,'make_tokenizer',return_value=FakeTokenizer()),patch.object(job,'infer_value',side_effect=infer),patch.object(quick.context_boundary,'fit',side_effect=lambda rows,*_:rows[:2]):job.run()
        return context_job.result(self.path,'1')

    def test_quick_only_boundaries_failure_continues_and_resume(self):
        job=self.job();result=self.execute(job,'S2')
        self.assertEqual(context_job.state(self.path)['state'],'review');self.assertEqual(result['done'],6)
        self.assertEqual(result['item_failures'],1);self.assertIn('S4',self.calls)
        run=result['id'];before=(self.path/'context/runs'/run/'work.json').read_bytes()
        result=self.execute(self.job('timestamps-resume',run))
        self.assertTrue(result['complete']);self.assertEqual(self.calls,['S2','S4'])
        self.assertNotEqual(result['id'],run)
        self.assertEqual(before,(self.path/'context/runs'/run/'work.json').read_bytes())
        self.assertEqual(result['mode'],'timestamps');self.assertFalse(result['inference']['thinking'])
        self.assertEqual(self.before,self.old.read_bytes())

    def test_fast_resume_ignores_chat_changes_and_timing_over_ten_hours(self):
        job=self.job();result=self.execute(job,'S2');self.source['chat'][0]['text']='새 채팅'
        resumed=self.execute(self.job('timestamps-resume',result['id']));self.assertFalse(resumed['stale'])
        self.source['rows'][0]['start_ms']=36000000;self.source['rows'][0]['end_ms']=36009000
        card=data.card(self.source['rows'][:1],'열 시간 뒤',[],self.source)
        self.assertTrue(card['input']['label'].startswith('10:00:00'))

    def test_reference_budget_preserves_source_and_bounds_long_context(self):
        rows=copy.deepcopy(self.source['rows']);rows[0]['text']='긴 발언 '*1000
        before=copy.deepcopy(rows);tokenizer=FakeTokenizer()
        selected=quick.reference(rows,tokenizer,256)
        self.assertEqual(before,rows)
        self.assertLessEqual(tokenizer.count(quick.prompt('',data.records(selected))),256)


if __name__=='__main__':unittest.main()
