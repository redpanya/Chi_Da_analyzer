"""저장 경계, 중복 실행, 중단 복구와 제공 범위 판정의 회귀 검사."""

import csv
import errno
from http.client import HTTPConnection
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import urlsplit

from archive import chat, source
from archive.jobs import Manager
from archive.server import make_server, byte_range
from archive.storage import (Conflict, ProjectLock, Project, create_or_load, load_project,
                             project_path, read_json, recover, save_json, asset_path)


def metadata(vod='1', enabled=True):
    return {'id': vod, 'title': '검증 방송', 'channel': '검증 채널', 'duration': 3,
            'chat_enabled': enabled, 'formats': [{'id': '360p', 'estimated_bytes': 10}],
            'url': f'https://chzzk.naver.com/video/{vod}'}


def message(offset, text='ㅋㅋ'):
    return {'playerMessageTime': offset, 'messageTime': 1791510000000 + offset,
            'content': text, 'profile': '{"nickname":"검증"}'}


def page(messages, following):
    return {'code': 200, 'content': {'videoChats': messages, 'previousVideoChats': [], 'nextPlayerMessageTime': following}}


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='치지직 M1 검사 ')
        self.root = Path(self.temp.name)
        self.locks = []

    def tearDown(self):
        for lock in self.locks:
            lock.close()
        self.temp.cleanup()

    def project(self, vod='1', enabled=True):
        path = project_path(self.root, vod)
        lock = ProjectLock(path)
        self.locks.append(lock)
        return Project(path, create_or_load(path, metadata(vod, enabled), '360p'), lock)

    def test_vod_directory_identity_and_quality(self):
        project = self.project()
        self.assertNotEqual(project.path, project_path(self.root, '2'))
        with self.assertRaises(Conflict):
            create_or_load(project.path, metadata('2'), '360p')
        with self.assertRaises(Conflict):
            create_or_load(project.path, metadata(), '1080p')
        self.assertEqual(load_project(project.path, '1')['format_id'], '360p')

    def test_unowned_and_symlink_directories_not_adopted(self):
        path = project_path(self.root, '1')
        with ProjectLock(path):
            (path / 'original.mp4').write_bytes('보존'.encode())
            with self.assertRaises(Conflict) as error:
                create_or_load(path, metadata(), '360p')
            self.assertIn(str(path), str(error.exception))
            self.assertIn('original.mp4', str(error.exception))
            self.assertFalse((path / 'project.json').exists())
            self.assertEqual((path / 'original.mp4').read_bytes(), '보존'.encode())
        (self.root / 'vod-2').symlink_to(path, target_is_directory=True)
        with self.assertRaises(Conflict):
            project_path(self.root, '2')

    def test_macos_metadata_allows_first_download_and_resume(self):
        path = project_path(self.root, '1')
        path.mkdir()
        files = {name: b'macOS metadata' for name in ('.DS_Store', '._.DS_Store', '._.write.lock')}
        for name, content in files.items():
            (path / name).write_bytes(content)
        manager = Manager(self.root)
        manager.metadata['1'] = metadata()
        entered = {kind: threading.Event() for kind in ('video', 'chat')}
        def work(kind):
            def run(project, stop):
                entered[kind].set()
                stop.wait(5)
                source.check_cancel(stop)
            return run
        with patch('archive.jobs.video.download', work('video')), patch('archive.jobs.chat.collect', work('chat')):
            for _ in range(2):
                try:
                    manager.start(str(self.root), '1', '360p', 'all')
                    for event in entered.values():
                        self.assertTrue(event.wait(2))
                        event.clear()
                finally:
                    manager.close()
                data = load_project(path, '1')
                self.assertTrue(all(task['state'] == 'paused' for task in data['tasks'].values()))
        self.assertEqual({name: (path / name).read_bytes() for name in files}, files)

    def test_metadata_names_do_not_allow_directories_symlinks_or_other_hidden_files(self):
        outside = self.root / '보존.txt'
        outside.write_bytes(b'keep')
        cases = [(name, kind) for name in ('.DS_Store', '._.DS_Store', '._.write.lock')
                 for kind in ('directory', 'symlink')]
        cases += [('._original.mp4', 'file'), ('.unknown', 'file')]
        for index, (name, kind) in enumerate(cases, 1):
            with self.subTest(name=name, kind=kind):
                vod = str(index)
                path = project_path(self.root, vod)
                with ProjectLock(path):
                    entry = path / name
                    if kind == 'directory':
                        entry.mkdir()
                    elif kind == 'symlink':
                        entry.symlink_to(outside)
                    else:
                        entry.write_bytes(b'keep')
                    with self.assertRaises(Conflict):
                        create_or_load(path, metadata(vod), '360p')
                    self.assertFalse((path / 'project.json').exists())
                    self.assertTrue(entry.exists())
        self.assertEqual(outside.read_bytes(), b'keep')

    def test_lock_survives_inheriting_media_child(self):
        path = project_path(self.root, '1')
        lock = ProjectLock(path)
        child = subprocess.Popen([sys.executable, '-c', 'import time; print("준비", flush=True); time.sleep(.5)'], pass_fds=(lock.fd,), stdout=subprocess.PIPE, text=True)
        child.stdout.readline()
        lock.close()
        try:
            with self.assertRaises(Conflict):
                ProjectLock(path)
        finally:
            child.wait()
            child.stdout.close()
        with ProjectLock(path):
            pass

    def test_stale_running_state_recovers_without_losing_progress(self):
        project = self.project()
        project.update('video', state='downloading', progress={'downloaded_bytes': 123})
        project.lock.close()
        data = Manager(self.root).view(str(self.root), '1')
        self.assertEqual(data['tasks']['video']['state'], 'paused')
        self.assertEqual(data['tasks']['video']['progress']['downloaded_bytes'], 123)

    def test_missing_complete_asset_requires_retry(self):
        project = self.project()
        project.update('video', state='complete', assets={'original': 'media/original.mp4'})
        self.assertEqual(recover(project.path, project.snapshot())['tasks']['video']['state'], 'error')
        outside = self.root / 'secret.txt'
        outside.write_text('보호')
        with self.assertRaises(ValueError):
            asset_path(project.path, '../secret.txt')

    def test_atomic_write_failure_keeps_last_manifest(self):
        project = self.project()
        path = project.path / 'project.json'
        before = path.read_bytes()
        with patch('archive.storage.os.replace', side_effect=OSError(errno.ENOSPC, '공간 부족')):
            with self.assertRaises(OSError):
                save_json(path, {'덮어쓰면 안 됨': True})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(project.path.glob('*.tmp')), [])

    def test_failed_update_keeps_memory_and_disk_consistent(self):
        project = self.project()
        before = project.snapshot()
        with patch('archive.storage.save_json', side_effect=OSError(errno.ENOSPC, '공간 부족')):
            with self.assertRaises(OSError):
                project.update('video', state='queued')
        self.assertEqual(project.snapshot(), before)
        self.assertEqual(read_json(project.path / 'project.json'), before)

    def test_failed_start_releases_ownership_and_can_retry(self):
        project = self.project()
        project.lock.close()
        manager = Manager(self.root)
        with patch('archive.storage.save_json', side_effect=OSError(errno.ENOSPC, '공간 부족')):
            with self.assertRaises(OSError):
                manager.start(str(self.root), '1', '360p', 'video')
        self.assertIsNone(manager.job)
        with ProjectLock(project.path):
            pass
        with patch('archive.jobs.video.download', side_effect=source.Cancelled):
            manager.start(str(self.root), '1', '360p', 'video')
            manager.close()
        self.assertEqual(manager.view(str(self.root), '1')['tasks']['video']['state'], 'paused')

    def test_read_only_page_directory_preserves_failure(self):
        project = self.project()
        pages = project.path / 'chat-pages'
        pages.mkdir()
        pages.chmod(0o555)
        try:
            with patch('archive.chat.fetch', return_value=page([message(1)], None)), self.assertRaises(PermissionError):
                chat.collect(project, threading.Event())
            self.assertEqual(list(pages.iterdir()), [])
            self.assertNotEqual(project.data['tasks']['chat']['state'], 'complete')
        finally:
            pages.chmod(0o755)

    def test_duplicate_start_and_independent_stop(self):
        manager, other = Manager(self.root), Manager(self.root)
        manager.metadata['1'] = metadata()
        entered = {kind: threading.Event() for kind in ('video', 'chat')}
        def work(kind):
            def run(project, stop):
                entered[kind].set()
                stop.wait(5)
                source.check_cancel(stop)
            return run
        with patch('archive.jobs.video.download', work('video')), patch('archive.jobs.chat.collect', work('chat')):
            manager.start(str(self.root), '1', '360p', 'all')
            for event in entered.values():
                self.assertTrue(event.wait(2))
            with self.assertRaises(Conflict):
                manager.start(str(self.root), '1', '360p', 'all')
            with self.assertRaises(Conflict):
                manager.start(str(self.root), '2', '360p', 'all')
            with self.assertRaises(Conflict):
                other.start(str(self.root), '1', '360p', 'all')
            manager.stop(str(self.root), '1', 'video')
            self.assertFalse(manager.job.stops['chat'].is_set())
            manager.job.workers['video'].join(timeout=2)
            manager.start(str(self.root), '1', '360p', 'video')
            self.assertFalse(manager.job.stops['video'].is_set())
            self.assertFalse(manager.job.stops['chat'].is_set())
            manager.close()
        self.assertEqual(manager.view(str(self.root), '1')['tasks']['video']['state'], 'paused')

    def test_complete_tasks_are_not_redownloaded(self):
        project = self.project()
        for kind in ('video', 'chat'):
            project.update(kind, state='complete')
        project.lock.close()
        with patch('archive.jobs.video.download') as download:
            result = Manager(self.root).start(str(self.root), '1', '360p', 'all')
            self.assertFalse(result['locked'])
            download.assert_not_called()

    def test_chat_pause_resume_preserves_repeats_and_exports(self):
        project, stop = self.project(), threading.Event()
        repeated = message(1000, '=검증\nㅋㅋ')
        def first(vod, cursor, event):
            stop.set()
            return page([repeated, repeated], 1000)
        with patch('archive.chat.fetch', side_effect=first):
            chat.collect(project, stop)
        original = (project.path / 'chat-pages/000000.json').read_bytes()
        sidecar = project.path / 'chat-pages/._000000.json'
        sidecar.write_bytes(bytes.fromhex('0005160700020000'))
        first_assets = project.snapshot()['tasks']['chat']['assets']
        self.assertEqual(project.data['tasks']['chat']['state'], 'paused')
        stop.clear()
        def resumed(vod, cursor, event):
            return page([message(2000)], None) if cursor == 1000 else page([repeated, repeated], 1000)
        with patch('archive.chat.fetch', side_effect=resumed):
            chat.collect(project, stop)
        task = project.snapshot()['tasks']['chat']
        self.assertEqual(task['state'], 'complete')
        self.assertEqual((project.path / 'chat-pages/000000.json').read_bytes(), original)
        self.assertEqual(sidecar.read_bytes(), bytes.fromhex('0005160700020000'))
        self.assertTrue((project.path / first_assets['json']).exists())
        rows = read_json(project.path / task['assets']['json'])['messages']
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['text'], '=검증\nㅋㅋ')
        with (project.path / task['assets']['csv']).open(encoding='utf-8-sig', newline='') as file:
            exported = list(csv.DictReader(file))
        self.assertEqual(exported[0]['text'], "'=검증\nㅋㅋ")
        self.assertEqual(len(exported), 3)

    def test_boundary_missing_message_is_not_complete(self):
        project = self.project()
        responses = [page([message(1)], None), page([message(1), message(1, '누락')], None)]
        with patch('archive.chat.fetch', side_effect=responses):
            chat.collect(project, threading.Event())
        self.assertEqual(project.data['tasks']['chat']['state'], 'review')

    def test_macos_sidecar_does_not_hide_a_real_page_gap(self):
        project = self.project()
        pages = project.path / 'chat-pages'
        pages.mkdir()
        save_json(pages / '000001.json', {'vod_id': '1', 'cursor': 0, 'response': page([], None)})
        (pages / '._000001.json').write_bytes(bytes.fromhex('0005160700020000'))
        with patch('archive.chat.fetch') as fetch, self.assertRaisesRegex(ValueError, '빈 구간'):
            chat.collect(project, threading.Event())
        fetch.assert_not_called()
        self.assertFalse((pages / '000000.json').exists())
        self.assertTrue((pages / '000001.json').exists())

    def test_unavailable_and_empty_are_distinct(self):
        disabled = self.project('1', False)
        with patch('archive.chat.fetch') as fetch:
            chat.collect(disabled, threading.Event())
            fetch.assert_not_called()
        enabled = self.project('2')
        with patch('archive.chat.fetch', return_value=page([], None)):
            chat.collect(enabled, threading.Event())
        self.assertEqual(disabled.data['tasks']['chat']['state'], 'unavailable')
        self.assertEqual(enabled.data['tasks']['chat']['state'], 'empty')

    def test_error_response_does_not_poison_resume_cursor(self):
        project = self.project()
        with patch('archive.chat.fetch', return_value={'code': 403, 'content': None}), self.assertRaises(ValueError):
            chat.collect(project, threading.Event())
        self.assertEqual(list((project.path / 'chat-pages').glob('*.json')), [])
        self.assertEqual(len(list((project.path / 'diagnostics').glob('chat-error-*.json'))), 1)
        with patch('archive.chat.fetch', return_value=page([], None)):
            chat.collect(project, threading.Event())
        self.assertEqual(project.data['tasks']['chat']['state'], 'empty')

    def test_cursor_and_page_validation(self):
        self.assertEqual(chat.validate(page([], 5), 0), ([], 5))
        for response in (page([], 0), page([], True), page([message(2), message(1)], 3), {'code': 200, 'content': {}}):
            with self.assertRaises(ValueError):
                chat.validate(response, 0)

    def test_url_boundaries_and_retry_limit(self):
        self.assertEqual(source.resolve_url('https://chzzk.naver.com/video/15143708?t=5'), '15143708')
        for value in ('http://chzzk.naver.com/video/1', 'https://other.test/video/1', 'https://chzzk.naver.com@other.test/video/1', 'https://chzzk.naver.com:443/video/1', 'https://chzzk.naver.com/video/../1'):
            with self.assertRaises(ValueError):
                source.resolve_url(value)
        stop = threading.Event()
        with patch('archive.source.urlopen', side_effect=URLError('중단')) as request, patch.object(stop, 'wait', return_value=False):
            with self.assertRaises(URLError):
                source.request_json('https://example.invalid', stop)
            self.assertEqual(request.call_count, 3)

    def test_http_origin_token_range_and_exports(self):
        project = self.project()
        (project.path / 'media').mkdir()
        (project.path / 'media/original.mp4').write_bytes(b'0123456789')
        project.update('video', state='complete', assets={'original': 'media/original.mp4'})
        project.lock.close()
        manager = Manager(self.root)
        server, url = make_server(manager)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        prefix = urlsplit(url).path.rstrip('/')
        def request(method, path, body=None, headers=None):
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            value = response.status, dict(response.getheaders()), response.read()
            connection.close()
            return value
        try:
            self.assertEqual(request('GET', '/')[0], 404)
            self.assertEqual(request('POST', prefix + '/api/projects', '{}', {'Content-Type': 'application/json', 'Origin': 'https://other.test'})[0], 403)
            self.assertEqual(request('GET', prefix + '/api/config')[0], 200)
            from urllib.parse import urlencode
            file = prefix + '/file?' + urlencode({'root': str(self.root), 'vod_id': '1', 'kind': 'video', 'key': 'original'})
            response = request('GET', file, headers={'Range': 'bytes=2-4'})
            self.assertEqual((response[0], response[2]), (206, b'234'))
            self.assertEqual(request('GET', file, headers={'Range': 'bytes=99-'})[0], 416)
            self.assertEqual(request('GET', file.replace('key=original', 'key=project.json'))[0], 404)
            self.assertEqual(request('HEAD', file)[2], b'')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
