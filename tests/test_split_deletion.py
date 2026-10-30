"""삭제 범위·원본 보존·중단 및 부분 실패 복구 검사. 실제 사용자 파일은 사용하지 않는다."""
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from archive import split_contract as contract
from archive.split_jobs import Splitter
from archive.storage import Conflict, ProjectLock, read_json, save_json


class SplitDeletion(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.manager = SimpleNamespace(guard=threading.RLock())
        self.splitter = Splitter(self.manager, self.root/'records')
        self.manager.speech_idle = self.splitter.idle
        source = self.root/'원본.mp4'; source.write_bytes(b'original video')
        self.source = {'path': str(source), 'name': source.name, 'identity': contract.identity(source)}
        self.folder = self.root/'분할 결과'; self.folder.mkdir()
        output = self.folder/'part.mp4'; output.write_bytes(b'generated clip')
        self.id = 'a'*32; self.file = self.splitter.file(self.id)
        self.value = {'id': self.id, 'source_id': 'b'*32, 'source': self.source,
                      'created_at': '2026-10-29T00:00:00Z', 'state': 'complete', 'message': '완료',
                      'folder': str(self.folder), 'folder_identity': [self.folder.stat().st_dev, self.folder.stat().st_ino],
                      'plan': {'parts': [{'name': 'part.mp4'}]},
                      'outputs': {'0': {'name': 'part.mp4', 'identity': contract.identity(output)}}}
        save_json(self.file, self.value); (self.file.parent/'ffmpeg.log').write_text('log')
        self.trash = self.root/'fake-trash'; self.trash.mkdir(); self.moved = []
        def move(path):
            self.moved.append(path)
            path.rename(self.trash/str(len(self.moved)))
        self.mover = patch('archive.split_deletion.trash_path', side_effect=move)
        self.move = self.mover.start()

    def tearDown(self):
        self.mover.stop()
        self.assertEqual(Path(self.source['path']).read_bytes(), b'original video')
        self.temp.cleanup()

    def preview(self):
        return self.splitter.dispatch('delete-preview', {'id': self.id})

    def delete(self, value=None):
        value = value or self.preview()
        return self.splitter.dispatch('delete', {'id': self.id, 'token': value['token']})

    def test_preview_cancel_and_delete_completed_job(self):
        before = contract.identity(Path(self.source['path']))
        value = self.preview()
        self.assertEqual(value['output_count'], 1)
        self.move.assert_not_called(); self.assertTrue(self.file.exists())
        self.assertTrue(self.delete(value)['deleted'])
        self.assertFalse(self.file.parent.exists()); self.assertFalse(self.folder.exists())
        self.assertEqual(self.splitter.dispatch('list', {})['runs'], [])
        self.assertEqual(contract.identity(Path(self.source['path'])), before)
        self.assertEqual((self.trash/'1'/'part.mp4').read_bytes(), b'generated clip')
        self.assertTrue((self.trash/'2'/'ffmpeg.log').is_file())

    def test_ready_job_only_removes_record(self):
        for key in ('folder', 'folder_identity'): self.value.pop(key)
        self.value.update(state='ready', outputs={}); save_json(self.file, self.value)
        self.delete()
        self.assertTrue(self.folder.is_dir()); self.assertEqual(self.moved, [self.file.parent])

    def test_changed_token_or_result_and_foreign_files_block_before_any_move(self):
        value = self.preview(); (self.file.parent/'ffmpeg.log').write_text('changed log')
        with self.assertRaisesRegex(Conflict, '바뀌었습니다'): self.delete(value)
        (self.folder/'part.mp4').write_bytes(b'edited video')
        with self.assertRaisesRegex(Conflict, '변경되었습니다'): self.preview()
        (self.folder/'part.mp4').unlink()
        (self.folder/'user.txt').write_text('사용자 자료')
        with self.assertRaisesRegex(Conflict, '작업 외 파일'): self.preview()
        self.move.assert_not_called()

    def test_symlink_and_original_hardlink_block(self):
        output = self.folder/'part.mp4'; output.unlink(); output.symlink_to(self.source['path'])
        with self.assertRaises(ValueError): self.preview()
        output.unlink(); output.hardlink_to(self.source['path'])
        self.value['outputs']['0']['identity'] = contract.identity(output); save_json(self.file, self.value)
        with self.assertRaisesRegex(Conflict, '원본 영상'): self.preview()
        self.move.assert_not_called()

    def test_other_job_source_and_unselected_job_preserved(self):
        second = self.splitter.file('c'*32)
        other = dict(self.value, id='c'*32, source_id='d'*32,
                     source={'path': str(self.folder/'part.mp4'), 'name': 'part.mp4',
                             'identity': contract.identity(self.folder/'part.mp4')})
        other.pop('folder'); other.pop('folder_identity'); other['outputs'] = {}
        save_json(second, other)
        with self.assertRaisesRegex(Conflict, '원본으로 사용하는 작업'): self.preview()
        other['source'] = self.source; save_json(second, other)
        # 다른 기록 자체는 지우지 않는다.
        self.delete(); self.assertTrue(second.exists())

    def test_source_inside_folder_blocks(self):
        self.value['source'] = dict(self.source, path=str(self.folder/'original.mp4'))
        save_json(self.file, self.value)
        with self.assertRaisesRegex(Conflict, '원본으로 사용하는 작업'): self.preview()

    def test_active_job_and_other_process_lock_block(self):
        self.splitter.job = SimpleNamespace(closed=False)
        with self.assertRaises(Conflict): self.preview()
        self.splitter.job = None
        with ProjectLock(self.splitter.root):
            with self.assertRaises((Conflict, OSError)): self.preview()
        self.move.assert_not_called()

    def test_missing_drive_and_changed_folder_block(self):
        self.folder.rename(self.root/'moved')
        with self.assertRaisesRegex(Conflict, '출력 폴더를 찾을 수 없습니다'): self.preview()
        self.folder.mkdir()
        with self.assertRaisesRegex(Conflict, '다른 폴더'): self.preview()
        self.move.assert_not_called()

    def test_output_failure_keeps_every_record_and_file(self):
        self.move.side_effect = OSError('디스크 오류')
        with self.assertRaises(OSError): self.delete()
        self.assertTrue(self.file.exists()); self.assertTrue((self.folder/'part.mp4').exists())
        self.assertNotIn('deleted_output_folder', read_json(self.file))

    def test_record_failure_can_retry_without_output_drive(self):
        move = self.move.side_effect
        def fail_record(path):
            if path == self.file.parent: raise OSError('기록 폴더 잠김')
            move(path)
        self.move.side_effect = fail_record
        with self.assertRaises(OSError): self.delete()
        self.assertFalse(self.folder.exists()); self.assertTrue(self.file.exists())
        self.assertTrue(read_json(self.file)['deleted_output_folder'])
        with self.assertRaisesRegex(Conflict, '삭제 중인 작업'):
            self.splitter.dispatch('resume', {'id': self.id})
        self.move.side_effect = move
        self.delete(); self.assertFalse(self.file.parent.exists())

    def test_recorded_crash_temporary_files_are_included(self):
        attempt = self.folder/'.split-owned123'; attempt.mkdir()
        for name in ('part-000.mp4', 'closed.csv', 'progress.txt'): (attempt/name).write_text('temporary')
        self.value['command'] = ['ffmpeg', str(attempt/'part-%03d.mp4')]; save_json(self.file, self.value)
        self.delete(); self.assertTrue((self.trash/'1'/attempt.name/'part-000.mp4').is_file())

    def test_unrecorded_temporary_folder_is_not_deleted(self):
        (self.folder/'.split-unknown').mkdir()
        with self.assertRaisesRegex(Conflict, '작업 외 파일'): self.delete()
        self.move.assert_not_called()

    def test_macos_metadata_sidecars_follow_owned_files_only(self):
        sidecar = self.folder/'._part.mp4'; sidecar.write_bytes(b'\x00\x05\x16\x07\x00\x02\x00\x00metadata')
        (self.folder/'.DS_Store').write_bytes(b'\x00\x00\x00\x01Bud1metadata')
        self.delete(); self.assertTrue((self.trash/'1'/sidecar.name).is_file())

    def test_fake_or_foreign_sidecars_block(self):
        sidecar = self.folder/'._part.mp4'; sidecar.write_bytes(b'personal file')
        with self.assertRaisesRegex(Conflict, '작업 외 파일'): self.preview()
        sidecar.unlink()
        (self.folder/'._unrelated.mp4').write_bytes(b'\x00\x05\x16\x07\x00\x02\x00\x00metadata')
        with self.assertRaisesRegex(Conflict, '작업 외 파일'): self.preview()
        self.move.assert_not_called()


if __name__ == '__main__': unittest.main()
