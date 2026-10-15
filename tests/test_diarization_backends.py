import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
import sys
import time
from unittest.mock import patch

from archive import diarization_backends as backends, diarization_models as models, diarization_run
from archive import voices, voice_store as store
from archive.source import Cancelled
from archive.storage import ProjectLock, read_json, save_json
import test_voices as fixture


class BackendTests(unittest.TestCase):
    def test_backend_and_speaker_limits(self):
        for bad in ['unknown','../fluid','nemo',None,{}]:
            with self.assertRaises(ValueError): backends.checked(bad)
        for count in [True,0,21,'2']:
            with self.assertRaises(ValueError): backends.validate('fluid',count)
        self.assertEqual(set(backends.BACKENDS),{'sherpa','pyannote','fluid'})
        backends.validate('pyannote',-1)
        self.assertNotEqual(backends.signature('fluid'),backends.signature('pyannote'))

    def test_model_hash_and_symlink_detection(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root).resolve()
            file=root/'model';file.write_bytes(b'abc')
            spec={'size':3,'sha256':hashlib.sha256(b'abc').hexdigest()}
            self.assertTrue(models.matches(file,spec))
            file.write_bytes(b'abd');self.assertFalse(models.matches(file,spec))
            link=Path(root)/'link';link.symlink_to(file)
            with patch.object(backends,'home',return_value=Path(root)):
                with self.assertRaises(ValueError): models.local('fluid','link')

    def test_fluid_revision_marker_is_required(self):
        with tempfile.TemporaryDirectory() as root, patch.object(backends,'home',return_value=Path(root).resolve()), patch.object(backends,'catalog',return_value={'revision':'fixed','files':[]}):
            with self.assertRaises(FileNotFoundError): models.fingerprints('fluid')
            (Path(root)/'.fluidaudio-revision').write_text('wrong')
            with self.assertRaises(ValueError): models.fingerprints('fluid')
            (Path(root)/'.fluidaudio-revision').write_text('fixed\n')
            self.assertEqual(models.fingerprints('fluid'),{})

    def test_native_process_cancel_does_not_commit_result(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root); engine=folder/'test-engine'
            engine.write_text(f'#!{sys.executable}\nimport time\nfrom pathlib import Path\nPath(__file__).with_name("started").touch()\ntime.sleep(30)\nPath(__file__).with_name("should-not-exist").touch()\n')
            engine.chmod(0o700);stop=threading.Event()
            def cancel():
                for _ in range(100):
                    if (folder/'started').exists():break
                    time.sleep(.02)
                stop.set()
            thread=threading.Thread(target=cancel);thread.start()
            with ProjectLock(folder) as lock,patch.object(backends,'executable',return_value=engine):
                with self.assertRaises(Cancelled):diarization_run.process('fluid',folder,{},stop,lock,lambda **v:None)
            thread.join();self.assertTrue((folder/'started').exists());self.assertFalse((folder/'should-not-exist').exists())
            self.assertFalse((folder/'engine.json').exists())


class BackendPreservationTests(unittest.TestCase):
    setUp=fixture.VoiceTests.setUp
    tearDown=fixture.VoiceTests.tearDown
    audio=fixture.VoiceTests.audio
    fake_engine=fixture.VoiceTests.fake_engine
    transcribe=fixture.VoiceTests.transcribe
    prepare=fixture.VoiceTests.prepare
    change=fixture.VoiceTests.change

    def test_switch_creates_new_pending_and_preserves_previous_names(self):
        ids=list(self.prepare());self.change('rename',speaker=ids[0],name='보존 이름')
        before={p.name:p.read_bytes() for p in store.local(self.path,'runs/test').iterdir()}
        pending=[]
        for backend in ['sherpa','fluid','fluid','pyannote']:
            with ProjectLock(self.path) as lock:
                job=voices.VoiceJob(self.path,self.data,lock,'diarize',{'backend':backend})
                with patch.object(job,'worker',side_effect=Cancelled()):
                    job.run()
            pending.append(store.state(self.path)['pending_diarization']['id'])
            self.assertEqual(store.state(self.path)['run'],'test')
        self.assertNotEqual(pending[0],pending[1]);self.assertEqual(pending[1],pending[2]);self.assertNotEqual(pending[2],pending[3])
        self.assertEqual(before,{p.name:p.read_bytes() for p in store.local(self.path,'runs/test').iterdir()})
        self.assertEqual(store.browse(self.path)['speakers'][0]['name'],'보존 이름')

    def test_new_result_provenance_and_failed_result_do_not_replace_active(self):
        self.prepare()
        with ProjectLock(self.path) as lock:
            job=voices.VoiceJob(self.path,self.data,lock,'diarize',{'backend':'fluid'})
            with patch.object(job,'worker',return_value={'turns':[{'start_ms':0,'end_ms':2500,'speaker':0}]}): job.run()
        result=store.result(self.path)
        self.assertEqual(result['backend'],'fluid');self.assertEqual(len(store.state(self.path)['runs']),2)
        with ProjectLock(self.path) as lock:
            job=voices.VoiceJob(self.path,self.data,lock,'diarize',{'backend':'pyannote'})
            with patch.object(job,'worker',return_value={'turns':[{'start_ms':0,'end_ms':9000,'speaker':0}]}): job.run()
        self.assertEqual(store.state(self.path)['state'],'error')
        self.assertEqual(store.result(self.path),result)

    def test_removed_engine_results_and_manual_names_remain_readable(self):
        ids=list(self.prepare())
        file=store.local(self.path,'runs/test/result.json')
        save_json(file,store.result(self.path)|{'backend':'nemo','backend_label':'Nemotron 3 + NeMo-Speech.cpp'})
        self.change('rename',speaker=ids[0],name='보존 이름')
        before={str(p):p.read_bytes() for p in (self.path/'voices').rglob('*') if p.is_file()}
        value=store.browse(self.path)
        self.assertEqual(value['backend_label'],'Nemotron 3 + NeMo-Speech.cpp')
        self.assertEqual(value['speakers'][0]['name'],'보존 이름')
        self.assertEqual(value['run'],'test')
        from archive.jobs import Manager
        manager=Manager(self.root)
        for action in ('prepare','diarize'):
            with self.assertRaisesRegex(ValueError,'지원하는 화자 엔진'):
                manager.voices_start(str(self.root),'1',action,{'backend':'nemo'})
        self.assertEqual(before,{str(p):p.read_bytes() for p in (self.path/'voices').rglob('*') if p.is_file()})
