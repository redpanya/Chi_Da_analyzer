"""로캘과 무관한 미디어 JSON 읽기 및 Windows 읽기 스레드 오류 재현."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from archive import video

INFO = {'streams': [{'codec_type': 'video', 'codec_name': 'h264'},
                    {'codec_type': 'audio', 'codec_name': 'aac'}],
        'format': {'duration': '1.0', 'filename': '한글 폴더/영상 🤩.mp4',
                   'tags': {'title': '다국어 제목 日本語 é 🤩'}}}
PAYLOAD = json.dumps(INFO, ensure_ascii=False).encode('utf-8')
COMMAND = [sys.executable, '-c', f'import sys;sys.stdout.buffer.write(bytes.fromhex("{PAYLOAD.hex()}"))']


class MediaProbeTests(unittest.TestCase):
    def test_utf8_output_preserves_unicode_under_legacy_locale(self):
        run = subprocess.run
        # ffprobe와 같은 UTF-8 바이트를 실제 파이프로 받는다. 시스템 설정은 바꾸지 않는다.
        with patch('subprocess._text_encoding', return_value='cp949'), \
                patch('archive.video.subprocess.run', side_effect=lambda args, **kw: run(COMMAND, **kw)):
            self.assertEqual(video.probe(Path('사용자 영상.mp4')), INFO)

    @unittest.skipUnless(os.name == 'nt', 'Windows 읽기 스레드 전용')
    def test_old_text_mode_reproduces_reported_none_type_error(self):
        errors = []
        with patch.object(threading, 'excepthook', side_effect=lambda args: errors.append(args.exc_value)):
            result = subprocess.run(COMMAND, capture_output=True, text=True, encoding='cp949', timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIsNone(result.stdout)
        self.assertTrue(any(isinstance(error, UnicodeDecodeError) for error in errors))
        with self.assertRaisesRegex(TypeError, 'not NoneType'):
            json.loads(result.stdout)

    def test_empty_malformed_and_wrong_shape_are_readable_errors(self):
        for output in (None, b'', b'\xff', b'{', b'null', b'[]', b'{}',
                       b'{"streams": [null], "format": {}}'):
            with self.subTest(output=output), patch('archive.video.subprocess.run',
                    return_value=subprocess.CompletedProcess([], 0, output, b'')):
                with self.assertRaisesRegex(ValueError, 'ffprobe JSON'):
                    video.probe(Path('original.mp4'))

    def test_tool_failure_remains_distinct_from_json_failure(self):
        with patch('archive.video.subprocess.run', return_value=subprocess.CompletedProcess([], 1, b'', b'error')):
            with self.assertRaisesRegex(ValueError, '영상 파일을 읽을 수 없습니다'):
                video.probe(Path('original.mp4'))

    def test_duration_and_video_requirements_still_apply(self):
        for duration in (None, 'N/A', 'NaN', 'Infinity', 0, -1):
            output = json.dumps(INFO | {'format': {'duration': duration}}).encode()
            with self.subTest(duration=duration), patch('archive.video.subprocess.run',
                    return_value=subprocess.CompletedProcess([], 0, output, b'')):
                with self.assertRaisesRegex(ValueError, '영상 길이'):
                    video.probe(Path('original.mp4'))
        output = json.dumps(INFO | {'streams': [{'codec_type': 'audio'}]}).encode()
        with patch('archive.video.subprocess.run', return_value=subprocess.CompletedProcess([], 0, output, b'')):
            with self.assertRaisesRegex(ValueError, '영상 트랙'):
                video.probe(Path('original.mp4'))

    def test_timeout_and_filesystem_errors_are_not_hidden(self):
        for error in (subprocess.TimeoutExpired('ffprobe', 30), FileNotFoundError(), PermissionError()):
            with self.subTest(error=type(error).__name__), patch('archive.video.subprocess.run', side_effect=error):
                with self.assertRaises(type(error)):
                    video.probe(Path('original.mp4'))


if __name__ == '__main__':
    unittest.main()
