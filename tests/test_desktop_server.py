"""앱 업데이트 직전에 시작된 작업과 진행 중인 저장 요청을 보호한다."""
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
import os
from pathlib import Path
import tempfile
import threading
from urllib.parse import urlsplit
from unittest import TestCase
from unittest.mock import patch

from archive import server
from archive.jobs import Manager


class DesktopExitTest(TestCase):
    def test_freeze_waits_for_post_queue_and_mix_then_thaws(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, CHIDA_DESKTOP_CONTROL='test-secret'):
            manager = Manager(Path(tmp))
            http, url = server.make_server(manager)
            address = urlsplit(url)
            thread = threading.Thread(target=http.serve_forever)
            thread.start()

            def post(action, *, key=''):
                conn = HTTPConnection(address.hostname, address.port, timeout=5)
                try:
                    conn.request('POST', address.path+'api/'+action, b'{}', {
                        'Content-Type':'application/json', 'X-Chida-Control':key})
                    res = conn.getresponse()
                    res.read()
                    return res.status
                finally:
                    conn.close()

            entered, release = threading.Event(), threading.Event()
            def hold():
                entered.set()
                release.wait(5)
                return {}

            try:
                with patch.object(manager.tasks, 'status', hold), ThreadPoolExecutor(1) as pool:
                    saving = pool.submit(post, 'work-queue')
                    self.assertTrue(entered.wait(3))
                    self.assertEqual(post('desktop-freeze', key='test-secret'), 409)
                    release.set()
                    self.assertEqual(saving.result(), 200)
                manager.tasks.items.append({'state':'queued'})
                self.assertEqual(post('desktop-freeze', key='test-secret'), 409)
                manager.tasks.items.clear()
                manager.mix.jobs[tmp] = {'thread':thread}
                self.assertEqual(post('desktop-freeze', key='test-secret'), 409)
                manager.mix.jobs.clear()
                self.assertEqual(post('desktop-freeze'), 403)
                self.assertEqual(post('desktop-freeze', key='test-secret'), 200)
                self.assertEqual(post('work-queue'), 409)
                self.assertEqual(post('desktop-thaw'), 403)
                self.assertEqual(post('desktop-thaw', key='test-secret'), 200)
                self.assertEqual(post('work-queue'), 200)
            finally:
                release.set()
                manager.tasks.items.clear()
                manager.mix.jobs.clear()
                http.shutdown()
                http.server_close()
                thread.join()
                manager.close()
