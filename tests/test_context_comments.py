"""댓글 목록 저장과 이전 메모·원본 보호."""
import copy
from pathlib import Path
import tempfile
import unittest
from archive import context_comments as comments
from archive.storage import save_json, read_json, Conflict

class CommentListTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name);self.run='a'*32
        save_json(self.path/'context/state.json',{'runs':[{'id':self.run}],'run':self.run})
        self.original=self.path/f'context/runs/{self.run}/result.json';save_json(self.original,{'원본':'보존'})
        self.row={'id':'1','source_id':'1','start_ms':1000,'end_ms':2000,'title':'편집 제목'}
        self.value={'revision':0,'format':2,'rows':[self.row],'legacy_text':''}
    def test_roundtrip_conflict_reset_and_original(self):
        before=self.original.read_bytes();saved=comments.save(self.path,self.run,self.value)
        self.assertEqual(comments.read(self.path,self.run),saved)
        with self.assertRaises(Conflict):comments.save(self.path,self.run,self.value)
        empty=comments.save(self.path,self.run,saved|{'rows':[]});self.assertEqual(empty['rows'],[])
        self.assertEqual(self.original.read_bytes(),before)
    def test_legacy_backup_and_downgrade_blocked(self):
        old={'revision':0,'text':'00:00:01 직접 고친 제목\n자유 문장','selected':['1'],'edited':True,'basis':'원래 제목'}
        previous=comments.save(self.path,self.run,old);file=comments.target(self.path,self.run);original=file.read_bytes()
        new=comments.save(self.path,self.run,self.value|{'revision':1,'legacy_text':old['text']})
        backup=file.with_name(self.run+'.legacy.json');self.assertEqual(backup.read_bytes(),original)
        comments.save(self.path,self.run,new|{'rows':[]});self.assertEqual(backup.read_bytes(),original)
        with self.assertRaises(Conflict):comments.save(self.path,self.run,old|{'revision':3})
    def test_bad_rows_and_symlink_rejected(self):
        for patch in ({'start_ms':-1},{'end_ms':float('nan')},{'start_ms':True},{'end_ms':1000},{'title':'둘\n줄'},{'start_ms':None}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):comments.save(self.path,self.run,self.value|{'rows':[self.row|patch]})
        for rows in ([self.row,self.row], [self.row,self.row|{'id':'2'}]):
            with self.assertRaises(ValueError):comments.save(self.path,self.run,self.value|{'rows':rows})
        with self.assertRaises(ValueError):comments.save(self.path,'../다른결과',self.value)
        folder=self.path/'context/comments';folder.mkdir(exist_ok=True)
        backup=folder/(self.run+'.legacy.json');backup.symlink_to(self.original)
        old={'revision':0,'text':'원문','selected':[],'edited':True,'basis':''};comments.save(self.path,self.run,old)
        with self.assertRaises(ValueError):comments.save(self.path,self.run,self.value|{'revision':1})
    def test_unmatched_text_can_be_preserved(self):
        saved=comments.save(self.path,self.run,self.value|{'rows':[self.row|{'source_id':None,'start_ms':None,'end_ms':None,'title':'자유 문장'}]})
        self.assertIsNone(saved['rows'][0]['end_ms'])

if __name__=='__main__':unittest.main()
