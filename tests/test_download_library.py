import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from archive import runtime
from archive.jobs import Manager
from archive.server import make_server
from archive.storage import LibraryFolderRequired, save_json
from archive.work_queue import execute, check_download_folder


class DownloadLibraryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name).resolve()
        self.enterContext(patch.object(runtime, 'SUPPORT', self.path/'settings'))
        self.manager = Manager()
        self.addCleanup(self.manager.close)

    def test_only_explicit_selection_persists(self):
        server, url = make_server(self.manager)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        address = urlsplit(url)
        def post(action, **data):
            conn = HTTPConnection(address.hostname, address.port, timeout=5)
            try:
                conn.request('POST', address.path+'api/'+action, json.dumps(data), {'Content-Type':'application/json'})
                response = conn.getresponse()
                return response.status, json.loads(response.read())
            finally:
                conn.close()

        folder = self.path/'저장할 폴더'
        folder.mkdir()
        for action in ('library-catalog', 'projects'):
            self.assertEqual(post(action, root=str(folder))[0], 200)
        self.assertIsNone(runtime.saved_library())
        status, result = post('queue-add', root=str(folder), url='https://chzzk.naver.com/video/1')
        self.assertEqual((status, result['code']), (409, 'library_folder_required'))
        self.assertEqual(list(folder.iterdir()), [])
        self.assertEqual(post('library-folder', root=str(folder))[0], 200)
        self.assertEqual(runtime.saved_library(), folder)
        for other in (self.path, self.path/'없는 폴더'):
            post('library-catalog', root=str(other))
        self.assertEqual(post('library-folder', root=str(self.path/'없는 폴더'))[0], 400)
        with patch('archive.jobs.tempfile.TemporaryFile', side_effect=PermissionError):
            self.assertEqual(post('library-folder', root=str(self.path))[0], 400)
        self.assertEqual(runtime.saved_library(), folder)
        reopened = Manager()
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.download_library, str(folder))
        reopened.require_download_library(str(folder/'.download-ranges'/('a'*32)))
        with self.assertRaises(LibraryFolderRequired):
            reopened.require_download_library(str(self.path))
        folder.rmdir()
        with self.assertRaises(LibraryFolderRequired):
            reopened.require_download_library(str(folder))
        self.assertFalse(folder.exists())

    def test_download_paths_stop_before_queueing_or_receiving(self):
        root = str(self.path)
        data = {'root':root, 'vod_id':'1', 'kind':'video', 'format_id':'480p'}
        queue_file = self.path/'.automation/queue.json'
        save_json(queue_file, {'version':1, 'items':[{'id':'retry','vod':'1','state':'paused','options':{'steps':['download']}}]})
        run = 'a'*32
        manifest = self.path/'vod-1/studio/runs'/run/'manifest.json'
        save_json(manifest, {'kind':'remote','state':'paused'})
        for action, request in [('start', data), ('studio-remote', data), ('studio-resume', dict(data,run=run)),
                                ('video-quality', dict(data,existing='keep')), ('queue-start', {'root':root})]:
            with self.subTest(action=action):
                with self.assertRaises(LibraryFolderRequired):
                    self.manager.tasks.submit(action, request)
                with self.assertRaises(LibraryFolderRequired):
                    execute(self.manager, action, request)
        self.assertEqual(self.manager.tasks.items, [])
        with self.assertRaises(LibraryFolderRequired):
            self.manager.automation.remove_or_retry(root, 'retry', retry=True)
        self.assertEqual(self.manager.automation.read(root)['items'][0]['state'], 'paused')
        with self.assertRaises(LibraryFolderRequired):
            self.manager.automation.add_saved(root, ['1'], {})
        with self.assertRaises(LibraryFolderRequired):
            self.manager.start(root, '1', '480p', 'chat')
        save_json(queue_file, {'version':1,'items':[{'state':'queued','options':{'steps':['transcribe']}}]})
        check_download_folder(self.manager, 'queue-start', {'root':root})
        save_json(manifest, {'kind':'start','state':'paused'})
        check_download_folder(self.manager, 'studio-resume', dict(data,run=run))
