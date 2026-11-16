import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from archive.media_readers import MediaReaders
from archive.storage import Conflict


class MediaReaderTests(unittest.TestCase):
    def test_only_target_streams_close_before_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vod = root / 'vod-1'
            vod.mkdir()
            target, other = vod / 'movie.mp4', root / 'other.mp4'
            target.write_bytes(b'a')
            other.write_bytes(b'b')
            readers, opened = MediaReaders(), threading.Event()
            sender, receiver = socket.socketpair()
            independent, peer = socket.socketpair()
            def stream():
                with readers.open(target, sender):
                    opened.set()
                    sender.recv(1)
            with sender, receiver, independent, peer, readers.open(other, independent) as unaffected:
                thread = threading.Thread(target=stream, daemon=True)
                thread.start()
                self.assertTrue(opened.wait(2))
                with readers.drain(vod):
                    thread.join(2)
                    self.assertFalse(thread.is_alive())
                    with self.assertRaises(Conflict), readers.open(target, sender):
                        pass
                    self.assertEqual(unaffected.read(), b'b')
                    independent.sendall(b'1')
                    self.assertEqual(peer.recv(1), b'1')
                with readers.open(target, independent) as again:
                    self.assertEqual(again.read(), b'a')

    def test_unclosed_handle_aborts_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'movie.mp4'
            target.touch()
            readers = MediaReaders()
            a, b = socket.socketpair()
            with a, b, readers.open(target, a), patch.object(readers.changed, 'wait_for', return_value=False):
                with self.assertRaises(Conflict), readers.drain(root):
                    self.fail('열린 파일이 있으면 이동할 수 없습니다')
            self.assertTrue(target.exists())
            self.assertFalse(readers.draining)
