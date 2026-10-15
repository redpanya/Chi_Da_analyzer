"""분리 설정 격리, 원음 우회, 설정 전환 후 복구와 이전 결과 보존."""
import hashlib
import json
import threading
import unittest
from unittest.mock import patch

from archive import sam_models, sam_options, separation, speech, speech_model as model, speech_store as store, speech_media as media
from archive.jobs import Manager
from archive.source import Cancelled
from archive.storage import ProjectLock, save_json
import test_speech


class SpeechOptionsTests(unittest.TestCase):
    setUp = test_speech.SpeechTests.setUp
    tearDown = test_speech.SpeechTests.tearDown
    audio = test_speech.SpeechTests.audio
    fake_engine = test_speech.SpeechTests.fake_engine

    def transcribe(self, kind, profile='standard', callback=None):
        raw = store.state(self.path).get('raw_audio') or store.state(self.path)['audio']
        audio = raw | {'input_kind': kind}
        if kind == 'sam': audio.update(sam_profile=profile, separation_run=profile)
        with ProjectLock(self.path) as lock, patch.object(model, 'verify', return_value=self.root/'model'), patch.object(model, 'engine_version', return_value=('engine', 'test')), patch.object(media, 'process', side_effect=callback or self.fake_engine), patch.object(store, 'CHUNK_MS', 1000):
            speech.transcribe(self.path, self.data, 'ko', threading.Event(), lock, lambda **v: store.update(self.path, **v), audio, raw)
        return store.manifest(self.path)

    def test_profiles_and_old_standard_contract(self):
        old = {'model':sam_models.NAME,'revision':sam_models.REVISION,'runtime':'mlx-audio/0.5.9',
               'rate':48000,'chunk_seconds':10,'overlap_seconds':3,'seed':42,'description':'speech','ode':'midpoint/16','version':1}
        self.assertEqual(separation.contract(), old)
        self.assertEqual([sam_options.ode_options(separation.contract(p)) for p in ('standard','balanced','fast')],
                         [{'method':'midpoint','step_size':1/16}, {'method':'midpoint','step_size':1/8}, {'method':'euler','step_size':1/8}])
        for bad in ('', 'turbo', [], None):
            with self.assertRaises(ValueError): separation.contract(bad)
        with self.assertRaises(ValueError): sam_options.ode_options({'ode':'euler/0'})

    def test_cached_whole_separation_is_isolated_and_kept(self):
        self.audio(1000); raw = store.state(self.path)['audio']
        signature = {'source':raw['source'],'raw_sha256':raw['sha256'],'track':raw['track'],'contract':separation.contract()}
        key = hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
        folder = media.local(self.path, 'separations/'+key); folder.mkdir(parents=True)
        for name in ('target','residual','speech16'): (folder/(name+'.wav')).write_bytes(b'cached')
        result = {'contract':separation.contract(),'review_chunks':[], 'hashes':{k:model.digest(folder/(k+'.wav')) for k in ('target','residual')}}
        save_json(folder/'result.json', result); before = (folder/'result.json').read_bytes()
        with patch.object(sam_models,'verify'), patch.object(separation,'validate'), patch.object(media,'validate_wav'), patch.object(separation,'run_worker') as worker:
            _, audio = separation.whole(self.path,self.data,threading.Event(),None,lambda **v:store.update(self.path,**v))
            worker.assert_not_called()
            self.assertEqual(audio['separation_run'],key)
            self.assertEqual(audio['sam_profile'],'standard')
        self.assertIsNone(separation.completed(folder,'fast'))
        self.assertEqual((folder/'result.json').read_bytes(),before)

    def test_same_audio_different_source_and_profile_create_separate_runs(self):
        self.audio()
        runs = [self.transcribe('original'), self.transcribe('sam'), self.transcribe('sam','fast')]
        self.assertEqual(len({r['id'] for r in runs}),3)
        self.assertEqual(len({r['audio_sha256'] for r in runs}),1)
        saved = {r['id']:media.local(self.path,f"runs/{r['id']}/manifest.json").read_bytes() for r in runs}
        old = self.transcribe('original',callback=lambda *args:self.fail('완료된 원음은 다시 추론하지 않아야 함'))
        self.assertEqual(old['id'],runs[0]['id'])
        for rid,content in saved.items(): self.assertEqual(media.local(self.path,f'runs/{rid}/manifest.json').read_bytes(),content)
        self.assertEqual({v['input_label'] for v in store.view(self.path,self.data)['versions']}, {'원본 오디오','SAM 분리음 · 표준','SAM 분리음 · 빠름'})

    def test_switch_back_resumes_partial_and_keeps_original_corrections(self):
        self.audio(); old = self.transcribe('original')
        store.correct(self.path,old['id'],'00000-00000','이전 교정문')
        calls=[]
        def interrupted(*args):
            calls.append(1)
            if len(calls)==2: raise Cancelled()
            self.fake_engine(*args)
        with self.assertRaises(Cancelled): self.transcribe('sam','fast',interrupted)
        pending = store.state(self.path)['pending_run']; checkpoint=media.local(self.path,f'runs/{pending}/00000.json'); content=checkpoint.read_bytes()
        self.assertEqual(store.result(self.path)['items'][0]['text'],'이전 교정문')
        self.transcribe('sam','balanced')
        resumed=self.transcribe('sam','fast')
        self.assertEqual(resumed['id'],pending); self.assertTrue(resumed['complete'])
        self.assertEqual(checkpoint.read_bytes(),content)
        store.select(self.path,old['id'])
        self.assertEqual(store.result(self.path)['items'][0]['text'],'이전 교정문')

    def test_legacy_transcript_reuses_without_migration(self):
        self.audio(); old=self.transcribe('original')
        for key in ('input_kind','separation_run','input_audio'): old.pop(key)
        file=media.local(self.path,f"runs/{old['id']}/manifest.json");save_json(file,old);before=file.read_bytes()
        reused=self.transcribe('original',callback=lambda *args:self.fail('이전 완료본 재추론'))
        self.assertEqual(reused['id'],old['id']);self.assertEqual(file.read_bytes(),before)

    def test_original_job_does_not_prepare_or_require_sam(self):
        self.audio();raw=store.state(self.path)['audio']
        with patch.object(separation,'whole',side_effect=AssertionError('SAM 실행 금지')), patch.object(sam_models,'verify',side_effect=AssertionError('SAM 검사 금지')), patch.object(speech,'transcribe') as transcribe:
            job=speech.SpeechJob(self.path,self.data,ProjectLock(self.path),'transcribe',{'language':'ko','input_kind':'original'})
            job.run();self.assertTrue(job.closed);self.assertEqual(store.state(self.path)['state'],'complete')
            self.assertEqual(transcribe.call_args.args[-2],raw|{'input_kind':'original'})
        with patch.object(separation,'whole',return_value=(raw,raw)) as separate:
            job=speech.SpeechJob(self.path,self.data,ProjectLock(self.path),'separate',{'sam_profile':'fast'})
            job.run();separate.assert_not_called();self.assertEqual(store.state(self.path)['state'],'error')

    def test_invalid_options_do_not_change_state(self):
        self.audio();before=media.local(self.path,'state.json').read_bytes();m=Manager(self.root)
        try:
            for options in ({'input_kind':'wrong'},{'sam_profile':'wrong'},{'input_kind':None},{'sam_profile':[]}):
                with self.assertRaises(ValueError):m.speech_start(str(self.root),'1','transcribe',**options)
            with self.assertRaises(ValueError):m.voices_start(str(self.root),'1','separate',{'sam_profile':'wrong'})
        finally:m.close()
        self.assertEqual(media.local(self.path,'state.json').read_bytes(),before)

    def test_work_settings_and_elapsed_time_are_isolated(self):
        self.audio();m=Manager(self.root)
        def start(kind, profile):
            # 실제 Job은 생성하되 엔진 실행만 생략해 상태·시간 키를 직접 검사한다.
            with patch('threading.Thread.start'), patch.object(m,'view',return_value={}):
                m.speech_start(str(self.root),'1','transcribe',asr_options={'vad':kind,'prompt':profile})
            m.speech_job.lock.close();m.speech_job.closed=True;m.speech_job=None
            return store.state(self.path)
        try:
            first=start('sensitive','용어 힌트')
            store.update(self.path,state='paused',timing={'elapsed_ms':10000,'since_ms':None})
            same=start('sensitive','용어 힌트');self.assertGreaterEqual(same['timing']['elapsed_ms'],10000)
            store.update(self.path,state='paused',timing={'elapsed_ms':10000,'since_ms':None})
            original=start('standard','용어 힌트')
            self.assertNotEqual(first['timing_key'],original['timing_key'])
            self.assertLess(original['timing']['elapsed_ms'],10000)
            self.assertEqual(original['options'],{'input_kind':'original','asr_options':{'vad':'standard','prompt':'용어 힌트'}})
        finally:m.close()


if __name__=='__main__': unittest.main()
