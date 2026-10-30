"""HLS 형식 오류를 구별하면서 원격 서명 URL과 로그 원문을 보존한다."""
from pathlib import Path
import tempfile
import unittest

from archive.media_errors import failure_message


class MediaFormatErrorTests(unittest.TestCase):
    def test_hls_format_errors_are_distinct_and_do_not_expose_url(self):
        messages = (
            ('detected format mov,mp4 extension mp4 mismatches allowed extensions in url', '내부 형식'),
            ('URL https://example.invalid/file.bin is not in allowed_segment_extensions', '허용하지 않는'),
        )
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder)/'range.part.log'
            for message, expected in messages:
                original = (message+' https://example.invalid/clip.m4v?token=private\n'
                            'Error opening input: Invalid data found when processing input').encode()
                log.write_bytes(original)
                for executable in ('ffmpeg', 'ffmpeg.exe'):
                    result = failure_message([executable], 183, log)
                    self.assertIn(expected, result)
                    self.assertIn(str(log.resolve()), result)
                    self.assertNotIn('example.invalid', result)
                    self.assertNotIn('token=private', result)
                    self.assertNotIn('메모리', result)
                self.assertEqual(log.read_bytes(), original)

    def test_generic_invalid_data_is_not_assumed_to_be_extension_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder)/'range.part.log'
            log.write_text('Invalid data found when processing input', encoding='utf-8')
            self.assertIn('처리 로그', failure_message(['ffmpeg'], 183, log))


if __name__ == '__main__':
    unittest.main()
