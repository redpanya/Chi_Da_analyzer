"""동률 채팅 통계와 구버전 지문을 원문 변경과 구분한다."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from archive import context_clip_chat as chat, context_exchange_data as data
from archive.storage import save_json


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.path=Path(tmp.name)
        self.source={'rows':[{'id':'S0','start_ms':0,'end_ms':10000,'text':'방송 이야기',
                              'speaker_tag':'?','corrected':False}],
                     'chat':[{'id':f'C{i}','start_ms':1000+i,'end_ms':1000+i,
                              'text':'alpha bravo charlie delta echo foxtrot golf hotel ㅋㅋ ㅎㅎ'} for i in range(5)],
                     'include_chat':True,'chat_offset_ms':0,'duration_ms':10000,
                     'input_selection':{'transcript_run':'b'*32,'speaker_run':None},'input_label':'검증 전사',
                     'rejected':[],'analysis_guidance':{'mode':'clips','revision':1}}
        self.previous=chat.attach(copy.deepcopy(self.source))
        # 과거 실행에서는 동률 6개 제한의 구성도 집합 순서에 따라 달라질 수 있었다.
        self.previous['clip_chat']['cues'][0]['repeats']=[
            {'kind':'word','term':term,'messages':5} for term in ('hotel','golf','foxtrot','echo','delta','charlie')]
        self.saved={'id':'a'*32,'fingerprint':data.fingerprint(self.previous),'clip_chat_revision':chat.REVISION,
                    **{key:self.source[key] for key in ('input_selection','include_chat','chat_offset_ms','analysis_guidance')}}
        mock=patch.object(data,'snapshot',side_effect=lambda *args:copy.deepcopy(self.source))
        mock.start();self.addCleanup(mock.stop)

    def write_previous(self, saved=None):
        saved=saved or self.saved
        group='runs' if saved.get('origin') in ('local','external') else 'exchange'
        file=self.path/'context'/group/saved['id']/'source.json'
        save_json(file,self.previous)
        return file

    def test_repeat_ties_are_stable_across_processes_including_cutoff(self):
        script='import json,sys;from archive import context_clip_chat as c,context_exchange_data as d;print(d.fingerprint(c.attach(json.load(sys.stdin))))'
        hashes=[subprocess.check_output([sys.executable,'-c',script],input=json.dumps(self.source),text=True,
                    cwd=Path(__file__).resolve().parents[1],env=os.environ|{'PYTHONHASHSEED':str(seed)}).strip()
                for seed in (1,2,3)]
        self.assertEqual(len(set(hashes)),1)
        cue=chat.attach(self.source)['clip_chat']['cues'][0]
        self.assertEqual(len(cue['repeats']),6)
        self.assertEqual(cue['repeats'],sorted(cue['repeats'],key=lambda r:(-r['messages'],r['kind'],r['term'])))

    def test_legacy_exports_and_local_external_runs_recover_without_writes(self):
        self.assertNotEqual(data.fingerprint(chat.attach(self.source)),self.saved['fingerprint'])
        for origin in (None,'local','external'):
            saved=self.saved|({'origin':origin} if origin else {})
            file=self.write_previous(saved);before=file.read_bytes();metadata=copy.deepcopy(saved)
            with self.subTest(origin=origin):
                self.assertFalse(data.stale(self.path,'1',saved))
                self.assertEqual(file.read_bytes(),before)
                self.assertEqual(saved,metadata)

    def test_actual_input_changes_still_block(self):
        self.write_previous();original=copy.deepcopy(self.source)
        changes=[('rows',0,'text','변경한 발언'),('rows',0,'start_ms',50),('rows',0,'corrected',True),
                 ('rows',0,'speaker_tag','다른 화자'),('chat',0,'text','변경한 채팅'),('chat',0,'start_ms',2000)]
        for group,index,key,value in changes:
            self.source=copy.deepcopy(original);self.source[group][index][key]=value
            with self.subTest(field=(group,key)):self.assertTrue(data.stale(self.path,'1',self.saved))
        for key,value in (('duration_ms',11000),('chat_offset_ms',100),
                          ('input_selection',{'transcript_run':'c'*32,'speaker_run':None}),('chat',original['chat'][:-1])):
            self.source=copy.deepcopy(original);self.source[key]=value
            with self.subTest(field=key):self.assertTrue(data.stale(self.path,'1',self.saved))

    def test_missing_damaged_or_changed_revision_does_not_bypass_guard(self):
        self.assertTrue(data.stale(self.path,'1',self.saved))
        file=self.write_previous();damaged=copy.deepcopy(self.previous);damaged['rows'][0]['text']='손상된 원문'
        save_json(file,damaged)
        self.assertTrue(data.stale(self.path,'1',self.saved))
        save_json(file,[])
        self.assertTrue(data.stale(self.path,'1',self.saved))
        self.write_previous()
        self.assertTrue(data.stale(self.path,'1',self.saved|{'clip_chat_revision':chat.REVISION+1}))
        self.assertTrue(data.stale(self.path,'1',self.saved|{'id':'../outside'}))

    def test_current_hash_and_legacy_without_chat_keep_existing_contract(self):
        current=self.saved|{'fingerprint':data.fingerprint(chat.attach(self.source))}
        self.assertFalse(data.stale(self.path,'1',current))
        legacy={k:v for k,v in self.saved.items() if k!='clip_chat_revision'}
        legacy['fingerprint']=data.fingerprint(self.source)
        self.assertFalse(data.stale(self.path,'1',legacy))
        self.source['rows'][0]['text']='실제 변경'
        self.assertTrue(data.stale(self.path,'1',legacy))


if __name__=='__main__':unittest.main()
