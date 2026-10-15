"""작은 모형 파일로 모델 이어받기·취소·손상·응답 범위를 검증한다."""
import hashlib
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from archive import context_model as model
from archive.source import Cancelled

class Response(io.BytesIO):
    def __init__(self,data,status=206,range='bytes 3-5/6'):
        super().__init__(data);self.status=status;self.headers={'Content-Range':range}

class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name);self.stop=threading.Event()
        self.patches=[patch.object(model,'DEFAULT_NAME',model.NAME),patch.object(model,'home',return_value=self.home),patch.object(model,'SIZE',6),patch.object(model,'SHA256',hashlib.sha256(b'abcdef').hexdigest())]
        for p in self.patches:p.start()
        self.part=self.home/(model.NAME+'.part')
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_resume_and_cached_hash_validation(self):
        self.part.write_bytes(b'abc')
        with patch.object(model,'urlopen',return_value=Response(b'def')) as open:
            model.prepare(self.stop,lambda **kw:None);self.assertEqual(open.call_args.args[0].get_header('Range'),'bytes=3-')
        self.assertEqual(model.model_path().read_bytes(),b'abcdef');self.assertTrue(model.status()['ready'])
        with patch.object(model,'urlopen',side_effect=AssertionError('네트워크 재요청')):model.prepare(self.stop,lambda **kw:None)
    def test_restart_on_full_response_and_invalid_range(self):
        self.part.write_bytes(b'abc')
        with patch.object(model,'urlopen',return_value=Response(b'def',range='bytes 0-2/6')):
            with self.assertRaises(ValueError):model.prepare(self.stop,lambda **kw:None)
        self.assertEqual(self.part.read_bytes(),b'abc')
        with patch.object(model,'urlopen',return_value=Response(b'abcdef',status=200)):model.prepare(self.stop,lambda **kw:None)
        self.assertEqual(model.model_path().read_bytes(),b'abcdef')
    def test_cancel_preserves_partial_and_bad_hash_is_quarantined(self):
        with patch.object(model,'urlopen',return_value=Response(b'abc',status=200)):
            with self.assertRaises(Cancelled):model.prepare(self.stop,lambda **kw:self.stop.set())
        self.assertEqual(self.part.read_bytes(),b'abc');self.stop.clear()
        with patch.object(model,'urlopen',return_value=Response(b'xyz')):
            with self.assertRaises(ValueError):model.prepare(self.stop,lambda **kw:None)
        self.assertFalse(model.model_path().exists());self.assertFalse(self.part.exists());self.assertTrue(list(self.home.glob('*.invalid-*')))
