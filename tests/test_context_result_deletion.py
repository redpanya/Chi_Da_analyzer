"""임시 보관함에서 문맥 버전 삭제·실패 복구·자료 보존을 검사한다."""
from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from archive import context_job as store, context_comments, result_deletion
from archive.jobs import Manager
from archive.storage import Conflict, ProjectLock, create_or_load, save_json
from test_archive import metadata


class ContextResultDeletionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root = Path(temp.name);self.path = self.root/'vod-1'
        with ProjectLock(self.path):create_or_load(self.path, metadata('1'), '360p')
        self.ids = ['a'*32, 'b'*32, 'c'*32]
        runs = [dict(id=id, mode=mode) for id, mode in zip(self.ids, ['detail', 'timestamps', 'clips'])]
        save_json(store.local(self.path, 'state.json'), dict(state='paused', action='timestamps',
            run=self.ids[1], full_run=self.ids[0], clip_run=self.ids[2], runs=runs, progress={'done':3}))
        for id in self.ids:save_json(store.local(self.path, f'runs/{id}/result.json'), {'원본':id})
        self.preserved = [self.path/'media/original.mp4', self.path/'chat/messages.json',
            self.path/'speech/corrections.json', self.path/'voices/manual.json',
            store.local(self.path, f'comments/{self.ids[1]}.json')]
        for file in self.preserved:save_json(file, {'유지':'원본과 수동 입력'})
        self.before = {file:file.read_bytes() for file in self.preserved}
        self.trash = self.root/'trash';self.trash.mkdir()

    def move(self, folder):folder.rename(self.trash/folder.name)

    def test_each_mode_only_moves_selected_folder_and_clears_its_pointers(self):
        for id in self.ids:
            with patch('archive.deletion.trash_path', side_effect=self.move):result_deletion.context(self.path, id)
            self.assertTrue((self.trash/id/'result.json').is_file())
            value = store.state(self.path)
            self.assertNotIn(id, [r['id'] for r in value['runs']])
            for key in ('run', 'full_run', 'clip_run'):self.assertNotEqual(value.get(key), id)
            self.assertIn(id, value['deleted_runs'])
            if id == self.ids[0]:self.assertEqual(value['action'], 'timestamps')
            if id == self.ids[1]:self.assertEqual(value['state'], 'idle')
            for file, content in self.before.items():self.assertEqual(file.read_bytes(), content)
        with self.assertRaises(ValueError):context_comments.read(self.path, self.ids[1])

    def test_trash_failure_restores_catalog_and_preserves_all_files(self):
        before = {file:file.read_bytes() for file in self.path.rglob('*') if file.is_file() and file.name != '.write.lock'}
        with patch('archive.deletion.trash_path', side_effect=OSError('볼륨 사용 중')):
            with self.assertRaises(OSError):result_deletion.context(self.path, self.ids[1])
        self.assertEqual(before, {file:file.read_bytes() for file in self.path.rglob('*') if file.is_file() and file.name != '.write.lock'})

    def test_invalid_id_symlink_and_comment_write_lock_do_not_delete(self):
        with patch('archive.deletion.trash_path') as trash:
            for id in (None, '../escape', 'd'*32):
                with self.assertRaises(ValueError):result_deletion.context(self.path, id)
            with ProjectLock(store.local(self.path, 'comments')):
                with self.assertRaises(Conflict):result_deletion.context(self.path, self.ids[0])
            store.local(self.path, f'runs/{self.ids[0]}/link').symlink_to(self.preserved[0])
            with self.assertRaises(ValueError):result_deletion.context(self.path, self.ids[0])
            trash.assert_not_called()

    def test_delete_while_analysis_owns_chat_but_not_context(self):
        manager = Manager(self.root)
        self.addCleanup(manager.close)
        with ProjectLock(self.path, read=['chat'], write=['analysis']):
            with patch('archive.deletion.trash_path', side_effect=self.move):
                manager.context_delete(str(self.root), '1', self.ids[0])
        self.assertTrue((self.trash/self.ids[0]/'result.json').is_file())
        self.assertEqual([r['id'] for r in store.state(self.path)['runs']], self.ids[1:])

    def test_two_deletes_cannot_change_the_same_catalog_concurrently(self):
        writer, other = Manager(self.root), Manager(self.root)
        self.addCleanup(writer.close)
        self.addCleanup(other.close)
        entered, release = threading.Event(), threading.Event()
        def move(folder):
            entered.set()
            self.assertTrue(release.wait(10))
            self.move(folder)
        with patch('archive.deletion.trash_path', side_effect=move) as trash, ThreadPoolExecutor(1) as pool:
            first = pool.submit(writer.context_delete, str(self.root), '1', self.ids[0])
            try:
                self.assertTrue(entered.wait(10))
                catalog = store.local(self.path, 'state.json')
                state = catalog.read_bytes()
                with self.assertRaises(Conflict):
                    other.context_delete(str(self.root), '1', self.ids[1])
                self.assertEqual(catalog.read_bytes(), state)
                self.assertTrue(store.local(self.path, f'runs/{self.ids[1]}/result.json').is_file())
                trash.assert_called_once()
            finally:
                release.set()
            first.result(10)
        with ProjectLock(self.path):
            with self.assertRaises(Conflict):
                other.context_delete(str(self.root), '1', self.ids[1])
        self.assertEqual([r['id'] for r in store.state(self.path)['runs']], self.ids[1:])
