"""실제 CDN 없이 HTTPS 바이트 분할 수신과 중단 자료 보존을 검사한다."""
import io
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from yt_dlp.utils.networking import HTTPHeaderDict

from archive import http_download
from archive.source import Cancelled


class Response(io.BytesIO):
    def __init__(self, body, headers, status, release):
        super().__init__(body)
        self.headers = HTTPHeaderDict(headers)
        self.status = self.code = status
        self.url = 'https://example.invalid/video.mp4'
        self.release = release

    def getcode(self):
        return self.status

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def close(self):
        if not self.closed:
            self.release()
        super().close()


class Server:
    def __init__(self, payload, *, parallel=0):
        self.payload = payload
        self.etag = '"source-one"'
        self.requests = []
        self.guard = threading.Lock()
        self.gate = threading.Event()
        self.parallel = parallel
        self.active = self.peak = 0
        self.supported = True
        self.invalid_chunks = False
        self.short_once = False
        self.short_reads = 0
        self.stop = None
        self.stop_offset = None
        self.params = {'retries': 3, 'socket_timeout': 1}

    def urlopen(self, request):
        headers = HTTPHeaderDict(request.headers)
        match = re.fullmatch(r'bytes=(\d+)-(\d+)', headers.get('Range', ''))
        if not match:
            raise AssertionError('바이트 범위를 명시한 요청이 필요합니다')
        start, end = map(int, match.groups())
        probe = start == end == 0
        with self.guard:
            self.requests.append((start, end, dict(headers)))
            self.active += 1
            self.peak = max(self.peak, self.active)
            if not probe and self.active >= self.parallel:
                self.gate.set()
            short = self.short_once and not probe and self.short_reads == 0
            if short:
                self.short_reads += 1
        if not probe and self.parallel:
            self.gate.wait(2)
        if self.stop is not None and not probe and start >= self.stop_offset:
            self.stop.set()
        body = self.payload[start:end+1] if self.supported else self.payload
        response_headers = {'ETag': self.etag, 'Content-Length': str(len(body)),
                            'Accept-Ranges': 'bytes', 'Content-Encoding': 'identity'}
        if self.supported:
            reported_start = start + 1 if self.invalid_chunks and not probe else start
            response_headers['Content-Range'] = f'bytes {reported_start}-{end}/{len(self.payload)}'
        if short:
            body = body[:len(body)//2]

        def release():
            with self.guard:
                self.active -= 1

        return Response(body, response_headers, 206 if self.supported else 200, release)


class HttpDownloadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.original = self.folder/'original.mp4'
        self.state = self.folder/'original.mp4.part-range.json'
        self.data = self.folder/'original.mp4.part-range.data'
        self.payload = bytes(range(256))*16
        self.info = {'url': 'https://example.invalid/video.mp4?token=test-secret',
                     'http_headers': {'Referer': 'https://chzzk.naver.com/'},
                     'filesize': len(self.payload), 'protocol': 'https', 'ext': 'mp4'}
        self.progress = []
        self.chunk = patch.object(http_download, 'CHUNK_SIZE', 128)
        self.chunk.start()
        self.addCleanup(self.chunk.stop)

    def receive(self, server, stop=None, concurrency=4):
        return http_download.download(server, self.info, self.original,
                                      stop or threading.Event(), self.progress.append, concurrency)

    def interrupted(self, etag='"source-one"'):
        server = Server(self.payload)
        server.etag = etag
        stop = threading.Event()
        server.stop, server.stop_offset = stop, 256
        with self.assertRaises(Cancelled):
            self.receive(server, stop, concurrency=2)
        self.assertFalse(self.original.exists())
        self.assertTrue(self.state.is_file())
        self.assertTrue(self.data.is_file())
        self.assertEqual(server.active, 0)
        return server

    def test_exact_ranges_parallel_sixteen_and_cleanup(self):
        server = Server(self.payload, parallel=16)
        self.assertTrue(self.receive(server, concurrency=16))
        self.assertEqual(self.original.read_bytes(), self.payload)
        self.assertEqual(server.peak, 16)
        self.assertEqual(server.active, 0)
        ranges = sorted((a, b) for a, b, _ in server.requests if (a, b) != (0, 0))
        self.assertEqual(ranges, [(a, a+127) for a in range(0, len(self.payload), 128)])
        self.assertTrue(all(HTTPHeaderDict(headers).get('Accept-Encoding') == 'identity'
                            for _, _, headers in server.requests))
        self.assertFalse(self.state.exists())
        self.assertFalse(self.data.exists())
        self.assertTrue(self.progress)
        self.assertEqual(self.progress[-1]['downloaded_bytes'], len(self.payload))

    def test_unsupported_range_returns_single_download_fallback(self):
        server = Server(self.payload)
        server.supported = False
        self.assertFalse(self.receive(server))
        self.assertEqual(len(server.requests), 1)
        self.assertEqual(server.active, 0)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_weak_or_missing_etag_does_not_start_parallel_download(self):
        for etag in ('W/"source-one"', ''):
            with self.subTest(etag=etag):
                server = Server(self.payload)
                server.etag = etag
                self.assertFalse(self.receive(server))
                self.assertEqual(len(server.requests), 1)
                self.assertEqual(server.active, 0)
                self.assertEqual(list(self.folder.iterdir()), [])

    def test_unquoted_etag_parallel_download_resumes_with_identical_if_range(self):
        etag = 'test-resource-v1-0123456789abcdef'
        interrupted = self.interrupted(etag)
        self.assertNotIn(etag, self.state.read_text(encoding='utf-8'))
        server = Server(self.payload, parallel=4)
        server.etag = etag
        self.assertTrue(self.receive(server, concurrency=4))
        self.assertEqual(server.peak, 4)
        self.assertEqual(server.active, 0)
        self.assertEqual(self.original.read_bytes(), self.payload)
        ranges = [(a, b) for a, b, _ in server.requests if (a, b) != (0, 0)]
        self.assertLess(len(ranges), len(self.payload)//128)
        for start, end, headers in interrupted.requests + server.requests:
            if (start, end) != (0, 0):
                self.assertEqual(HTTPHeaderDict(headers).get('If-Range'), etag)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.data.exists())

    def test_whitespace_etag_falls_back_without_creating_partial_files(self):
        for etag in ('has space', 'has\t tab', 'has\nnewline', 'has\r\nline'):
            with self.subTest(etag=etag):
                server = Server(self.payload)
                server.etag = etag
                self.assertFalse(self.receive(server))
                self.assertEqual(len(server.requests), 1)
                self.assertEqual(server.active, 0)
                self.assertEqual(list(self.folder.iterdir()), [])

    def test_short_final_chunk_has_no_extra_byte(self):
        server = Server(self.payload+b'end')
        self.info['filesize'] = len(server.payload)
        self.assertTrue(self.receive(server))
        self.assertEqual(self.original.read_bytes(), self.payload+b'end')
        self.assertIn((4096, 4098), [(a, b) for a, b, _ in server.requests])

    def test_wrong_chunk_content_range_never_publishes_original(self):
        server = Server(self.payload)
        server.invalid_chunks = True
        self.assertFalse(self.receive(server))
        self.assertFalse(self.original.exists())
        self.assertTrue(self.state.is_file())
        self.assertTrue(self.data.is_file())
        self.assertEqual(server.active, 0)

    def test_remote_identity_change_preserves_interrupted_files(self):
        self.interrupted()
        before = {path: path.read_bytes() for path in (self.state, self.data)}
        server = Server(self.payload)
        server.etag = '"source-two"'
        with self.assertRaises((ValueError, OSError)):
            self.receive(server)
        self.assertFalse(self.original.exists())
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertTrue(all((a, b) == (0, 0) for a, b, _ in server.requests))
        self.assertEqual(server.active, 0)

    def test_changed_remote_size_preserves_interrupted_files(self):
        self.interrupted()
        before = {path: path.read_bytes() for path in (self.state, self.data)}
        server = Server(self.payload+b'changed')
        with self.assertRaises((ValueError, OSError)):
            self.receive(server)
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertFalse(self.original.exists())
        self.assertEqual(server.active, 0)

    def test_interrupt_then_single_worker_resume_skips_completed_chunks(self):
        self.interrupted()
        self.assertNotIn('test-secret', self.state.read_text(encoding='utf-8'))
        server = Server(self.payload)
        self.assertTrue(self.receive(server, concurrency=1))
        ranges = [(a, b) for a, b, _ in server.requests if (a, b) != (0, 0)]
        self.assertLess(len(ranges), len(self.payload)//128)
        self.assertLessEqual(server.peak, 1)
        self.assertEqual(server.active, 0)
        self.assertEqual(self.original.read_bytes(), self.payload)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.data.exists())

    def test_existing_single_download_partial_is_preserved(self):
        partial = self.folder/'original.mp4.part'
        metadata = self.folder/'original.mp4.ytdl'
        partial.write_bytes('기존 수신 파일'.encode('utf-8'))
        metadata.write_bytes(b'{"fragment_index":3}')
        before = {path: path.read_bytes() for path in (partial, metadata)}
        server = Server(self.payload)
        self.assertFalse(self.receive(server, concurrency=16))
        self.assertEqual(server.requests, [])
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertFalse(self.original.exists())
        self.assertFalse(self.state.exists())

    def test_corrupted_completed_chunk_is_downloaded_again(self):
        self.interrupted()
        saved = json.loads(self.state.read_text(encoding='utf-8'))
        index = int(next(iter(saved['done'])))
        with self.data.open('r+b') as file:
            file.seek(index*128)
            file.write(b'changed')
        server = Server(self.payload)
        self.assertTrue(self.receive(server))
        self.assertIn((index*128, index*128+127), [(a, b) for a, b, _ in server.requests])
        self.assertEqual(self.original.read_bytes(), self.payload)

    def test_new_single_worker_stays_on_existing_downloader(self):
        server = Server(self.payload)
        self.assertFalse(self.receive(server, concurrency=1))
        self.assertEqual(server.requests, [])
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_invalid_parallel_limit_is_rejected_before_network(self):
        server = Server(self.payload)
        for concurrency in (0, 33, True, '4'):
            with self.subTest(concurrency=concurrency), self.assertRaises(ValueError):
                self.receive(server, concurrency=concurrency)
        self.assertEqual(server.requests, [])
        self.assertEqual(list(self.folder.iterdir()), [])

    @unittest.skipUnless(os.name == 'posix', 'POSIX 물리 할당량 검사')
    def test_allocated_space_matches_real_posix_file_blocks(self):
        with self.data.open('wb') as file:
            file.truncate(8*1024*1024)
            file.seek(4*1024*1024)
            file.write(self.payload)
            file.flush()
            os.fsync(file.fileno())
        stat = self.data.stat()
        self.assertEqual(http_download._allocated(self.data, 123), stat.st_blocks*512)
        self.assertGreater(stat.st_blocks, 0)
        self.assertEqual(http_download._allocated(self.folder/'missing', 123), 0)

    def test_preallocated_resume_needs_only_reserved_free_space(self):
        self.interrupted()
        server = Server(self.payload)
        with patch.object(http_download, '_allocated', return_value=len(self.payload)) as allocated, \
             patch.object(http_download.shutil, 'disk_usage', return_value=SimpleNamespace(free=256*1024*1024)):
            self.assertTrue(self.receive(server))
        allocated.assert_called_once()
        self.assertEqual(allocated.call_args.args[0], self.data)
        self.assertLess(allocated.call_args.args[1], len(self.payload))
        self.assertEqual(self.original.read_bytes(), self.payload)
        self.assertEqual(server.active, 0)

    def test_short_read_is_retried_without_holes(self):
        server = Server(self.payload)
        server.short_once = True
        self.assertTrue(self.receive(server))
        self.assertEqual(server.short_reads, 1)
        self.assertEqual(server.active, 0)
        self.assertEqual(self.original.read_bytes(), self.payload)
        requested = sum(b-a+1 for a, b, _ in server.requests if (a, b) != (0, 0))
        self.assertGreater(requested, len(self.payload))


if __name__ == '__main__':
    unittest.main()
