"""특정 방송·문구 예외 없이 채팅 발견, 지연 근거, 구버전·원본 보존을 검사한다."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from archive import context_clip_chat as chat, context_clip_model as model, context_clips as clips
from archive import context_exchange as exchange, context_exchange_data as data, context_clips_local as local
from archive import context_job, context_input, context_guidance
from archive.storage import read_json, save_json
import test_context_exchange


def speech(i,start,end=None):
    return {'id':f'S{i}','kind':'speech','start_ms':start,'end_ms':end or start+4000,
            'text':f'서로 다른 상황을 검토할 발언 {i}', 'speaker_tag':'?','corrected':False}


def message(i,at,text='ㅋㅋㅋ'):
    return {'id':f'C{i}','kind':'chat','start_ms':at,'end_ms':at,'text':text}


class ChatTests(unittest.TestCase):
    def source(self):
        return {'rows':[speech(i,i*10000) for i in range(12)],
                'chat':[message(i,61000+i*300,'ㅋㅋㅋ' if i<8 else '규칙이 반대 아닌가요?') for i in range(10)],
                'include_chat':True}

    def test_cues_sparse_duplicate_diversity_preserve_source(self):
        source=self.source();before=copy.deepcopy(source);value=chat.attach(source)
        cue=value['clip_chat']['cues'][0]
        self.assertEqual(cue['anchor_id'],'S6');self.assertEqual(cue['messages'],10)
        self.assertEqual(cue['unique_texts'],2);self.assertGreater(cue['burst_ratio'],3)
        self.assertTrue(any(r['kind']=='consonant' for r in cue['repeats']))
        many=[message(i,61000+i,'ㅋㅋㅋ') for i in range(100)]+[message(101,61500,'정정 요청입니다')]
        self.assertIn('정정 요청입니다',[r['text'] for r in chat.sample(many)])
        self.assertEqual(source,before)

    def test_long_gap_overlapping_speech_and_offset_are_not_fabricated(self):
        source=self.source();source['rows']=[speech(0,0,1000),speech(1,100000)]
        result=chat.attach(source)['clip_chat']
        self.assertFalse(result['cues']);self.assertEqual(len(result['unanchored']),1)
        source['rows']=[speech(0,0,90000),speech(1,50000,51000)]
        self.assertEqual(chat.attach(source)['clip_chat']['cues'][0]['anchor_id'],'S0')
        source=self.source()
        for row in source['chat']:row['start_ms']+=1234;row['end_ms']+=1234
        cue=chat.attach(source)['clip_chat']['cues'][0]
        self.assertIn(cue['reaction_ms'],[r['start_ms'] for r in source['chat']])
        source['include_chat']=False;source['chat']=[]
        self.assertEqual(chat.attach(source)['clip_chat']['cues'],[])

    def test_long_video_all_cues_kept_and_no_author_payload(self):
        source={'rows':[speech(i,i*600000) for i in range(120)],'chat':[], 'include_chat':True}
        for i in range(120):
            source['chat'] += [message(i*4+j,i*600000+2000+j*100,'ㅎㅎㅎ') for j in range(4)]
        value=chat.attach(source);index=chat.Index(value)
        self.assertEqual(len(value['clip_chat']['cues']),120)
        seen=[]
        for row in source['rows']:seen += [c['id'] for c in index.packet([row])['cues']]
        self.assertEqual(len(set(seen)),120)
        self.assertNotIn('nickname',json.dumps(value));self.assertNotIn('user_id_hash',json.dumps(value))

    def test_scan_uses_chat_before_selection_and_keeps_quiet_speech(self):
        source=chat.attach(self.source());index=chat.Index(source)
        tokenizer=SimpleNamespace(count=lambda text:len(text)//8)
        owned,context,text=model.scan_plan(source['rows'],0,12,tokenizer,index)
        self.assertEqual(len(owned),12);self.assertIn('규칙이 반대',text)
        self.assertIn('chat_discovery',text);self.assertIn('S0',text)
        packet=index.packet(owned,context)
        seed={'start_id':'S6','peak_id':'S6','end_id':'S6','title':'정정하며 다시 설명','review_needed':True,
              'discovery':'chat','chat_evidence_ids':['C8']}
        self.assertTrue(model.validate_seeds({'clips':[seed]},context,owned,packet))
        for bad in (seed|{'peak_id':'C8'},seed|{'chat_evidence_ids':[]},seed|{'chat_evidence_ids':['C999']}):
            with self.assertRaises(ValueError):model.validate_seeds({'clips':[bad]},context,owned,packet)
        quiet=seed|{'start_id':'S0','peak_id':'S0','end_id':'S0','discovery':'speech','chat_evidence_ids':[]}
        self.assertTrue(model.validate_seeds({'clips':[quiet]},context,owned,packet))

    def test_budget_splits_instead_of_losing_cues(self):
        source=chat.attach(self.source());index=chat.Index(source);seen=[];cursor=0
        for row in source['rows']:row['text']='서로 다른 일반 발언 내용 '*80
        tokenizer=SimpleNamespace(count=lambda text:len(text)//2)
        while cursor<len(source['rows']):
            owned,context,text=model.scan_plan(source['rows'],cursor,len(source['rows']),tokenizer,index)
            self.assertLessEqual(tokenizer.count(text),4800)
            seen.extend(c['id'] for c in index.packet(owned,context)['cues']);cursor+=len(owned)
        self.assertEqual(set(seen),{c['id'] for c in source['clip_chat']['cues']})

    def test_delayed_chat_relation_and_legacy_restrictions(self):
        rows=[speech(0,60000,64000)];chats=[message(0,80000),message(1,95000)]
        part=clips.example(rows[0])|{'discovery':'chat','chat_relation':'uncertain','review_needed':True,
                                  'chat_summary':'뒤늦은 웃음 반응','chat_evidence_ids':['C0']}
        clips.validate({'clips':[part]},rows,rows,chats,chat_discovery=True)
        for change in ({'chat_evidence_ids':['C1']},{'chat_relation':'unrelated'},{'review_needed':False},{'chat_relation':'not_used'}):
            with self.assertRaises(ValueError):clips.validate({'clips':[part|change]},rows,rows,chats,chat_discovery=True)
        old={k:v for k,v in part.items() if k not in ('discovery','chat_relation')}
        with self.assertRaises(ValueError):clips.validate({'clips':[old]},rows,rows,chats)
        source=chat.attach({'rows':rows,'chat':chats,'include_chat':True})
        item=clips.render_items(source,[{'id':'one'}],{'one':{'clips':[part]}})[0]
        self.assertEqual(item['peak_ms'],60000);self.assertEqual(item['end_ms'],64000)
        self.assertEqual(item['chat_reactions'][0]['time_ms'],80000)

    def test_offset_once_and_private_identifiers_not_copied(self):
        source={'speech':[{'start_ms':60000,'end_ms':64000,'text':'설명하는 말'}],
                'chat':[{'offset_ms':60000+i*100,'text':'ㅎㅎ','nickname':'비공개 닉네임','user_id_hash':'secret'} for i in range(4)],
                'duration_ms':100000,'notes':[],'input_selection':{},'input_label':'전사'}
        with patch.object(context_input,'source',return_value=source):
            actual=chat.attach(data.snapshot(Path('/unused'),'1',{},True,2000))
        self.assertEqual(actual['chat'][0]['start_ms'],62000)
        self.assertEqual(actual['clip_chat']['cues'][0]['reaction_ms'],62000)
        dumped=json.dumps(actual,ensure_ascii=False)
        self.assertNotIn('비공개 닉네임',dumped);self.assertNotIn('secret',dumped)


class ExchangeChatTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_context_exchange.ExchangeTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.path=self.fixture.path
        self.fixture.source['chat']=[message(i,31500+i*100,'ㅋㅋ') for i in range(5)]

    def test_external_complete_chat_and_shared_discovery_delayed_evidence(self):
        bundle=self.fixture.create('clips',True);folder=exchange.folder(self.path,bundle['id'])
        saved=read_json(folder/'manifest.json');source=read_json(folder/'source.json')
        docs=list(exchange.documents(saved,source));self.assertIn(chat.RULES,bundle['prompt'])
        self.assertEqual(sum(len(d['chat']) for _,d in docs),5)
        self.assertEqual(sum(len(d['chat_discovery']['cues']) for _,d in docs),1)
        c,doc=next((c,d) for c,d in docs if any(r['id']=='S2' for r in d['utterances']))
        entry=copy.deepcopy(doc['output_example']);row=source['rows'][2]
        entry['clips']=[clips.example(row)|{'discovery':'chat','chat_relation':'uncertain','review_needed':True,
            'chat_summary':'발언 후 웃음 채팅','chat_evidence_ids':['C0']}]
        self.assertIn('C0',{r['id'] for r in doc['chat']+doc['chat_reference']})
        result=self.fixture.receive([entry]);value=data.result(self.path,'1',result['run'])
        self.assertFalse(value['stale']);self.assertEqual(value['items'][0]['chat_reactions'][0]['time_ms'],31500)
        self.assertEqual(value['items'][0]['discovery_info']['source'],'chat')
        self.assertEqual(self.fixture.old.read_bytes(),self.fixture.before)

    def test_old_export_keeps_old_window_and_bytes(self):
        bundle=self.fixture.create('clips',True);folder=exchange.folder(self.path,bundle['id'])
        saved=read_json(folder/'manifest.json');source=read_json(folder/'source.json')
        saved.pop('clip_chat_revision');source.pop('clip_chat');saved['fingerprint']=data.fingerprint(source)
        saved['request_prompt']='이전 작업서';saved['work_order']='이전 전체 작업서'
        save_json(folder/'manifest.json',saved);save_json(folder/'source.json',source)
        before=(folder/'source.json').read_bytes()
        c,doc=next((c,d) for c,d in exchange.documents(saved,source) if any(r['id']=='S2' for r in d['utterances']))
        self.assertNotIn('chat_discovery',doc);self.assertNotIn('discovery',doc['output_example']['clips'][0])
        entry=doc['output_example'];entry['clips']=[clips.example(source['rows'][2])|{'chat_summary':'늦은 반응','chat_evidence_ids':['C0']}]
        with self.assertRaises(ValueError):exchange.validate_entry(saved,source,entry)
        self.assertEqual(exchange.bundle(self.path,bundle['id'])['prompt'],'이전 전체 작업서')
        from archive.context_exchange_zip import work_order
        ancient={k:v for k,v in saved.items() if k not in ('request_prompt','work_order')}
        fallback=work_order(ancient)
        self.assertNotIn(chat.RULES,fallback)
        self.assertIn('후보 시작 이상, 끝 발언 종료 미만',fallback)
        self.assertEqual((folder/'source.json').read_bytes(),before)

    def test_chat_off_excludes_all_discovery_content(self):
        bundle=self.fixture.create('clips',False);folder=exchange.folder(self.path,bundle['id'])
        saved=read_json(folder/'manifest.json');source=read_json(folder/'source.json')
        for _,doc in exchange.documents(saved,source):
            self.assertEqual(doc['chat'],[]);self.assertEqual(doc['chat_reference'],[])
            self.assertEqual(doc['chat_discovery']['cues'],[])
        self.assertFalse(data.stale(self.path,'1',saved))

    def test_local_scan_review_partial_recovery_preserves_previous_version(self):
        prepared=local.prepare(self.path,'1','clips',{'selection':self.fixture.source['input_selection']})
        def job(value):
            result=SimpleNamespace(input=value,path=self.path,vod='1',value={'runs':[]},stop=threading.Event(),
                tokenizer=None,check_engine=lambda:None,make_tokenizer=lambda:SimpleNamespace(count=lambda t:len(t)//10))
            def update(**kwargs):result.value.update(kwargs);save_json(self.path/'context/state.json',result.value)
            result.update=update
            return result
        calls=[];fail=[True]
        def infer(job,folder,key,value,text,schema,validate):
            calls.append(key)
            if key=='clips-scan':
                self.assertIn('chat_discovery',text);self.assertIn('ㅋㅋ',text)
                raw={'clips':[{'start_id':'S3','peak_id':'S3','end_id':'S3','title':'실제 발언','review_needed':True,
                               'discovery':'chat','chat_evidence_ids':['C0']}]}
            else:
                self.assertIn('C0',[r['id'] for r in value['chat_sample']])
                if fail[0]:raise ValueError('검증용 일시 오류')
                raw={'clips':[clips.example(self.fixture.source['rows'][3])|{'discovery':'chat','chat_relation':'uncertain',
                    'review_needed':True,'chat_summary':'웃음 채팅','chat_evidence_ids':['C0']}]}
            validate(raw);return raw
        with patch.object(local.model,'call',side_effect=infer):self.assertEqual(local.run(job(prepared)),1)
        first=prepared['saved']['id'];file=self.path/'context/runs'/first/'work.json';before=file.read_bytes()
        fail[0]=False;calls.clear();resumed=local.prepare(self.path,'1','clips-resume',{'run':first})
        self.assertNotEqual(resumed['saved']['id'],first)
        with patch.object(local.model,'call',side_effect=infer):self.assertEqual(local.run(job(resumed)),0)
        self.assertEqual(calls,['clips-review']);self.assertEqual(file.read_bytes(),before)
        self.assertEqual(self.fixture.old.read_bytes(),self.fixture.before)


if __name__=='__main__':unittest.main()
