"""기존 영상과 다른 자료가 이어 붙는 것을 막는 경계 검사."""

import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from archive import video
from archive.storage import Conflict, Project, ProjectLock, create_or_load, save_json
from test_archive import metadata


class VideoTests(unittest.TestCase):
    def test_changed_source_and_playlist_never_append(self):
        for protocol in ('https', 'm3u8_native'):
            with self.subTest(protocol=protocol), tempfile.TemporaryDirectory() as root:
                path = Path(root) / 'vod-1'
                with ProjectLock(path) as lock:
                    project = Project(path, create_or_load(path, metadata(), '360p'), lock)
                    media = path / 'media'
                    media.mkdir()
                    part = media / 'original.mp4.part'
                    part.write_bytes(b'original-part')
                    info = {'id': '1', 'format_id': '360p', 'ext': 'mp4', 'protocol': protocol,
                            'width': 640, 'height': 360, 'vcodec': 'h264', 'acodec': 'aac', 'url': 'https://example.invalid/video'}
                    identity = {k: info.get(k) for k in ('id', 'format_id', 'ext', 'protocol', 'width', 'height', 'vcodec', 'acodec')}
                    if protocol == 'https':
                        identity['filesize'] = 999
                    else:
                        identity['playlist'] = video.playlist('#EXTINF:2,\na\n#EXT-X-ENDLIST')
                    save_json(media / 'source.json', identity)
                    downloader = MagicMock()
                    downloader.extract_info.return_value = info
                    downloader.urlopen.return_value = io.BytesIO(b'#EXTINF:3,\na\n#EXT-X-ENDLIST')
                    with patch('archive.video.YoutubeDL') as factory:
                        factory.return_value.__enter__.return_value = downloader
                        with self.assertRaises(Conflict):
                            video.download(project, threading.Event())
                    downloader.process_info.assert_not_called()
                    self.assertEqual(part.read_bytes(), b'original-part')

    def test_disk_full_fails_before_network_and_keeps_partial(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'vod-1'
            with ProjectLock(path) as lock:
                project = Project(path, create_or_load(path, metadata(), '360p'), lock)
                (path / 'media').mkdir()
                partial = path / 'media/original.mp4.part'
                partial.write_bytes(b'keep')
                with patch('archive.video.shutil.disk_usage', return_value=MagicMock(free=0)), patch('archive.video.YoutubeDL') as downloader:
                    with self.assertRaises(OSError) as raised:
                        video.download(project, threading.Event())
                    self.assertEqual(raised.exception.errno, 28)
                    downloader.assert_not_called()
                self.assertEqual(partial.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
