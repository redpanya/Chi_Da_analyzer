"""특정 VOD와 무관한 다중 입력·삭제 범위·복구·다른 OS 기록 검증."""
import copy
import shutil
import unittest
from unittest.mock import patch

from archive import analysis_inputs as inputs, speech_store as speech, voice_store as voices
from archive import context_full as full, context_job, result_deletion, compute
from archive.jobs import Manager
from archive.storage import Conflict, ProjectLock, read_json, save_json
import test_speech
from test_context_full import output


class InputTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_speech.SpeechTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.path=self.fixture.path
        self.fixture.audio()
        self.fixture.transcribe()
        self.first=speech.manifest(self.path)
        self.second=copy.deepcopy(self.first)
        self.second.update(id='b'*32, language='en', asr_options={'vad':'off','prompt':'이름'})
        shutil.copytree(speech.local(self.path,f"runs/{self.first['id']}"),
                        speech.local(self.path,f"runs/{self.second['id']}"))
        save_json(speech.local(self.path,f"runs/{self.second['id']}/manifest.json"),self.second)
        self.row=speech.segments(self.path,self.first)[0]
        speech.correct(self.path,self.first['id'],self.row['id'],'사용자가 보존한 교정')
        speech.select(self.path,self.second['id'])
        self.voice='c'*32
        save_json(voices.local(self.path,f'runs/{self.voice}/result.json'),{
            'id':self.voice,'created_at':'2026-10-20','backend_label':'검증 엔진',
            'transcript_run':self.first['id'],'audio_sha256':self.first['audio_sha256'],
            'speakers':{'speaker_1':'A화자'},'assignments':{
                self.row['id']:{'speaker':'speaker_1','status':'assigned','reason':''}},'turns':[]})
        save_json(voices.local(self.path,f'runs/{self.voice}/edits.json'),{
            'revision':1,'names':{'speaker_1':'사용자 이름'},'speakers':{},'assignments':{},'history':[]})
        voices.update(self.path,run=self.voice,runs=[self.voice],state='complete')
        self.selection={'transcript_run':self.first['id'],'speaker_run':self.voice}

    def chosen(self, **values):
        return inputs.selected(self.path,self.fixture.data,self.selection|values)

    def test_named_catalog_and_explicit_selection_keep_other_pages(self):
        before=speech.local(self.path,'state.json').read_bytes()
        catalog=inputs.catalog(self.path)
        self.assertEqual(len(catalog['transcripts']),2)
        self.assertIn('발화 검출 끄기',next(r for r in catalog['transcripts'] if r['id']==self.second['id'])['label'])
        self.assertIn('검증 엔진',catalog['speakers'][0]['label'])
        row=self.chosen()['speech'][0]
        self.assertEqual(row['text'],'사용자가 보존한 교정')
        self.assertEqual(row['speaker_name'],'사용자 이름')
        self.assertEqual(row['start_ms'],self.row['start_ms'])
        self.assertNotIn('speaker_name',self.chosen(speaker_run=None)['speech'][0])
        self.assertEqual(speech.local(self.path,'state.json').read_bytes(),before)
        with self.assertRaisesRegex(ValueError,'연결된 분석'):
            self.chosen(transcript_run=self.second['id'])
        with self.assertRaises(ValueError):self.chosen(transcript_run='../elsewhere')
        changed=full.current_source(self.path,'1',0,selection=self.selection)
        speech.select(self.path,self.first['id'])
        self.assertEqual(full.fingerprint(changed),full.fingerprint(full.current_source(self.path,'1',0,selection=self.selection)))
        self.assertEqual(full.fingerprint(changed),full.fingerprint(changed|{'input_label':'표시 설명만 변경'}))

    def test_resume_uses_saved_inputs_and_deleted_input_keeps_summary(self):
        # 추론 품질이 아니라 저장·이어하기 계약을 검사하는 경량 엔진 대역이다.
        with patch.object(full,'VERSION',3):
            prepared=full.prepare(self.path,'1','whole',{'selection':self.selection})
            job=context_job.ContextJob(self.path,'1',ProjectLock(self.path),'whole',prepared)
            def stop(value,*args):
                job.cancel()
                return output(value),0
            with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=stop):
                job.run()
            id=context_job.state(self.path)['full_run']
            file=context_job.local(self.path,f'runs/{id}/result.json')
            before=file.read_bytes()
            resumed=full.prepare(self.path,'1','resume',{'run':id,'selection':{'transcript_run':self.second['id'],'speaker_run':None}})
            self.assertEqual(resumed['source']['input_selection'],self.selection)
            self.assertFalse(full.result(self.path,'1',id)['stale'])
            with patch('archive.deletion.trash_path',side_effect=self.trash):
                result_deletion.voices(self.path,self.voice)
            self.assertTrue(full.result(self.path,'1',id)['stale'])
            self.assertEqual(file.read_bytes(),before)
            with self.assertRaises(ValueError):full.prepare(self.path,'1','resume',{'run':id})

    def test_current_pipeline_stores_selection_and_detects_manual_input_changes(self):
        import test_context_adaptive
        from test_context_dialogue import FakeTokenizer
        self.calls=[]
        prepared=full.prepare(self.path,'1','whole',{'selection':self.selection})
        job=context_job.ContextJob(self.path,'1',ProjectLock(self.path),'whole',prepared)
        with patch.object(job,'check_engine'), patch('archive.context_tokens.Tokenizer',FakeTokenizer), \
             patch.object(job,'infer_value',side_effect=lambda *a:test_context_adaptive.AdaptiveTests.infer(self,*a)):
            job.run()
        value=context_job.result(self.path,'1')
        self.assertEqual(value['version'],10)
        self.assertEqual(value['input_selection'],self.selection)
        self.assertFalse(value['stale'])
        source=read_json(context_job.local(self.path,f"runs/{value['id']}/source.json"))
        self.assertEqual(source['speech'][0]['speaker_name'],'사용자 이름')
        self.assertEqual(source['speech'][0]['text'],'사용자가 보존한 교정')
        speech.select(self.path,self.first['id'])
        speech.correct(self.path,self.first['id'],self.row['id'],'다음 수동 교정')
        self.assertTrue(context_job.result(self.path,'1')['stale'])

    def trash(self,folder):
        target=self.fixture.root/'휴지통'/folder.name
        target.parent.mkdir(exist_ok=True)
        shutil.move(str(folder),target)

    def test_delete_only_chosen_version_and_preserve_originals_exports_summary(self):
        original=self.fixture.video.read_bytes()
        audio=speech.local(self.path,speech.state(self.path)['audio']['file'])
        wav=audio.read_bytes()
        kept=speech.local(self.path,f"runs/{self.second['id']}/manifest.json").read_bytes()
        with self.assertRaisesRegex(Conflict,'화자 분석'):
            result_deletion.speech(self.path,self.first['id'])
        exported=speech.export(self.path)
        export=speech.local(self.path,exported['json']); export_bytes=export.read_bytes()
        with patch('archive.deletion.trash_path',side_effect=self.trash):
            result_deletion.voices(self.path,self.voice)
            result_deletion.speech(self.path,self.first['id'])
        self.assertEqual(self.fixture.video.read_bytes(),original)
        self.assertEqual(audio.read_bytes(),wav)
        self.assertEqual(export.read_bytes(),export_bytes)
        self.assertEqual(speech.local(self.path,f"runs/{self.second['id']}/manifest.json").read_bytes(),kept)
        self.assertEqual(speech.state(self.path)['run'],self.second['id'])
        self.assertEqual([r['id'] for r in inputs.transcripts(self.path)],[self.second['id']])
        self.assertIsNone(voices.result(self.path))
        with self.assertRaises(ValueError):self.chosen()
        with self.assertRaises(ValueError):result_deletion.voices(self.path,'../outside')

    def test_delete_failure_rolls_back_and_running_job_blocks_mutation(self):
        state=voices.local(self.path,'state.json').read_bytes()
        with patch('archive.deletion.trash_path',side_effect=OSError('사용 중인 볼륨')):
            with self.assertRaises(OSError):result_deletion.voices(self.path,self.voice)
        self.assertEqual(voices.local(self.path,'state.json').read_bytes(),state)
        manager=Manager(self.fixture.root)
        manager.analysis_path=self.path
        with patch('archive.deletion.trash_path') as trash:
            with self.assertRaises(Conflict):manager.voices_edit(str(self.fixture.root),'1','delete',{'run':self.voice})
            with self.assertRaises(Conflict):manager.speech_edit(str(self.fixture.root),'1','delete',run=self.second['id'])
            trash.assert_not_called()

    def test_cross_platform_compute_view_does_not_modify_saved_record(self):
        speech.update(self.path,action='transcribe',compute={'backend':'cpu','note':'CPU · NVIDIA GTX 1060'})
        file=speech.local(self.path,'state.json');before=file.read_bytes()
        with patch.object(compute.sys,'platform','darwin'):
            self.assertIsNone(speech.view(self.path,self.fixture.data)['compute'])
        with patch.object(compute.sys,'platform','win32'):
            self.assertIn('NVIDIA',speech.view(self.path,self.fixture.data)['compute']['note'])
        self.assertEqual(file.read_bytes(),before)
        with patch.object(compute.sys,'platform','darwin'):
            self.fixture.transcribe()
        self.assertEqual(speech.state(self.path)['compute']['platform'],'darwin')
        self.assertNotIn('NVIDIA',str(speech.state(self.path)['compute']))
