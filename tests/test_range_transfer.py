"""합성 영상에서 실제 FFmpeg와 기록 가능한 전송기로 구간 수신을 검증한다."""
from collections import Counter
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from yt_dlp.networking.exceptions import TransportError
from archive import remote_media
from archive.source import Cancelled
from archive.storage import ProjectLock

FIX = Path(__file__).parent/'fixtures'


class Response(BytesIO):
    def __init__(self, url, data, status, headers, close_hook):
        super().__init__(data)
        self.url, self.status, self.headers, self.hook = url,status,headers,close_hook

    def close(self):
        if not self.closed:
            self.hook()
        super().close()


class Transport:
    def __init__(self, files):
        self.files = files
        self.requests = Counter()
        self.failures = {}
        self.failed_key = None
        self.revalidated = []
        self.fail_first_piece = 0
        self.active = self.peak = 0
        self.guard = threading.Lock()
        self.on_request = None

    def urlopen(self, req):
        name = urlsplit(req.url).path.rsplit('/',1)[-1]
        data = self.files[name]
        headers = {'ETag':'"fixture-v1"'}
        status = 200
        bounds = None
        if val := req.headers.get('Range'):
            a,b = map(int,val[6:].split('-'))
            bounds = (a,b+1)
            headers['Content-Range'] = f'bytes {a}-{b}/{len(data)}'
            data = data[a:b+1]
            status = 206
        if req.headers.get('If-None-Match') == headers['ETag']:
            self.revalidated.append(name)
            status,data = 304,b''
        key = (name,bounds)
        with self.guard:
            self.requests[key] += 1
            if self.fail_first_piece and len(data) >= 64000 and self.failed_key is None:
                self.failed_key = key
                self.failures[key] = self.fail_first_piece
            if self.failures.get(key,0):
                self.failures[key] -= 1
                raise TransportError('측정용 전송 중단')
            self.active += 1
            self.peak = max(self.active,self.peak)
        if self.on_request:
            self.on_request(key)
        time.sleep(.006)
        def closed():
            with self.guard:
                self.active -= 1
        headers['Content-Length'] = str(len(data))
        return Response(req.url,data,status,headers,closed)

    def __enter__(self):
        return self
    def __exit__(self,*args):
        pass


def command(*args):
    return subprocess.check_output([str(arg) for arg in args],stderr=subprocess.PIPE)


def frames(file, *bounds):
    rows = command('ffmpeg','-v','error',*bounds[:2],'-i',file,*bounds[2:],'-map','0:v','-f','framemd5','-').decode().splitlines()
    return [r.rsplit(',',1)[-1].strip() for r in rows if not r.startswith('#')]


class RangeTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.original = Path(cls.temp.name)/'source.mp4'
        command('ffmpeg','-loglevel','error','-f','lavfi','-i','testsrc2=s=320x180:r=24:d=24',
                '-f','lavfi','-i','sine=frequency=800:sample_rate=48000:duration=24',
                '-c:v','libx264','-threads:v','2','-preset','ultrafast','-crf','16','-g','24',
                '-bf','0','-c:a','aac','-movflags','+faststart',cls.original)
        cls.video = cls.original.read_bytes()

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name)
        self.stop = threading.Event()
        self.progress = []
        self.net = Transport({'v.mp4':self.video})

    def fetch(self,start,end,count,protocol='https',name='v.mp4'):
        self.out = self.path/'out.mp4'
        info = {'url':'https://example.invalid/'+name,'protocol':protocol,'format_id':'test'}
        with ProjectLock(self.path) as lock, patch.object(remote_media,'YoutubeDL',return_value=self.net), \
             patch.object(remote_media,'extract_vod',return_value=info):
            return remote_media.receive('1',start,end,self.out,self.stop,lock,lambda **v:self.progress.append(v),concurrent_fragments=count)

    def test_parallel_partial_copy_and_one_piece_retry(self):
        self.net.fail_first_piece = 1
        proof = self.fetch(8000,16000,4)
        self.assertTrue(proof['stream_copy'])
        self.assertEqual(frames(self.out), frames(self.original,'-ss','8','-t','8'))
        self.assertGreater(self.net.peak,1)
        self.assertLessEqual(self.net.peak,4)
        self.assertEqual([k for k,v in self.net.requests.items() if v>1],[self.net.failed_key])
        self.assertEqual(self.net.requests[self.net.failed_key],2)
        transferred = sum(z-a for name,(a,z) in self.net.requests)
        self.assertLess(transferred,len(self.video)*.55)
        self.assertTrue(any(v.get('speed',0)>0 for v in self.progress if v.get('phase')=='receive'))
        self.assertFalse(any('speed' in v for v in self.progress if v.get('phase')!='receive'))
        self.assertEqual(self.original.read_bytes(),self.video)
        self.assertFalse(list(self.path.glob('range-cache-*')))

    def test_copy_b_frames_preserves_images_when_only_audio_boundary_needs_encoding(self):
        file = FIX/'https-media.mp4'
        self.net = Transport({'v.mp4':file.read_bytes()})
        proof = self.fetch(1000,3000,1)
        self.assertTrue(proof['video_stream_copy'])
        self.assertFalse(proof['stream_copy'])
        self.assertEqual(frames(self.out),frames(file,'-ss','1','-t','2'))

    def test_resume_reuses_completed_bytes_and_only_retries_bad_piece(self):
        self.net.fail_first_piece = 3
        with self.assertRaisesRegex(ValueError,'세 번'):
            self.fetch(8000,16000,4)
        self.assertTrue(list(self.path.glob('range-cache-*/*.sha256')))
        self.assertFalse(self.out.exists())
        before = self.net.requests.copy()
        self.fetch(8000,16000,4)
        self.assertEqual(self.net.requests[self.net.failed_key],4)
        for key,count in before.items():
            if key!=self.net.failed_key and key[1][1]-key[1][0] >= 64000:
                self.assertEqual(self.net.requests[key],count)

    def test_non_keyframe_encodes_local_material_and_preserves_timing(self):
        proof = self.fetch(8250,16250,16)
        self.assertFalse(proof['video_stream_copy'])
        self.assertAlmostEqual(proof['duration'],8,delta=.025)
        info = remote_media.clip_render.probe(self.out)
        for track in info['streams']:
            self.assertAlmostEqual(float(track['duration']),8,delta=.025)
        self.assertEqual(len(frames(self.out)),192)
        self.assertGreater(self.net.peak,1)
        self.assertLessEqual(self.net.peak,16)

    def test_cancel_does_not_retry_or_create_output(self):
        self.net.on_request = lambda k:self.stop.set() if k[1][1]-k[1][0]>=64000 else None
        with self.assertRaises(Cancelled):
            self.fetch(8000,16000,4)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.net.active,0)
        self.assertEqual(max(self.net.requests.values()),1)

    def test_hls_resume_revalidates_complete_parts_without_receiving_payload_again(self):
        files = {f.name:f.read_bytes() for f in FIX.glob('https-fmp4-*')}
        self.net = Transport(files)
        self.net.failures[('https-fmp4-01.m4s',None)] = 3
        with self.assertRaisesRegex(ValueError,'세 번'):
            self.fetch(0,4000,4,'m3u8_native','https-fmp4-m4s.m3u8')
        self.fetch(0,4000,4,'m3u8_native','https-fmp4-m4s.m3u8')
        self.assertEqual(set(self.net.revalidated),{'https-fmp4-init.mp4','https-fmp4-00.m4s'})
        self.assertFalse(list(self.path.glob('range-cache-*')))

    def test_existing_output_is_preserved(self):
        existing = self.path/'out.mp4'
        existing.write_bytes(b'original')
        with self.assertRaisesRegex(ValueError,'덮어쓸'):
            self.fetch(8000,16000,4)
        self.assertEqual(existing.read_bytes(),b'original')
        self.assertFalse(self.net.requests)

    def test_hls_only_selected_segment_and_init(self):
        files = {f.name:f.read_bytes() for f in FIX.glob('https-fmp4-*')}
        self.net = Transport(files)
        self.fetch(2000,4000,4,'m3u8_native','https-fmp4-m4s.m3u8')
        self.assertEqual({k[0] for k in self.net.requests},{'https-fmp4-m4s.m3u8','https-fmp4-01.m4s','https-fmp4-init.mp4'})
        self.assertEqual(self.net.peak,2)
        self.assertAlmostEqual(float(remote_media.clip_render.probe(self.out)['format']['duration']),2,delta=.06)
