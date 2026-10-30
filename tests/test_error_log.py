import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit
from archive import error_log, runtime
from archive.server import make_server

class ErrorLog(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.support=patch.object(runtime,'SUPPORT',self.root);self.support.start();error_log._warning=''
    def tearDown(self):self.support.stop();self.tmp.cleanup()
    def test_toggle_preserves_settings_and_existing_log(self):
        runtime.save_settings(models='existing-models',other=123)
        error_log.record('speech',RuntimeError('종료됐습니다(3221226505)'),vod='15910443')
        before=error_log.location().read_bytes()
        error_log.configure(False);error_log.record('speech',ValueError('new'))
        self.assertEqual(before,error_log.location().read_bytes())
        self.assertEqual(runtime.settings()['models'],'existing-models')
        error_log.configure(True);error_log.record('speech',ValueError('new'))
        self.assertEqual(len(error_log.snapshot()['events']),2)
        self.assertEqual(error_log.snapshot(export=True)['events'][0]['code'],3221226505)
    def test_privacy_and_duplicate_count(self):
        raw='원문검사 privatebody hf_abc123 token=secret user@example.com https://example.com/token C:\\사용자\\자료'
        for _ in range(3):error_log.record('browser-index-script',ValueError(raw),vod='123')
        local=error_log.snapshot()['events'][0]
        self.assertEqual(local['count'],3)
        for private in ('hf_abc123','token=secret','user@example.com','https://','C:'):self.assertNotIn(private,local['message'])
        exported=json.dumps(error_log.snapshot(export=True),ensure_ascii=False)
        for private in ('privatebody','원문검사','secret','사용자','message'):self.assertNotIn(private,exported)
    def test_concurrent_limit_and_bounded_bytes(self):
        with patch.object(error_log,'LIMIT',12),patch.object(error_log,'MAX_BYTES',16000):
            with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda i:error_log.record('test',ValueError(f'{i} '+('한글'*1000))),range(40)))
            self.assertLessEqual(len(error_log.snapshot()['events']),12)
            self.assertLessEqual(error_log.location().stat().st_size,16000)
            self.assertFalse(error_log.config()['warning'])
    def test_write_failure_never_replaces_original_error(self):
        with patch.object(error_log,'save_json',side_effect=PermissionError('readonly')):
            error_log.record('video-split',RuntimeError('original'))
        self.assertTrue(error_log.config()['warning'])
        self.assertFalse(error_log.location().exists())
    def test_corrupt_log_is_preserved(self):
        error_log.location().parent.mkdir();error_log.location().write_text('broken')
        error_log.record('error',ValueError('new'))
        self.assertEqual(error_log.location().read_text(),'broken')
        self.assertTrue(error_log.snapshot()['warning'])
    def test_http_failure_capture_and_origin_guard(self):
        def fail(*args):raise ValueError('파일 검증 실패')
        server,url=make_server(SimpleNamespace(inspect=fail));t=threading.Thread(target=server.serve_forever);t.start()
        u=urlsplit(url)
        def call(action,data,origin=None):
            client=HTTPConnection(u.hostname,u.port,timeout=5)
            client.request('POST',u.path+'api/'+action,json.dumps(data),{'Content-Type':'application/json','Origin':origin or f'http://{u.netloc}'})
            response=client.getresponse();status=response.status;body=json.loads(response.read());client.close();return status,body
        try:
            self.assertEqual(call('inspect',{'url':'not-used'})[0],400)
            status,value=call('error-log-list',{});self.assertEqual(status,200);self.assertEqual(value['events'][0]['operation'],'/api/inspect')
            self.assertEqual(call('error-log-settings',{'enabled':False},'https://evil.invalid')[0],403)
            self.assertTrue(error_log.enabled())
            self.assertEqual(call('error-log-client',{'page':'video-split','kind':'media','message':'오류 4'})[0],200)
            self.assertEqual(len(call('error-log-export',{})[1]['events']),2)
            self.assertEqual(call('error-log-settings',{'enabled':False})[0],200)
            call('inspect',{'url':'not-used'});self.assertEqual(len(call('error-log-list',{})[1]['events']),2)
        finally:server.shutdown();server.server_close();t.join()

if __name__=='__main__':unittest.main()
