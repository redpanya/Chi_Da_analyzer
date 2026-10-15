"""첨부 원본 보존, 해시 기반 복구, VOD·로컬 시각 경계 검사."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from archive.local_import import Upload,options
from archive.storage import Project,ProjectLock,create_or_load,save_json,read_json,Conflict
from archive import analysis_store
from test_archive import metadata

class LocalImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.path=self.root/'vod-1'
        self.info={'name':'내 영상.mp4','size':6,'start_vod_ms':1000,'confirmed':True};self.job=None
    def tearDown(self):
        if self.job and not self.job.closed:self.job.cancel()
        self.temp.cleanup()
    def open(self):
        lock=ProjectLock(self.path);d=create_or_load(self.path,metadata(),None,self.info)
        self.job=Upload(Project(self.path,d,lock));return self.job
    def test_resume_rechecks_every_original_chunk_and_rejects_other_file(self):
        with patch('archive.local_import.CHUNK',3):
            job=self.open();sha=hashlib.sha256(b'abc').hexdigest();job.chunk(0,sha,b'abc');job.cancel()
            job=self.open();self.assertEqual(job.bytes,3)
            with self.assertRaises(ValueError):job.chunk(0,hashlib.sha256(b'xyz').hexdigest())
            self.assertEqual(job.part.read_bytes(),b'abc');job.chunk(0,sha)
            with self.assertRaises(ValueError):job.chunk(1,'f'*64,b'def')
            job.chunk(1,hashlib.sha256(b'def').hexdigest(),b'def');self.assertEqual(job.part.read_bytes(),b'abcdef')
    def test_short_part_never_grows_with_zero_padding(self):
        with patch('archive.local_import.CHUNK',3):
            job=self.open();job.chunk(0,hashlib.sha256(b'abc').hexdigest(),b'abc');job.cancel();job.part.write_bytes(b'a')
            with ProjectLock(self.path) as lock:
                with self.assertRaisesRegex(ValueError,'짧습니다'):Upload(Project(self.path,read_json(self.path/'project.json'),lock))
            self.assertEqual(job.part.read_bytes(),b'a')
    def test_existing_completed_video_cannot_be_replaced(self):
        job=self.open();job.project.update('video',state='complete');job.cancel()
        d=read_json(self.path/'project.json');d['tasks']['video']['state']='complete';save_json(self.path/'project.json',d)
        with ProjectLock(self.path):
            with self.assertRaises(Conflict):create_or_load(self.path,metadata(),None,self.info)
    def test_vod_chat_is_kept_but_local_view_discards_outside_range(self):
        job=self.open();job.cancel();d=read_json(self.path/'project.json')
        d['tasks']['video']['verification']={'duration':1};d['tasks']['chat'].update(state='complete',assets={'jsonl':'exports/chat.jsonl'})
        f=self.path/'exports/chat.jsonl';f.parent.mkdir();rows=[{'vod_id':'1','offset_ms':t,'text':'ㅋㅋ'} for t in (999,1000,1999,2000)]
        import json
        f.write_text(''.join(json.dumps(r)+'\n' for r in rows));before=f.read_bytes();count=[0]
        result=list(analysis_store.rows(self.path,d,counter=count))
        self.assertEqual([r['offset_ms'] for r in result],[0,999]);self.assertEqual([r['vod_offset_ms'] for r in result],[1000,1999]);self.assertEqual(count,[4]);self.assertEqual(before,f.read_bytes())
    def test_invalid_mapping_and_type_are_rejected(self):
        for update in ({'start_vod_ms':-1},{'confirmed':False},{'size':True},{'name':'x.txt'}):
            with self.assertRaises(ValueError):options(self.info|update)
    def test_confirmed_filename_before_state_commit_is_recoverable(self):
        with patch('archive.local_import.CHUNK',6):
            job=self.open();raw=b'abcdef';sha=hashlib.sha256(raw).hexdigest();job.chunk(0,sha,raw);job.cancel()
            job.part.replace(job.folder/'imported.mp4');job=self.open()
            self.assertEqual(job.part.name,'imported.mp4');job.chunk(0,sha);self.assertEqual(job.part.read_bytes(),raw)
