"""전체 영상 수신기의 병렬 선택과 단일 fallback을 검사한다. 실제 디코딩은 실행하지 않는다."""
from contextlib import ExitStack
import hashlib
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from archive import automation_media, video
from archive.source import Cancelled
from archive.storage import Project, ProjectLock, create_or_load, read_json
from test_archive import metadata


class VideoHttpDownloadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)/'vod-1'
        lock = ProjectLock(self.path)
        self.addCleanup(lock.close)
        meta = metadata()
        meta['formats'][0]['protocol'] = 'https'
        self.project = Project(self.path, create_or_load(self.path, meta, '360p'), lock)
        self.project.update('video', concurrent_fragments=16)
        self.original = self.path/'media/original.mp4'
        self.payload = b'mp4-fixture-data'
        self.stop = threading.Event()
        self.info = {'id': '1', 'format_id': '360p', 'ext': 'mp4', 'protocol': 'https',
                     'url': 'https://example.invalid/video.mp4', 'duration': 3,
                     'filesize': len(self.payload), 'width': 640, 'height': 360,
                     'vcodec': 'h264', 'acodec': 'aac'}
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(video.shutil, 'which', return_value='test-media-tool'))
        stack.enter_context(patch.object(video.shutil, 'disk_usage', return_value=MagicMock(free=10**12)))
        self.remote_metadata = stack.enter_context(patch.object(video, 'metadata', return_value=meta))
        self.factory = stack.enter_context(patch.object(video, 'YoutubeDL'))
        self.downloader = self.factory.return_value.__enter__.return_value
        self.downloader.extract_info.return_value = self.info
        self.parallel = stack.enter_context(patch.object(video.http_download, 'download'))
        self.probe = stack.enter_context(patch.object(video, 'probe', side_effect=RuntimeError('수신 후 검사 진입')))

    def verify_transfer(self):
        with self.assertRaisesRegex(RuntimeError, '수신 후 검사 진입'):
            video.download(self.project, self.stop)
        self.probe.assert_called_once_with(self.original)
        self.assertEqual(self.original.read_bytes(), self.payload)
        self.assertEqual(self.project.snapshot()['tasks']['video']['state'], 'verifying')

    def prepare_long_video(self):
        self.remote_metadata.return_value = self.info | {'duration': 600}
        self.info.update(duration=600, filesize=None)
        self.probe.side_effect = None
        self.probe.return_value = {'format': {'format_name': 'mp4', 'duration': '600'},
                                   'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'pix_fmt': 'yuv420p'}]}
        def receive(downloader, info, original, stop, progress, concurrency):
            original.write_bytes(self.payload)
            progress({'status': 'downloading', 'total_bytes': len(self.payload)})
            return True
        self.parallel.side_effect = receive

    def test_sampled_download_reused_by_automation(self):
        self.prepare_long_video()
        with patch.object(video, 'run_media') as run:
            video.download(self.project, self.stop)
        args = [call.args[0] for call in run.call_args_list]
        self.assertEqual([float(a[a.index('-ss') + 1]) for a in args], [0, 298.5, 597])
        proof = self.project.data['tasks']['video']['verification']
        self.assertEqual(proof['decode_mode'], 'sampled')
        self.assertNotIn('decode_exit_code', proof)
        self.assertEqual(proof['original_sha256'], hashlib.sha256(self.payload).hexdigest())
        self.assertTrue(automation_media.video_ready(self.project, self.stop))
        self.original.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '원본 영상이 다릅니다'):
            automation_media.video_ready(self.project, self.stop)

    def test_sample_error_falls_back_and_failed_full_check_preserves_original(self):
        self.prepare_long_video()
        with patch.object(video, 'run_media', side_effect=[None, ValueError('표본 오류'), ValueError('전체 오류')]) as run:
            with self.assertRaisesRegex(ValueError, '전체 오류'):
                video.download(self.project, self.stop)
        self.assertNotIn('-t', run.call_args.args[0])
        self.assertEqual(self.original.read_bytes(), self.payload)
        self.assertNotEqual(self.project.data['tasks']['video']['state'], 'complete')

    def test_cancelled_sample_does_not_launch_full_decode(self):
        self.prepare_long_video()
        with patch.object(video, 'run_media', side_effect=Cancelled) as run, self.assertRaises(Cancelled):
            video.download(self.project, self.stop)
        self.assertEqual(run.call_count, 1)
        self.assertNotEqual(self.project.data['tasks']['video']['state'], 'complete')

    def test_finished_bytes_alone_do_not_enable_sampling(self):
        self.prepare_long_video()
        self.parallel.side_effect = None
        self.parallel.return_value = False
        def receive(info):
            self.original.write_bytes(self.payload)
            hook = self.factory.call_args.args[0]['progress_hooks'][0]
            hook({'status': 'finished', 'total_bytes': len(self.payload)})
        self.downloader.process_info.side_effect = receive
        with patch.object(video, 'run_media') as run:
            video.download(self.project, self.stop)
        self.assertEqual(run.call_count, 1)
        self.assertNotIn('-ss', run.call_args.args[0])
        self.assertEqual(self.project.data['tasks']['video']['verification']['decode_exit_code'], 0)

    def test_long_replacement_uses_full_decode_proof(self):
        self.prepare_long_video()
        self.project.data['video_replacement'] = {'policy': 'keep'}
        with patch.object(video, 'run_media') as run:
            video.download(self.project, self.stop)
        self.assertEqual(run.call_count, 1)
        self.assertNotIn('-ss', run.call_args.args[0])
        self.assertEqual(self.project.data['tasks']['video']['verification']['decode_mode'], 'full')

    def test_duration_disagreement_uses_full_decode_proof(self):
        self.prepare_long_video()
        self.probe.return_value['format']['duration'] = '590'
        with patch.object(video, 'run_media') as run:
            video.download(self.project, self.stop)
        self.assertEqual(run.call_count, 1)
        self.assertNotIn('-ss', run.call_args.args[0])
        self.assertEqual(self.project.data['tasks']['video']['verification']['decode_exit_code'], 0)

    def test_wrong_content_length_never_completes(self):
        self.prepare_long_video()
        self.info['filesize'] = len(self.payload) + 1
        with self.assertRaisesRegex(ValueError, '크기'):
            video.download(self.project, self.stop)
        self.probe.assert_not_called()
        self.assertEqual(self.original.read_bytes(), self.payload)

    def test_parallel_completion_skips_yt_dlp_transfer(self):
        def receive(downloader, info, original, stop, progress, concurrency):
            self.assertIs(downloader, self.downloader)
            self.assertEqual(info, self.info)
            self.assertEqual(original, self.original)
            self.assertIs(stop, self.stop)
            self.assertTrue(callable(progress))
            self.assertEqual(concurrency, 16)
            original.write_bytes(self.payload)
            return True

        self.parallel.side_effect = receive
        self.verify_transfer()
        self.parallel.assert_called_once()
        self.downloader.process_info.assert_not_called()
        self.assertEqual(read_json(self.original.parent/'source.json')['filesize'], len(self.payload))

    def test_unsupported_parallel_uses_single_transfer(self):
        self.parallel.return_value = False
        self.downloader.process_info.side_effect = lambda info: self.original.write_bytes(self.payload)
        self.verify_transfer()
        self.parallel.assert_called_once()
        self.downloader.process_info.assert_called_once_with(self.info)

    def test_cancelled_probe_never_starts_single_fallback(self):
        def unsupported(*args):
            self.stop.set()
            return False

        self.parallel.side_effect = unsupported
        with self.assertRaises(Cancelled):
            video.download(self.project, self.stop)
        self.parallel.assert_called_once()
        self.downloader.process_info.assert_not_called()
        self.probe.assert_not_called()
        self.assertFalse(self.original.exists())

    def test_hls_keeps_existing_fragment_downloader(self):
        self.info['protocol'] = 'm3u8_native'
        self.project.data['metadata']['formats'][0]['protocol'] = 'm3u8_native'
        playlist = b'#EXTM3U\n#EXTINF:3,\nsegment.ts\n#EXT-X-ENDLIST\n'
        self.downloader.urlopen.side_effect = lambda url: io.BytesIO(playlist)
        self.downloader.process_info.side_effect = lambda info: self.original.write_bytes(self.payload)
        self.verify_transfer()
        self.parallel.assert_not_called()
        self.downloader.process_info.assert_called_once_with(self.info)
        self.assertEqual(self.downloader.urlopen.call_count, 2)
        self.assertEqual(self.factory.call_args.args[0]['concurrent_fragment_downloads'], 16)
        self.assertEqual(read_json(self.original.parent/'source.json')['playlist'], video.playlist(playlist.decode()))


if __name__ == '__main__':
    unittest.main()
