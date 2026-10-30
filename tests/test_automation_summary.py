"""입력·모드·정책 일치 여부와 보존을 검사한다. 실제 모델은 실행하지 않는다."""
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
import threading

from archive import context_guidance, context_background, context_clip_chat
from archive import automation_summary as summary, context_server, context_exchange_data, context_clip_model, context_full, context_model
from archive.context_adaptive import REVISION
from archive.storage import save_json


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.stack = ExitStack()
        self.addCleanup(self.tmp.cleanup); self.addCleanup(self.stack.close)
        self.runs = []
        self.stack.enter_context(patch('archive.context_job.state', side_effect=lambda p:{'runs':self.runs,'full_run':'another-mode'}))
        self.stack.enter_context(patch('archive.speech_store.state', return_value={'run':'speech-1'}))
        self.voice = self.stack.enter_context(patch('archive.voice_store.result', return_value=None))
        self.stack.enter_context(patch('archive.voice_store.current', return_value=True))
        context_background.save(self.path,'방송 배경')
        self.source = self.stack.enter_context(patch('archive.context_exchange_data.snapshot', return_value={'rows':['자료']}))
        self.full_source = self.stack.enter_context(patch('archive.context_full.current_source', side_effect=lambda *a:context_guidance.attach({'speech':['자료']},a[5])))
        self.settings = {'mode':'analysis', 'thinking':True, 'speakers_enabled':False}

    def saved(self, mode, complete=True, **extra):
        index = str(len(self.runs)+1)*32
        scope = {'summary':'full','timestamps':'timestamps','clips':'clips-local'}[mode]
        self.runs.append({'id':index,'scope':scope})
        guidance=context_guidance.prepare(self.path,'detail' if mode=='summary' else mode,self.settings)
        saved = dict(analysis_guidance=guidance,id=index, complete=complete, scope=scope, origin='local', revision=context_exchange_data.REVISION,
                     version=context_full.VERSION, pipeline_revision=REVISION, policy_revision=context_clip_model.REVISION,
                     model=context_model.DEFAULT_NAME, model_sha256=context_model.spec()['sha256'],
                     inference=context_server.profile(True), input_selection={'transcript_run':'speech-1','speaker_run':None},
                     fingerprint=context_full.fingerprint(context_guidance.attach({'speech':['자료']},guidance)) if mode=='summary' else context_exchange_data.fingerprint(context_guidance.attach(context_clip_chat.attach({'rows':['자료']}) if mode=='clips' else {'rows':['자료']},guidance))) | extra
        file = summary.context_job.local(self.path, f'runs/{index}/result.json')
        save_json(file, saved)
        return file

    def test_new_requests_and_voice_selection(self):
        for stage, action in [('summary','whole'),('timestamps','timestamps'),('clips','clips')]:
            result, values = summary.request(self.path,'1',stage,self.settings)
            self.assertEqual(result,action)
            self.assertEqual(values['selection'],{'transcript_run':'speech-1','speaker_run':None})
            self.assertEqual(values['background'],'방송 배경')
            self.assertEqual(values['custom_request'],'')
            self.assertEqual(values.get('include_chat'),True if stage=='clips' else None)
        self.voice.return_value={'id':'voice-1'}
        _, values = summary.request(self.path,'1','clips',self.settings|{'speakers_enabled':True})
        self.assertEqual(values['selection']['speaker_run'],'voice-1')
        with patch('archive.context_background.read') as background:
            _, values=summary.request(self.path,'1','summary',self.settings|{'background':'새 설명'})
            background.assert_not_called()
            self.assertEqual(values['background'],'새 설명')

    def test_completed_modes_reuse_without_changing_files(self):
        for stage in ['summary','timestamps','clips']:
            file = self.saved(stage); before=file.read_bytes()
            self.assertIsNone(summary.request(self.path,'1',stage,self.settings)[0])
            self.assertEqual(file.read_bytes(),before)
        self.assertTrue(self.source.call_args.kwargs['include_chat'])

    def test_resume_uses_explicit_mode_run_and_preserves_file(self):
        for stage, action, target in [('summary','resume','context_full'),('timestamps','timestamps-resume','context_timestamps'),('clips','clips-resume','context_clips_local')]:
            self.runs.clear();file=self.saved(stage,False);before=file.read_bytes()
            with patch(f'archive.{target}.prepare', return_value={}) as prepare:
                actual, values=summary.request(self.path,'1',stage,self.settings)
                self.assertEqual(actual,action);self.assertEqual(values,{'run':self.runs[-1]['id']})
                prepare.assert_called_once()
            self.assertEqual(file.read_bytes(),before)

    def test_changed_input_thinking_policy_external_or_bad_checkpoint_is_not_resumed(self):
        changes=[{'analysis_guidance':None},{'analysis_guidance':{'revision':0}},{'fingerprint':'changed'},{'inference':context_server.profile(False)},
                 {'policy_revision':-1},{'origin':'external'}, {'input_selection':{'transcript_run':'other','speaker_run':None}}]
        for extra in changes:
            self.runs.clear();self.saved('clips',False,**extra)
            self.assertEqual(summary.request(self.path,'1','clips',self.settings)[0],'clips')
        self.runs.clear();self.saved('clips',False)
        with patch('archive.context_clips_local.prepare',side_effect=ValueError('체크포인트 손상')):
            self.assertEqual(summary.request(self.path,'1','clips',self.settings)[0],'clips')

    def test_matching_complete_preferred_to_later_incomplete(self):
        self.saved('timestamps');self.saved('timestamps',False)
        with patch('archive.context_timestamps.prepare',return_value={}):
            self.assertIsNone(summary.request(self.path,'1','timestamps',self.settings)[0])

    def test_execution_dispatch_partial_status_and_reuse_report(self):
        from archive.automation_steps import execute
        manager=SimpleNamespace(context_start=Mock(), context_job=SimpleNamespace(closed=True), reports=Mock())
        queue=SimpleNamespace(manager=manager,root=str(self.path),stop=threading.Event())
        entry={'vod':'1','options':self.settings}
        with patch('archive.automation_steps.project_path',return_value=self.path), patch('archive.automation_steps.load_project',return_value={}), patch('archive.automation_steps.ready'):
            for stage, action in [('summary','whole'),('timestamps','timestamps'),('clips','clips')]:
                with patch('archive.context_job.state',return_value={'runs':[],'state':'review'}):
                    self.assertEqual(execute(queue,entry,stage),'partial')
                self.assertEqual(manager.context_start.call_args.args[2],action)
            self.saved('clips');manager.context_start.reset_mock()
            self.assertEqual(execute(queue,entry,'clips'),'reused')
            manager.context_start.assert_not_called()
            manager.reports.skipped.assert_called_once_with(self.path,'summary',settings={'summary_mode':'clips'})

    def test_pause_during_summary_keeps_next_mode_unstarted(self):
        from archive.automation_steps import execute, Paused
        manager=SimpleNamespace(context_start=Mock(),context_job=SimpleNamespace(closed=True),reports=Mock())
        stop=threading.Event();stop.set()
        queue=SimpleNamespace(manager=manager,root=str(self.path),stop=stop)
        with patch('archive.automation_steps.project_path',return_value=self.path), patch('archive.automation_steps.load_project',return_value={}), patch('archive.automation_steps.ready'):
            with self.assertRaises(Paused):execute(queue,{'vod':'1','options':self.settings},'timestamps')
        self.assertEqual(manager.context_start.call_count,1)


if __name__ == '__main__': unittest.main()
