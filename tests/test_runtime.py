"""앱 환경 격리·설정 복원과 실행기 종료 계약 검사."""
import json,os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from archive import runtime

class RuntimeTests(unittest.TestCase):
 def test_bundled_tools_certificate_and_library_settings(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(runtime,'FROZEN',True),patch.object(runtime,'SUPPORT',Path(folder)),patch.object(sys,'_MEIPASS',folder,create=True),patch.dict(os.environ,{'PATH':'/opt/homebrew/bin','PYTHONPATH':'/개발/경로','GGML_BACKEND_PATH':'/개발/외부.so'}):
   runtime.configure();self.assertEqual(os.environ['PATH'],folder+'/bin:/usr/bin:/bin:/usr/sbin:/sbin')
   self.assertEqual(os.environ['SSL_CERT_FILE'],folder+'/certs/cacert.pem');self.assertNotIn('PYTHONPATH',os.environ)
   self.assertNotIn('GGML_BACKEND_PATH',os.environ)
   runtime.remember_library(folder+'/한글 보관함');self.assertEqual(runtime.library_default(),Path(folder)/'한글 보관함')
   for malformed in ('{','[]','null','{"library":42}'):
    (Path(folder)/'settings.json').write_text(malformed);self.assertEqual(runtime.library_default(),Path.home()/'Movies/치지직 보관함')
 def test_development_keeps_existing_environment(self):
  with patch.object(runtime,'FROZEN',False),patch.dict(os.environ,{'PATH':'/개발/도구'}):
   runtime.configure();self.assertEqual(os.environ['PATH'],'/개발/도구')
 def test_ready_file_and_sigterm_cleanup(self):
  with tempfile.TemporaryDirectory() as folder:
   ready=Path(folder)/'ready.json'
   proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'app.py'),'--no-open','--library',folder,'--ready-file',str(ready)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    for _ in range(100):
     if ready.exists():break
     time.sleep(.05)
    self.assertTrue(ready.exists());value=json.loads(ready.read_text());self.assertEqual(value['pid'],proc.pid);self.assertTrue(value['url'].startswith('http://127.0.0.1:'))
    proc.terminate();self.assertEqual(proc.wait(timeout=10),0);self.assertFalse(ready.exists())
   finally:
    if proc.poll() is None:proc.kill();proc.wait()
 def test_parent_disappearance_stops_backend(self):
  with tempfile.TemporaryDirectory() as folder:
   proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'app.py'),'--no-open','--library',folder,'--parent-pid','999999'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:self.assertEqual(proc.wait(timeout=10),0)
   finally:
    if proc.poll() is None:proc.kill();proc.wait()
