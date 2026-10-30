import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from archive import speaker_tools as tools, speaker_tools_install as installer
from archive import runtime, voice_models, voices, voice_store, diarization_run, diarization_backends, diarization_models
from archive.source import Cancelled
from archive.storage import ProjectLock, read_json, save_json
import test_voices as fixture


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.support=patch.object(runtime,'SUPPORT',self.root/'지원')
        self.support.start()
        self.platform=patch.object(tools,'platform_id',return_value='macOS-arm64')
        self.platform.start()
        # ZIP 설치/프로토콜 검사는 실제 실행하되, 가상 Python 파일은 Windows에서도
        # Python으로 연다. Windows는 Unix shebang을 실행 파일로 인식하지 않는다.
        check = tools.check
        self.checker = patch.object(tools, 'check', side_effect=lambda args, *rest:
                                   check([sys.executable, *args] if os.name == 'nt' else args, *rest))
        self.checker.start()
        self.stop=threading.Event()
    def tearDown(self):
        self.checker.stop();self.platform.stop();self.support.stop();self.temp.cleanup()

    def package(self, backend='sherpa', marker=True):
        path=self.root/f'{backend}.zip'
        entry=tools.entry_name(backend)
        script=f'#!{sys.executable}\nprint("CHIDA_SPEAKER_TOOL:1:{backend}" if {marker!r} else "incompatible")\n'
        manifest={'backend':backend,'protocol':1,'platform':'macOS-arm64','entry':entry}
        with zipfile.ZipFile(path,'w') as archive:
            info=zipfile.ZipInfo(entry);info.external_attr=(stat.S_IFREG|0o755)<<16
            archive.writestr(info,script)
            archive.writestr('tool.json',json.dumps(manifest))
        return path

    def install(self, path, stop=None):
        raw=path.read_bytes()
        asset={'url':'https://github.com/test','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        with patch.object(installer,'release_asset',return_value=asset),patch.object(installer,'open_url',return_value=io.BytesIO(raw)),ProjectLock(self.root/'작업') as lock:
            installer.install('sherpa',stop or self.stop,lock,lambda **v:None)

    def test_installs_all_tools_and_preserves_models_and_prior_install(self):
        sentinel=self.root/'models/verified.json';sentinel.parent.mkdir();sentinel.write_text('기존 모델')
        path=self.package();self.install(path)
        first=read_json(tools.home('sherpa')/'active.json')
        exe=tools.managed('sherpa')
        self.assertTrue(exe.is_file());self.assertEqual(tools.status('sherpa')['source'],'installed')
        self.assertEqual(tools.command('sherpa','request')[-2:],['--voice-worker','request'])
        self.assertEqual(tools.command('sherpa','request',candidate=True)[-2:],['--voice-candidate-worker','request'])
        self.install(path)
        self.assertNotEqual(first,read_json(tools.home('sherpa')/'active.json'))
        self.assertTrue(exe.is_file());self.assertEqual(sentinel.read_text(),'기존 모델')
        for backend in ('pyannote','fluid'):
            bundle=self.package(backend);raw=bundle.read_bytes()
            asset={'url':'https://github.com/test','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            with patch.object(installer,'release_asset',return_value=asset),patch.object(installer,'open_url',return_value=io.BytesIO(raw)),ProjectLock(self.root/'작업') as lock:
                installer.install(backend,self.stop,lock,lambda **v:None)
            self.assertEqual(tools.command(backend,'request'),[str(tools.managed(backend)),'request'])
        self.assertFalse(list(tools.home('sherpa').glob('.install-*')))

    def test_failed_check_hash_and_cancel_preserve_active(self):
        self.install(self.package());before=(tools.home('sherpa')/'active.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'호환'):self.install(self.package(marker=False))
        with patch.object(installer,'download',side_effect=Cancelled()),self.assertRaises(Cancelled):self.install(self.package())
        with patch.object(installer.hashlib,'sha256') as sha:
            sha.return_value.hexdigest.return_value='bad'
            # 원격 메타데이터는 정상 해시이고 내려받은 파일 검증만 실패한다.
            with patch.object(installer,'release_asset',return_value={'url':'https://github.com/test','size':1,'sha256':'a'*64}),patch.object(installer,'open_url',return_value=io.BytesIO(b'x')),ProjectLock(self.root/'작업') as lock:
                with self.assertRaisesRegex(ValueError,'SHA-256'):installer.install('sherpa',self.stop,lock,lambda **v:None)
        self.assertEqual(before,(tools.home('sherpa')/'active.json').read_bytes())
        self.assertFalse(list(tools.home('sherpa').glob('.install-*')))

    def test_unsafe_archives_and_unsupported_device(self):
        cases=[('../escape',stat.S_IFREG),('/absolute',stat.S_IFREG),('C:/drive',stat.S_IFREG),('x:ads',stat.S_IFREG),('x\\y',stat.S_IFREG),('link',stat.S_IFLNK)]
        for index,(name,kind) in enumerate(cases):
            file=self.root/f'bad{index}.zip'
            with zipfile.ZipFile(file,'w') as archive:
                info=zipfile.ZipInfo(name);info.filename=name
                info.external_attr=(kind|0o755)<<16;archive.writestr(info,'../escape')
            target=self.root/f'out{index}';target.mkdir()
            with self.assertRaises(ValueError):installer.extract(file,target,self.stop)
        with patch.object(tools,'platform_id',return_value='Windows-x64'),ProjectLock(self.root/'작업') as lock:
            self.assertFalse(tools.supported('fluid'));self.assertTrue(tools.supported('pyannote'))
            with self.assertRaisesRegex(ValueError,'지원'):installer.install('fluid',self.stop,lock,lambda **v:None)
        self.assertFalse((self.root/'escape').exists())

    def test_release_requires_public_exact_asset_digest_and_https(self):
        name='chida-sherpa-macOS-arm64.zip'
        release={'tag_name':tools.RELEASE,'draft':False,'assets':[{'name':name,'state':'uploaded','size':10,'digest':'sha256:'+'a'*64,
            'browser_download_url':f'https://github.com/{tools.REPOSITORY}/releases/download/{tools.RELEASE}/{name}'}]}
        with patch.object(installer,'open_url',return_value=io.BytesIO(json.dumps(release).encode())):
            self.assertEqual(installer.release_asset('sherpa',self.stop)['sha256'],'a'*64)
        release['assets'][0]['digest']=None
        with patch.object(installer,'open_url',return_value=io.BytesIO(json.dumps(release).encode())),self.assertRaises(ValueError):
            installer.release_asset('sherpa',self.stop)
        for url in ['http://github.com/a','https://evil.example/a','https://github.com@evil.example/a','https://github.com:444/a','file:///tmp/a']:
            with self.assertRaises(ValueError):installer.allowed(url)

    def test_corrupt_marker_falls_back_without_deleting_existing(self):
        self.install(self.package());folder=tools.managed('sherpa').parent
        save_json(tools.home('sherpa')/'active.json',{'version':'../../other'})
        self.assertIsNone(tools.managed('sherpa'));self.assertTrue(folder.is_dir())
        with patch.object(voice_models,'PYTHON',self.root/'missing'):
            self.assertFalse(tools.status('sherpa')['ready'])

    def test_existing_pyannote_models_are_verified_without_hf_download(self):
        target=self.root/'existing-models';target.mkdir()
        sentinel=target/'weights.bin';sentinel.write_bytes(b'existing-model')
        with patch.object(diarization_backends,'status',return_value={'supported':True,'engine':True}), \
             patch.object(diarization_backends,'catalog',return_value={'files':[]}), \
             patch.object(diarization_backends,'signature',return_value={'version':1}), \
             patch.object(diarization_models,'local',return_value=target), \
             patch.object(diarization_models,'verify'), \
             patch.object(diarization_models,'fingerprints',return_value={}), \
             patch.object(diarization_run,'process') as process,ProjectLock(self.root/'job') as lock:
            diarization_run.prepare('pyannote',self.root/'prepare',self.stop,lock,lambda **v:None)
        process.assert_not_called();self.assertEqual(sentinel.read_bytes(),b'existing-model')

    def test_frozen_app_uses_installed_worker_without_python_script(self):
        self.install(self.package())
        with patch.object(sys,'frozen',True,create=True):
            args=tools.command('sherpa','request')
            self.assertEqual(args,[str(tools.managed('sherpa')),'--voice-worker','request'])
        save_json(tools.home('sherpa')/'active.json',{})
        with patch.object(sys,'frozen',True,create=True),patch.object(voice_models,'PYTHON',Path(sys.executable)):
            self.assertEqual(tools.command('sherpa','request'),[sys.executable,'--voice-worker','request'])


class ResultPreservationTests(unittest.TestCase):
    setUp=fixture.VoiceTests.setUp
    tearDown=fixture.VoiceTests.tearDown
    audio=fixture.VoiceTests.audio
    fake_engine=fixture.VoiceTests.fake_engine
    transcribe=fixture.VoiceTests.transcribe
    prepare=fixture.VoiceTests.prepare
    change=fixture.VoiceTests.change

    def test_runtime_actions_keep_result_and_manual_names(self):
        ids=list(self.prepare());self.change('rename',speaker=ids[0],name='수동 이름 보존')
        before=voice_store.browse(self.path)
        files={str(p):p.read_bytes() for p in (self.path/'voices/runs').rglob('*') if p.is_file()}
        for failure in (None,Cancelled(),ValueError('설치 실패')):
            with ProjectLock(self.path) as lock,patch.object(installer,'install',side_effect=failure):
                voices.VoiceJob(self.path,self.data,lock,'install-engine',{'backend':'pyannote'}).run()
            after=voice_store.browse(self.path)
            self.assertEqual(before['speakers'],after['speakers']);self.assertEqual(before['run'],after['run'])
            self.assertEqual(files,{str(p):p.read_bytes() for p in (self.path/'voices/runs').rglob('*') if p.is_file()})
