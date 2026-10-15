"""원본 보존·국소 치환·변조 거부·부분 실패와 체크포인트 검사."""
import copy
import tempfile
import threading
import unittest
from pathlib import Path
from archive import context_evidence as ev, transcript_correction as correction
from archive.transcript_correction_job import process

class Counter:
    def count(self,text): return len(text)//3

class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.source={'duration_ms':30000,'chat':[{'text':'채팅 전용 정보'}], 'speech':[
            {'id':'원본1','start_ms':1000,'end_ms':2000,'speaker_name':'가화자','text':'우체국에 갔어요.','raw_start_ms':950},
            {'id':'원본2','start_ms':3000,'end_ms':5000,'speaker_name':'화자인식 실패','text':'우채국에 안 갔어요.'}]}
        self.rows=ev.speech(self.source)
        self.edit={'id':'S1','before':'우채국','after':'우체국','reason':'앞 발언의 같은 대상 표기'}
        self.raw={'edits':[self.edit],'unresolved':[]}
    def test_only_text_changes_and_original_is_untouched(self):
        before=copy.deepcopy(self.source)
        value,report=correction.apply(self.source,self.raw,self.rows)
        self.assertEqual(self.source,before)
        self.assertEqual(value['speech'][1]['text'],'우체국에 안 갔어요.')
        correction.verify_metadata(before,value)
        self.assertEqual(len(report['accepted']),1)
        value['speech'][1]['speaker_name']='가화자'
        with self.assertRaises(ValueError): correction.verify_metadata(before,value)
    def test_metadata_in_response_and_unknown_id_are_rejected_individually(self):
        invalid=[dict(self.edit,start_ms=999),dict(self.edit,id='S99'),dict(self.edit,before='없는문자')]
        value,report=correction.apply(self.source,{'edits':invalid+[self.edit],'unresolved':[]},self.rows)
        self.assertEqual(len(report['accepted']),1);self.assertEqual(len(report['rejected']),3)
        self.assertEqual(value['speech'][1]['start_ms'],3000)
    def test_overlapping_and_duplicate_spans_do_not_depend_on_order(self):
        other=dict(self.edit,before='우채국에',after='우체국에')
        for edits in ([self.edit,other],[other,self.edit],[self.edit,self.edit]):
            value,report=correction.apply(self.source,{'edits':edits,'unresolved':[]},self.rows)
            self.assertEqual(value,self.source);self.assertEqual(len(report['rejected']),2)
    def test_ambiguous_repeated_phrase_and_empty_replacement_are_rejected(self):
        self.source['speech'][1]['text']='우채국 우채국'
        rows=ev.speech(self.source)
        for edit in (self.edit,dict(self.edit,after='')):
            value,report=correction.apply(self.source,{'edits':[edit],'unresolved':[]},rows)
            self.assertEqual(value,self.source);self.assertTrue(report['rejected'])
    def test_nonoverlapping_edits_apply_against_original_positions(self):
        raw={'edits':[self.edit,dict(self.edit,before='갔어요',after='가봤어요')],'unresolved':[]}
        value,report=correction.apply(self.source,raw,self.rows)
        self.assertEqual(value['speech'][1]['text'],'우체국에 안 가봤어요.')
        self.assertEqual(len(report['accepted']),2)
    def test_prompt_keeps_absolute_times_and_speaker_but_excludes_chat(self):
        value=correction.payload(self.rows,3532419)
        self.assertEqual(value['발언'][0]['start_ms'],3533419)
        self.assertEqual(value['발언'][1]['speaker'],'화자인식 실패')
        self.assertNotIn('채팅 전용 정보',correction.prompt(self.rows))
    def test_retry_checkpoint_and_changed_source_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            calls=[]
            def infer(*args):
                calls.append(args)
                if len(calls)==1:return {'wrong':True},0
                return self.raw,0
            result,report=process(self.source,Path(folder),infer,Counter(),threading.Event(),{'model':'시험'})
            self.assertEqual(len(calls),2);self.assertTrue(report['complete'])
            self.assertEqual(result['speech'][1]['text'],'우체국에 안 갔어요.')
            process(self.source,Path(folder),infer,Counter(),threading.Event(),{'model':'시험'})
            self.assertEqual(len(calls),2)
            with self.assertRaises(ValueError):
                process(self.source,Path(folder),infer,Counter(),threading.Event(),{'model':'다른 모델'})
    def test_failed_correction_preserves_original_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            value,report=process(self.source,Path(folder),lambda *args:({'wrong':True},0),Counter(),threading.Event(),{})
            self.assertEqual(value,self.source);self.assertFalse(report['complete'])
            self.assertTrue(report['batches'][0]['failed'])

if __name__=='__main__':unittest.main()
