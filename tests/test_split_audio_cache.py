"""전송 중 캐시와 Windows 삭제 거부가 새 미리듣기·원본을 손상하지 않는지 검사한다."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from archive import split_audio, split_contract
from archive.source import Cancelled


class PreviewCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source_file = Path(self.temp.name) / '원본.mp4'
        self.source_file.write_bytes(b'preserve original')
        self.source = {'path': str(self.source_file), 'identity': split_contract.identity(self.source_file),
                       'duration': 1200, 'streams': [{'index': 1, 'codec_type': 'audio'}]}
        self.preview = split_audio.Preview()
        self.capture = patch('archive.split_media.capture', side_effect=self.write_audio)
        self.probe = patch('archive.split_media.probe', return_value={
            'streams': [{'codec_name': 'aac', 'duration': '60'}]})
        self.capture.start(); self.probe.start()

    def tearDown(self):
        self.preview.close()
        self.capture.stop(); self.probe.stop()
        self.assertEqual(self.source_file.read_bytes(), b'preserve original')
        self.temp.cleanup()

    @staticmethod
    def write_audio(args, stop):
        Path(args[-1]).write_bytes(b'preview audio')

    def prepare(self, minute):
        return self.preview.prepare('a' * 32, self.source, 1, minute * 60)

    def test_locked_eviction_preserves_new_cache_and_retries_on_cache_hit(self):
        first = self.prepare(0)
        old = self.preview.file(first['id'])
        unlink = Path.unlink

        def locked(file, *args, **kwargs):
            if file == old:
                raise PermissionError('열린 파일 삭제 거부 재현')
            return unlink(file, *args, **kwargs)

        with patch.object(Path, 'unlink', locked):
            for minute in range(1, 9):
                newest = self.prepare(minute)
            self.assertTrue(self.preview.file(newest['id']).exists())
            self.assertEqual(len(self.preview.cache), 8)
            self.assertEqual(self.preview.pending, {first['id']: old})
            with self.assertRaises(ValueError):
                self.preview.file(first['id'])
        self.assertEqual(self.prepare(8), newest)
        self.assertFalse(old.exists())
        self.assertFalse(self.preview.pending)

    def test_http_borrow_survives_eviction_and_close_until_last_reader(self):
        first = self.prepare(0)
        with self.preview.borrow(first['id']) as file:
            with self.preview.borrow(first['id']):
                for minute in range(1, 9):
                    self.prepare(minute)
                self.assertTrue(file.exists())
                self.assertEqual(self.preview.readers[first['id']], 2)
                self.preview.close()
                self.assertTrue(file.exists())
                self.assertFalse(self.preview.cache)
                with self.assertRaises(Cancelled):
                    self.prepare(9)
            self.assertTrue(file.exists())
            self.assertEqual(self.preview.readers[first['id']], 1)
        self.assertFalse(file.exists())
        self.assertFalse(self.preview.readers)
        self.assertFalse(self.preview.pending)
        self.assertIsNone(self.preview.temp)

    def test_failed_transfer_releases_reader(self):
        first = self.prepare(0)
        with self.assertRaisesRegex(OSError, '전송 실패'):
            with self.preview.borrow(first['id']) as file:
                self.preview.close()
                raise OSError('전송 실패')
        self.assertFalse(file.exists())
        self.assertFalse(self.preview.readers)
        self.assertIsNone(self.preview.temp)

    def test_failed_generation_keeps_original_error_and_does_not_publish(self):
        with patch('archive.split_media.probe', return_value={'streams': []}), \
                patch.object(Path, 'unlink', side_effect=PermissionError('삭제 거부')):
            with self.assertRaisesRegex(ValueError, '재생할 오디오가 없습니다'):
                self.prepare(0)
        self.assertFalse(self.preview.cache)
        self.assertEqual(len(self.preview.pending), 1)
        orphan = next(iter(self.preview.pending.values()))
        self.preview.close()
        self.assertFalse(orphan.exists())
        self.assertIsNone(self.preview.temp)

    def test_shutdown_cleanup_error_can_be_retried(self):
        first = self.prepare(0)
        file = self.preview.file(first['id'])
        temp = self.preview.temp
        with patch.object(temp, 'cleanup', side_effect=PermissionError('폴더 정리 거부')):
            self.preview.close()
        self.assertFalse(file.exists())
        self.assertIs(self.preview.temp, temp)
        self.preview.close()
        self.assertIsNone(self.preview.temp)

    @unittest.skipUnless(os.name == 'nt', 'Windows 실제 열린 파일 삭제 제약 검사')
    def test_windows_open_handle_defers_unlink_without_failing_new_preview(self):
        first = self.prepare(0)
        old = self.preview.file(first['id'])
        with old.open('rb') as handle:
            for minute in range(1, 9):
                newest = self.prepare(minute)
            self.assertEqual(handle.read(), b'preview audio')
            self.assertTrue(self.preview.file(newest['id']).exists())
            self.assertEqual(self.preview.pending, {first['id']: old})
        self.prepare(8)
        self.assertFalse(old.exists())
        self.assertFalse(self.preview.pending)


if __name__ == '__main__':
    unittest.main()
