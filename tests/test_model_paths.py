"""모델 폴더 변경·기존 설정 보존·실행 중 차단·재시작 복원 검사."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

from archive import runtime, model_paths, speech_model, voice_models, context_model
from archive.jobs import Manager
from archive.server import make_server
from archive.storage import Conflict


class ModelPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.old = self.base/'기존 모델'; self.old.mkdir()
        (self.old/'보존.bin').write_bytes(b'original')
        for name, value in [('SUPPORT', self.base/'설정'), ('MODEL_ROOT', self.old), ('FROZEN', False)]:
            p = patch.object(runtime, name, value); p.start(); self.addCleanup(p.stop)
        runtime.save_settings(library=str(self.base/'보관함'), extra='기존 설정')
        self.manager = Manager(self.base/'보관함')

    def test_all_model_paths_and_restart_preserve_library_and_original(self):
        chosen = self.base/'한글 공용 모델'
        value = self.manager.model_folder(str(chosen))
        self.assertEqual(value['models'], str(chosen))
        self.assertFalse(any(value['ready'].values()))
        self.assertEqual(speech_model.model_path().parent, chosen)
        self.assertEqual(voice_models.home(), chosen/'voices')
        self.assertEqual(context_model.model_path().parent, chosen/'context')
        with patch.object(runtime, 'FROZEN', True):
            runtime.remember_library(str(self.base/'다른 보관함'))
        saved = runtime.settings()
        self.assertEqual(saved['models'], str(chosen)); self.assertEqual(saved['extra'], '기존 설정')
        self.assertEqual(saved['library'], str(self.base/'다른 보관함'))
        runtime.MODEL_ROOT = self.old
        runtime.configure()
        self.assertEqual(model_paths.root(), chosen)
        self.assertEqual((self.old/'보존.bin').read_bytes(), b'original')
        self.assertEqual(list(chosen.iterdir()), [])

    def test_invalid_paths_and_failed_persistence_keep_previous_settings(self):
        file = self.base/'파일'; file.write_text('유지')
        link = self.base/'연결'; link.symlink_to(self.old)
        child_link = self.base/'하위 연결'; child_link.mkdir(); (child_link/'voices').symlink_to(self.old)
        missing_drive = '/Volumes/chzzk-연결안됨-검증/models'
        before = (runtime.SUPPORT/'settings.json').read_bytes()
        for path in ['', None, 42, '상대/경로', str(file), str(link), str(child_link), str(self.base/'vod-123/models'), missing_drive]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.manager.model_folder(path)
            self.assertEqual(model_paths.root(), self.old)
            self.assertEqual((runtime.SUPPORT/'settings.json').read_bytes(), before)
        with patch.object(model_paths.tempfile, 'TemporaryFile', side_effect=PermissionError()):
            with self.assertRaisesRegex(ValueError, '쓸 수 없습니다'):
                self.manager.model_folder(str(self.base/'권한 실패'))
        with patch.object(runtime, 'save_settings', side_effect=OSError('설정 저장 실패')):
            with self.assertRaises(OSError): self.manager.model_folder(str(self.base/'저장 실패'))
        self.assertEqual(model_paths.root(), self.old)
        self.assertEqual((runtime.SUPPORT/'settings.json').read_bytes(), before)

    def test_all_jobs_block_change_even_stopping(self):
        for name in ['job', 'speech_job', 'voice_job', 'import_job', 'context_job']:
            with self.subTest(name=name):
                setattr(self.manager, name, SimpleNamespace(closed=False))
                self.assertTrue(self.manager.folders()['busy'])
                with self.assertRaises(Conflict): self.manager.model_folder(str(self.base/'변경'))
                setattr(self.manager, name, None)
        self.manager.analysis_path = self.base/'분석'
        with self.assertRaises(Conflict): self.manager.model_folder(str(self.base/'변경'))
        self.assertEqual(model_paths.root(), self.old)
        self.assertFalse((self.base/'변경').exists())

    def test_api_config_apply_read_and_invalid_do_not_replace_current(self):
        server, url = make_server(self.manager)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        parsed = urlsplit(url); conn = http.client.HTTPConnection(parsed.hostname, parsed.port)
        def request(method, action, data=None):
            conn.request(method, parsed.path+'api/'+action, json.dumps(data) if data is not None else None,
                         {'Content-Type': 'application/json'} if data is not None else {})
            response = conn.getresponse(); return response.status, json.loads(response.read())
        try:
            barrier = threading.Barrier(20)
            def load_module(index):
                client = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
                try:
                    barrier.wait(timeout=5)
                    client.request('GET', parsed.path+('folders.js' if index % 2 else 'app.js'))
                    response = client.getresponse()
                    return response.status, bool(response.read())
                finally: client.close()
            with ThreadPoolExecutor(max_workers=20) as pool:
                self.assertEqual(list(pool.map(load_module, range(20))), [(200, True)]*20)
            status, value = request('GET', 'config')
            self.assertEqual(status, 200); self.assertEqual(value['folders']['models'], str(self.old))
            chosen = str(self.base/'API 폴더')
            status, value = request('POST', 'model-folder', {'path': chosen})
            self.assertEqual(status, 200); self.assertEqual(value['models'], chosen)
            self.assertEqual(request('POST', 'folders', {})[1]['models'], chosen)
            new_library = str(self.base/'새 보관함')
            with patch.object(runtime, 'FROZEN', True):
                self.assertEqual(request('POST', 'projects', {'root': new_library})[0], 200)
            self.assertEqual(request('GET', 'config')[1]['root'], new_library)
            self.assertEqual(runtime.settings()['models'], chosen)
            self.assertEqual(request('POST', 'model-folder', {'path': '상대경로'})[0], 400)
            self.manager.speech_job = SimpleNamespace(closed=False)
            self.assertEqual(request('POST', 'model-folder', {'path': str(self.old)})[0], 409)
            self.assertEqual(model_paths.root(), Path(chosen))
        finally:
            conn.close(); server.shutdown(); server.server_close(); thread.join()
