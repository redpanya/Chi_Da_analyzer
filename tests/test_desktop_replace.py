import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop'))
import replace_windows as helper


class PortableReplaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.target = root / '사용자 앱'
        self.work = root / '.chida-update-fixture'
        self.work.mkdir()
        self.target.mkdir()
        self.archive = root / 'download.zip'
        self.updates = root / '프로필'
        self.updates.mkdir()
        self.plan = {'version':'1.3.0','previousVersion':'1.2.0','pid':123,
                     'token':'00000000-0000-0000-0000-000000000001',
                     'archive':str(self.archive),'updateRoot':str(self.updates)}
        for name, data in self.files('1.2.0').items():
            (self.target / name).write_bytes(data)
        self.make_zip()

    def files(self, version):
        return {helper.IMAGE:version.encode(),helper.INVENTORY:json.dumps(
            {'app':helper.APP,'version':version,'files':[helper.IMAGE]}).encode()}

    def make_zip(self, extra=None):
        with zipfile.ZipFile(self.archive,'w') as pack:
            for name, data in self.files('1.3.0').items():
                pack.writestr(helper.APP + '/' + name, data)
            for name in extra or []:
                pack.writestr(name,b'bad')
        self.plan.update(size=self.archive.stat().st_size,sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest())

    def test_swap_after_verification_and_health(self):
        helper.prepare(self.work,self.target,self.plan)
        self.assertEqual((self.target/helper.IMAGE).read_bytes(),b'1.2.0')
        helper.replace(self.work,self.target,self.plan,wait=lambda _:None,check=lambda *_:None)
        self.assertEqual((self.target/helper.IMAGE).read_bytes(),b'1.3.0')
        self.assertFalse((self.work/'previous').exists())

    def test_rollback_if_new_app_fails(self):
        helper.prepare(self.work,self.target,self.plan)
        def fail(*_):
            raise RuntimeError('시작 실패')
        with patch.object(helper,'launch') as start:
            with self.assertRaises(RuntimeError):
                helper.replace(self.work,self.target,self.plan,wait=lambda _:None,check=fail)
            start.assert_called_once_with(self.target)
        self.assertEqual((self.target/helper.IMAGE).read_bytes(),b'1.2.0')
        self.assertTrue((self.work/'failed'/helper.IMAGE).exists())

    def test_unknown_user_file_or_directory_prevents_replacement(self):
        personal=self.target/'개인원본'
        personal.mkdir()
        with self.assertRaisesRegex(ValueError,'자동 교체'):
            helper.prepare(self.work,self.target,self.plan)
        self.assertTrue(personal.is_dir())
        personal.rmdir()
        helper.prepare(self.work,self.target,self.plan)
        (self.target/'new-note.txt').write_text('남겨야 할 자료',encoding='utf-8')
        with patch.object(helper,'launch'), self.assertRaisesRegex(ValueError,'등록하지 않은 파일'):
            helper.replace(self.work,self.target,self.plan,wait=lambda _:None,check=lambda *_:None)
        self.assertTrue((self.target/'new-note.txt').is_file())
        self.assertFalse((self.work/'previous').exists())

    def test_empty_packaged_directory_is_replaceable(self):
        folder = self.target / 'locales'
        folder.mkdir()
        marker = self.target / helper.INVENTORY
        data = json.loads(marker.read_text())
        data['directories'] = ['locales']
        marker.write_text(json.dumps(data),encoding='utf-8')
        helper.prepare(self.work,self.target,self.plan)
        helper.replace(self.work,self.target,self.plan,wait=lambda _:None,check=lambda *_:None)
        self.assertEqual((self.target/helper.IMAGE).read_bytes(),b'1.3.0')

    def test_reject_malformed_zip_and_modified_download(self):
        for name in ['ChiDaanalyzer/../outside','ChiDaanalyzer/alpha./key','ChiDaanalyzer/aux.txt','/escape']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as stage:
                self.make_zip([name])
                with self.assertRaises(ValueError):
                    helper.extract_verified(self.archive,Path(stage),self.plan)
        self.archive.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'크기'):
            helper.prepare(self.work,self.target,self.plan)
        self.assertEqual((self.target/helper.IMAGE).read_bytes(),b'1.2.0')

    @unittest.skipUnless(os.name == 'nt', 'Windows에서 실행 파일 교체와 재시작을 확인합니다.')
    def test_windows_replace_executable_and_restart(self):
        sample = self.work / 'Probe.exe'
        code = self.work / 'Probe.cs'
        code.write_text('''
using System;
using System.IO;
class Probe {
    static void Main() {
        var dir = Environment.GetEnvironmentVariable("CHIDA_TEST_PROBE_DIR");
        var token = Environment.GetEnvironmentVariable("CHIDA_UPDATE_ATTEMPT");
        File.WriteAllText(Path.Combine(dir, token + ".ready"),
                          Environment.GetEnvironmentVariable("CHIDA_UPDATE_VERSION"));
        File.WriteAllText(Path.Combine(dir, "restarted"), Environment.CurrentDirectory);
    }
}''', encoding='utf-8')
        env = dict(os.environ, CHIDA_TEST_SOURCE=str(code), CHIDA_TEST_OUTPUT=str(sample))
        subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
                        'Add-Type -TypeDefinition ([IO.File]::ReadAllText($env:CHIDA_TEST_SOURCE)) '
                        '-OutputAssembly $env:CHIDA_TEST_OUTPUT '
                        '-OutputType WindowsApplication -ErrorAction Stop'],env=env,check=True,timeout=45)
        files = self.files('1.3.0')
        files[helper.IMAGE] = sample.read_bytes()
        with zipfile.ZipFile(self.archive,'w') as pack:
            for name,data in files.items():
                pack.writestr(helper.APP + '/' + name,data)
        parent = subprocess.Popen([sys.executable,'-c','import time; time.sleep(.7)'])
        try:
            self.plan.update(size=self.archive.stat().st_size,sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest(),
                             app=helper.APP,target=str(self.target),pid=parent.pid)
            config = self.work / 'plan.json'
            config.write_text(json.dumps(self.plan),encoding='utf-8')
            binary = Path(__file__).resolve().parents[1] / 'build/desktop-helper/chida-update.exe'
            cmd = [str(binary)] if binary.is_file() else [sys.executable, str(Path(helper.__file__).resolve())]
            env['CHIDA_TEST_PROBE_DIR'] = str(self.updates)
            for command in ['prepare','replace']:
                subprocess.run([*cmd,command,str(config)],env=env,check=True,timeout=45)
        finally:
            parent.wait(timeout=10)
        self.assertTrue(Path((self.updates/'restarted').read_text(encoding='utf-8-sig')).samefile(self.target))
        self.assertEqual(json.loads((self.work/'step.json').read_text())['phase'],'complete')
