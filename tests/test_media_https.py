"""TLS 검증 유지와 미디어 오류의 범용 분류·로그 경로 회귀 검사."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from archive import media_errors, remote_media, speech_media
from archive.storage import ProjectLock


class MediaHttpsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name).resolve()
        self.log = self.path/'한글 영상.part.log'

    def test_protocol_code_on_both_os_and_full_log_path(self):
        self.log.write_text('https://example.invalid/video?token=private\nProtocol not found', encoding='utf-8')
        before = self.log.read_bytes()
        for code in (-1330794744, 2964172552):
            text = media_errors.failure_message(['ffmpeg'], code, self.log)
            self.assertIn('HTTPS 지원', text)
            self.assertIn(str(self.log), text)
            self.assertIn('FFmpeg', text)
            self.assertNotIn('token=private', text)
            self.assertNotIn('메모리', text)
        self.assertEqual(self.log.read_bytes(), before)

    def test_certificate_disk_timeout_and_unknown_are_distinct(self):
        for line, expected in [('certificate verify failed', '인증서'),
                               ('SNI or certificate check failed', '인증서'),
                               ('Unable to negotiate TLS/SSL session: -9807', 'HTTPS 보안'),
                               ('Creating security context failed (0x80090325)', '인증서'),
                               ('No space left on device', '저장 공간'),
                               ('Connection timed out', '응답 시간'),
                               ('unknown error', '처리 로그')]:
            self.log.write_text(line, encoding='utf-8')
            self.assertIn(expected, media_errors.failure_message(['ffmpeg.exe'], 1, self.log))
        self.log.unlink()
        self.assertIn('처리 로그', media_errors.failure_message(['ffmpeg'], 1, self.log))

    def test_other_engine_does_not_get_ffmpeg_diagnosis(self):
        self.log.write_text('Protocol not found', encoding='utf-8')
        text = media_errors.failure_message(['whisper-cli'], 2964172552, self.log)
        self.assertIn('음성 처리', text)
        self.assertNotIn('HTTPS', text)
        self.assertIn(str(self.log), text)

    def test_shared_runner_uses_classification_without_removing_log(self):
        child = SimpleNamespace(returncode=2964172552, poll=lambda: 2964172552)
        with ProjectLock(self.path) as lock, patch('archive.speech_media.processes.popen', return_value=child):
            with self.assertRaisesRegex(ValueError, 'HTTPS 지원') as caught:
                speech_media.process(['ffmpeg'], self.log, threading.Event(), lock)
        self.assertIn(str(self.log), str(caught.exception))
        self.assertTrue(self.log.is_file())

    def test_remote_range_requires_tls_verification(self):
        url = 'https://example.invalid/source.mp4'
        with patch.object(remote_media, 'YoutubeDL') as downloader, \
             patch.object(remote_media.clip_render, 'command') as command, \
             patch.object(remote_media.clip_render, 'verify', return_value={'duration': 1}):
            downloader.return_value.__enter__.return_value.extract_info.return_value = {'url': url}
            result = remote_media.receive('1', 2000, 3000, self.path/'range.mp4',
                                          threading.Event(), None, lambda **v: None)
        self.assertEqual(result['duration'], 1)
        args = command.call_args.args[0]
        self.assertEqual(args[args.index('-tls_verify')+1], '1')
        self.assertLess(args.index('-tls_verify'), args.index('-i'))
        self.assertEqual(args[args.index('-i')+1], url)
        self.assertEqual(args[args.index('-ss')+1], '2.0')
        self.assertEqual(args[args.index('-t')+1], '1.0')

    def test_non_https_input_rejected_before_ffmpeg(self):
        with patch.object(remote_media, 'YoutubeDL') as downloader, \
             patch.object(remote_media.clip_render, 'command') as command:
            downloader.return_value.__enter__.return_value.extract_info.return_value = {'url': 'http://example.invalid/source.mp4'}
            with self.assertRaisesRegex(ValueError, 'HTTPS'):
                remote_media.receive('1', 0, 1000, self.path/'range.mp4', threading.Event(), None, lambda **v: None)
        command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
