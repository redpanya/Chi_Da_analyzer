"""등록된 로컬 파일만 같은 앱 세션에서 Range로 전달한다."""
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlsplit
from archive.jobs import Manager
from archive.server import make_server
from archive.split_contract import identity
from archive.split_jobs import Splitter


class SplitServer(unittest.TestCase):
    def test_registered_files_host_origin_and_ranges(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);file=root/'video.mp4';file.write_bytes(b'0123456789')
            manager=Manager(root/'absent');manager.splitter=Splitter(manager,root/'state')
            source='1'*32;manager.splitter.sources[source]={'path':str(file),'identity':identity(file)}
            audio=root/'preview.m4a';audio.write_bytes(b'0123456789')
            token='3'*32
            manager.splitter.audio_preview.cache[(source,1,0)]={'file':audio,'source':manager.splitter.sources[source],'info':{'id':token}}
            server,url=make_server(manager);thread=threading.Thread(target=server.serve_forever);thread.start()
            parsed=urlsplit(url);client=HTTPConnection(parsed.hostname,parsed.port,timeout=5)
            def call(method,path,headers=None,body=None):
                client.request(method,parsed.path+path,body=body,headers=headers or {})
                r=client.getresponse();data=r.read();return r.status,dict(r.getheaders()),data
            try:
                code,headers,data=call('GET','split-file?source='+source,{'Range':'bytes=2-5'})
                self.assertEqual((code,data),(206,b'2345'));self.assertEqual(headers['Content-Range'],'bytes 2-5/10')
                self.assertNotIn('unsafe-inline',headers['Content-Security-Policy'])
                self.assertEqual(call('GET','split-file?path='+str(file))[0],404)
                self.assertEqual(call('GET','split-file?source='+'2'*32)[0],404)
                self.assertEqual(call('GET','split-file?source='+source,{'Origin':'https://example.com'})[0],403)
                self.assertEqual(call('POST','api/split-register',{'Origin':'https://example.com','Content-Type':'application/json'},json.dumps({'path':str(file)}))[0],403)
                self.assertEqual(call('GET','video-split.html',{'Host':'example.com'})[0],403)
                self.assertEqual(call('GET','video-split.html')[0],200)
                self.assertEqual(call('GET','video-split-delete.js')[0],200)
                self.assertEqual(call('GET','video-split-audio.js')[0],200)
                code,headers,data=call('GET','split-audio?id='+token,{'Range':'bytes=2-5'})
                self.assertEqual((code,data),(206,b'2345'));self.assertEqual(headers['Content-Type'],'audio/mp4')
                self.assertEqual(call('GET','split-audio?id='+token,{'Origin':'https://example.com'})[0],403)
                self.assertEqual(call('GET','split-audio?id='+'4'*32)[0],404)
                self.assertEqual(call('GET','split-audio?path='+str(audio))[0],404)
                self.assertEqual(call('POST','api/split-delete',{'Origin':'https://example.com','Content-Type':'application/json'},json.dumps({'id':'a'*32,'token':'invalid'}))[0],403)
                file.write_bytes(b'changed')
                self.assertEqual(call('GET','split-file?source='+source)[0],404)
                self.assertFalse((root/'absent').exists())
            finally:client.close();server.shutdown();server.server_close();thread.join();manager.close()


if __name__=='__main__':unittest.main()
