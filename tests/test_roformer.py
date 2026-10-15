"""새 분리 모델의 입력 격리·이전 결과 보존·실패 경로 검사."""
import threading
import unittest
from unittest.mock import patch

from archive import roformer_models as models, roformer_separation as separation, sam_models
from archive import speech, speech_store as store, speech_media as media, speech_model
from archive.jobs import Manager
from archive.storage import ProjectLock, save_json
import test_speech

class RoformerTests(unittest.TestCase):
    setUp=test_speech.SpeechTests.setUp
    tearDown=test_speech.SpeechTests.tearDown
    audio=test_speech.SpeechTests.audio
    fake_engine=test_speech.SpeechTests.fake_engine

    def test_contract_profiles_and_legacy_labels(self):
        self.assertNotEqual(separation.contract('fast'),separation.contract('standard'))
        self.assertTrue(separation.contract('fast')['fp16'])
        self.assertEqual(store.input_info({'input_kind':'sam','input_audio':{'sam_profile':'fast'}})['input_label'],'SAM 분리음 · 빠름')
        self.assertIn('Viperx-1297',store.input_info({'input_kind':'roformer','input_audio':{'separation_profile':'fast'}})['input_label'])
        with self.assertRaises(ValueError):models.profile('balanced')

    def test_transcript_identity_does_not_reuse_same_bytes_from_sam(self):
        self.audio();raw=store.state(self.path)['audio'];runs=[]
        with patch.object(speech_model,'verify',return_value=self.root/'model'),patch.object(speech_model,'engine_version',return_value=('engine','test')),patch.object(media,'process',side_effect=self.fake_engine):
            for kind in ('sam','roformer','original'):
                audio=raw|{'input_kind':kind,'separation_run':kind,'separation_profile':'fast'}
                with ProjectLock(self.path) as lock:
                    speech.transcribe(self.path,self.data,'ko',threading.Event(),lock,lambda **v:store.update(self.path,**v),audio,raw)
                runs.append(store.manifest(self.path)['id'])
        self.assertEqual(len(set(runs)),3)
        for run in runs:self.assertTrue(media.local(self.path,f'runs/{run}/manifest.json').exists())

    def test_roformer_job_does_not_call_sam(self):
        self.audio();raw=store.state(self.path)['audio']
        with patch.object(sam_models,'verify',side_effect=AssertionError('SAM 사용 금지')),patch.object(separation,'whole',return_value=(raw,raw|{'input_kind':'roformer'})) as split,patch.object(speech,'transcribe') as transcribe:
            job=speech.SpeechJob(self.path,self.data,ProjectLock(self.path),'transcribe',{'input_kind':'roformer','sam_profile':'fast','language':'ko'})
            job.run()
            self.assertEqual(store.state(self.path)['state'],'error');split.assert_not_called();transcribe.assert_not_called()

    def test_failed_new_separation_keeps_selected_transcript(self):
        self.audio();store.update(self.path,run='existing')
        with patch.object(separation,'whole',side_effect=ValueError('분리 실패')):
            job=speech.SpeechJob(self.path,self.data,ProjectLock(self.path),'transcribe',{'input_kind':'roformer','sam_profile':'fast','language':'ko'});job.run()
        self.assertEqual(store.state(self.path)['run'],'existing');self.assertEqual(store.state(self.path)['state'],'error')

    def test_corrupt_completed_audio_is_not_overwritten(self):
        folder=self.root/'new';folder.mkdir()
        save_json(folder/'result.json',{'contract':separation.contract(),'hashes':{'target':'wrong'}})
        (folder/'target.wav').write_bytes(b'keep')
        with self.assertRaises(ValueError):separation.completed(folder)
        self.assertEqual((folder/'target.wav').read_bytes(),b'keep')

    def test_wrong_engine_profile_rejected_before_state_write(self):
        self.audio();before=store.state(self.path);m=Manager(self.root)
        try:
            with self.assertRaises(ValueError):m.speech_start(str(self.root),'1','transcribe',input_kind='roformer',sam_profile='balanced')
            with self.assertRaises(ValueError):m.voices_start(str(self.root),'1','separate',{'separation_model':'unknown'})
            with self.assertRaises(ValueError):m.voices_start(str(self.root),'1','separate',{'separation_model':'roformer','sam_profile':'balanced'})
            self.assertEqual(store.state(self.path),before)
        finally:m.close()

if __name__=='__main__':unittest.main()
