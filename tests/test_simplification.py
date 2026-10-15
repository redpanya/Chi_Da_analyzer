"""특정 방송 내용과 무관한 옵션 격리·부분 실패·상대 반응·초안 보존 계약."""
import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from archive import speech_options, speech, speech_model, speech_store, speech_media, speech_recognition, speech_vad
from archive import analysis, context_comments, context_job
from archive.storage import ProjectLock, Conflict, save_json
import test_speech
import test_context_dialogue


class SpeechOptionTests(unittest.TestCase):
    setUp = test_speech.SpeechTests.setUp
    tearDown = test_speech.SpeechTests.tearDown
    audio = test_speech.SpeechTests.audio
    fake_engine = test_speech.SpeechTests.fake_engine

    def run_options(self, options):
        with ProjectLock(self.path) as lock, patch.object(speech_model,'verify',return_value=self.root/'model'), patch.object(speech_model,'engine_version',return_value=('engine','test')), patch.object(speech_media,'process',side_effect=self.fake_engine):
            speech.transcribe(self.path,self.data,'ko',threading.Event(),lock,lambda **v:speech_store.update(self.path,**v),options=options)
        return speech_store.manifest(self.path)

    def test_options_change_creates_runs_and_preserves_corrections(self):
        self.audio()
        base=self.run_options({})
        speech_store.correct(self.path,base['id'],'00000-00000','사용자가 확인한 원문')
        folder=speech_media.local(self.path,f"runs/{base['id']}")
        before={p.name:p.read_bytes() for p in folder.glob('*.json')}
        sensitive=self.run_options({'vad':'sensitive'})
        hint=self.run_options({'prompt':'임의의 사용자 용어'})
        self.assertEqual(len({base['id'],sensitive['id'],hint['id']}),3)
        self.assertEqual({p.name:p.read_bytes() for p in folder.glob('*.json')},before)
        self.assertEqual(self.run_options({})['id'],base['id'])
        self.assertEqual(speech_store.result(self.path)['items'][0]['text'],'사용자가 확인한 원문')
        self.assertEqual(speech_store.view(self.path,self.data)['transcript']['asr_options'],{'vad':'standard','prompt':''})

    def test_off_requires_no_vad_model(self):
        self.audio()
        with patch.object(speech_vad,'prepare',side_effect=AssertionError('VAD 모델 불필요')):
            result=self.run_options({'vad':'off'})
        self.assertTrue(result['complete'])

    def test_invalid_options(self):
        for value in ({'vad':'unknown'},{'vad':[]},{'prompt':None},{'prompt':'x'*501},{'prompt':'a\0b'},{'extra':True},[]):
            with self.assertRaises(ValueError):speech_options.validate(value)


class RecognitionOptionsTests(unittest.TestCase):
    def test_off_windows_prompt_and_offsets_without_detector(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            def engine(args,*_):
                self.assertEqual(args[args.index('--prompt')+1],'용어')
                for i,arg in enumerate(args):
                    if arg=='-of':save_json(Path(args[i+1]).with_suffix('.json'),{'transcription':[{'text':'발화','offsets':{'from':0,'to':500}}]})
            def chunk(_source,target,*_):target.touch()
            with patch.object(speech_vad,'detect',side_effect=AssertionError('검출 호출 금지')),patch.object(speech_media,'process',side_effect=engine),patch.object(speech_media,'chunk_audio',side_effect=chunk):
                result=speech_recognition.recognize('engine','model','audio',folder,0,65000,'ko',None,threading.Event(),None,{'vad':'off','prompt':'용어'})
            self.assertEqual(result['windows'],[[0,30000],[30000,60000],[60000,65000]])
            self.assertEqual([r['offsets']['from'] for r in result['transcription']],[0,30000,60000])
            self.assertTrue((folder/'00000-raw.json').exists())


class ReactionTests(unittest.TestCase):
    def test_relative_extremes_union_and_no_reaction(self):
        rows=[{'offset_ms':1000+i*100,'text':'좋다 ㅋㅋ'} for i in range(3)]
        rows += [{'offset_ms':30000+i*100,'text':'다른말 ㅎㅎ'} for i in range(9)]
        before=copy.deepcopy(rows)
        result=analysis.analyze(rows,50000,True,{})['reaction_index']
        self.assertEqual(rows,before)
        self.assertEqual(result['min'],.3);self.assertEqual(result['max'],.9)
        self.assertEqual(min(p['index'] for p in result['points']),1)
        self.assertEqual(max(p['index'] for p in result['points']),10)
        self.assertEqual(analysis.analyze([],10000,True,{})['reaction_index']['points'],[])
        equal=analysis.analyze(rows[:3],10000,True,{})['reaction_index']
        self.assertFalse(equal['comparable']);self.assertEqual({p['index'] for p in equal['points']},{1})
        # 이름과 절대 시각이 달라도 같은 구조의 창은 같은 상대 지수다.
        moved=[dict(r,offset_ms=r['offset_ms']+100000,text=r['text'].replace('좋다','훌륭')) for r in rows]
        self.assertEqual([p['index'] for p in result['points']], [p['index'] for p in analysis.analyze(moved,150000,True,{})['reaction_index']['points']])

    def test_partial_tail_is_not_scored_as_complete_window(self):
        rows=[{'offset_ms':1000+i*100,'text':'반복'} for i in range(3)]
        self.assertEqual(analysis.analyze(rows,50000,False,{})['reaction_index']['points'],[])


class CommentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name);self.run='a'*32
        save_json(self.path/'context/state.json',{'runs':[{'id':self.run}],'run':self.run})
        self.original=self.path/'context/runs'/self.run/'result.json';save_json(self.original,{'원본':'변경 금지'})

    def test_persist_conflict_and_original_untouched(self):
        before=self.original.read_bytes()
        draft=context_comments.read(self.path,self.run)|{'text':'00:03:02 직접 수정한 댓글','selected':['story-1'],'edited':True,'basis':'원래 초안'}
        saved=context_comments.save(self.path,self.run,draft)
        self.assertEqual(context_comments.read(self.path,self.run),saved)
        self.assertEqual(saved['revision'],1)
        with self.assertRaises(Conflict):context_comments.save(self.path,self.run,draft)
        self.assertEqual(self.original.read_bytes(),before)
        bad=saved|{'text':'a'*50001}
        with self.assertRaises(ValueError):context_comments.save(self.path,self.run,bad)
        self.assertEqual(context_comments.read(self.path,self.run),saved)
        with self.assertRaises(ValueError):context_comments.save(self.path,'../other',saved)

    def test_symlink_rejected(self):
        folder=self.path/'context/comments';folder.symlink_to(self.path/'context/runs')
        with self.assertRaises(ValueError):context_comments.save(self.path,self.run,{'revision':0,'text':'','selected':[],'edited':False,'basis':''})


class ContinuationTests(unittest.TestCase):
    setUp = test_context_dialogue.DialogueTests.setUp
    job = test_context_dialogue.DialogueTests.job
    infer = test_context_dialogue.DialogueTests.infer
    execute = test_context_dialogue.DialogueTests.execute
    def test_continues_after_three_content_failures_then_success(self):
        self.source=test_context_dialogue.source(15,450000)
        def infer(value,folder,*args):
            if 'rows' in value and int(value['rows'][0]['id'][1:])<9:
                folder.mkdir(parents=True);return {},1
            return self.infer(value,folder,*args)
        result=self.execute(self.job(),infer)
        self.assertEqual(result['done'],15);self.assertEqual(result['item_failures'],3)
        self.assertTrue(any(not r.get('failed') and not r.get('gap') for r in result['items']))
        self.assertEqual(result['phase'],'done')

    def test_fatal_engine_stops_without_marking_remaining_as_failed(self):
        result=self.execute(self.job(),lambda *_:(_ for _ in ()).throw(context_job.FatalEngineError('프로세스 종료')))
        self.assertEqual(context_job.state(self.path)['state'],'error');self.assertEqual(result['done'],0)
        self.assertEqual(result['item_failures'],0)
