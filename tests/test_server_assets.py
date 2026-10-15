"""웹 모듈을 추가할 때 로컬 서버 허용 목록 누락을 검사한다."""
from http.client import HTTPConnection
import threading
import unittest
from urllib.parse import urlsplit

from archive.server import WEB, make_server


class ServerAssetTests(unittest.TestCase):
    def test_all_gui_assets_are_served_with_correct_mime(self):
        server, url = make_server(None)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        parsed = urlsplit(url)
        client = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        try:
            files = [(p.name, p, 'text/javascript') for p in WEB.glob('*.js')]
            files += [('', WEB/'index.html', 'text/html'), ('style.css', WEB/'style.css', 'text/css')]
            for route, file, mime in files:
                with self.subTest(file=file.name):
                    client.request('GET', parsed.path+route)
                    response = client.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertTrue(response.getheader('Content-Type').startswith(mime))
                    self.assertEqual(response.read(), file.read_bytes())
            client.request('GET', parsed.path+'archive/server.py')
            response = client.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join()

    def test_removed_clip_api_is_explicitly_unavailable(self):
        server,url=make_server(None);thread=threading.Thread(target=server.serve_forever);thread.start()
        p=urlsplit(url);client=HTTPConnection(p.hostname,p.port,timeout=5)
        try:
            client.request('POST',p.path+'api/clips-start',body='{}',headers={'Origin':f'http://{p.netloc}','Content-Type':'application/json'})
            r=client.getresponse();self.assertEqual(r.status,410);self.assertIn('제거',r.read().decode())
        finally:client.close();server.shutdown();server.server_close();thread.join()
