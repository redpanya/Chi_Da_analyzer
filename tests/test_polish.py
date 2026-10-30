"""폴리싱의 데이터 보존·공간·이력 경계 계약."""
import json, tempfile, threading, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from archive import clip_contract, studio_space, studio_maintenance as clean, split_draft
from archive.automation import completion_message
from archive.split_jobs import Splitter
from archive.storage import Conflict,save_json,read_json

class Polish(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.path=self.root/'vod-1';self.path.mkdir();self.source=self.path/'source.mp4';self.source.write_bytes(b'original')
        save_json(self.path/'project.json',{'tasks':{'video':{'assets':{'original':'source.mp4'}}}})
        self.src={'file':self.source,'origin':0,'duration':20000,'width':320,'height':180}
    def job(self,state='complete'):
        folder=self.path/'studio/runs'/('a'*32);folder.mkdir(parents=True)
        (folder/'clip-001.mp4').write_bytes(b'output');(folder/'clip-001-part.mp4').write_bytes(b'part')
        file=folder/'manifest.json';save_json(file,dict(id=folder.name,kind='start',state=state,outputs={'clip-001':{'assets':{'video':'clip-001.mp4'},'verification':{'bytes':6},'file_identity':clean.identity(folder/'clip-001.mp4')}}))
        return file
    def test_draft_keeps_empty_selection_and_raw_range(self):
        value={'clips':[],'range_drafts':{'a':{'title':'새 제목','start':'작성 중','end':'00:00:03'}},'caption_versions':{'A':{'1':'교정'},'B':{'1':'별개'}}}
        self.assertEqual(clip_contract.validate(value,self.src,draft=True)['range_drafts'],value['range_drafts'])
        with self.assertRaises(ValueError):clip_contract.validate(value,self.src)
        value['clips']=[{'title':'한 구간','start_ms':0,'end_ms':1000}];value['options']={'caption':True,'speed':'fast'}
        clip_contract.validate(value,self.src,draft=True)
        with self.assertRaises(ValueError):clip_contract.validate(value,self.src)
    def test_split_draft_conflict_and_original(self):
        folder=self.root/'draft';folder.mkdir();sources={'b'*32:{'path':str(self.source),'duration':20}}
        with patch('archive.split_contract.unchanged'):
            draft={'source_id':'b'*32,'points':[],'folder':str(self.root),'point_drafts':{'2':'아직 입력'},'pending_point':'00:'}
            value=split_draft.save(folder,{'revision':0,'draft':draft},sources)
            before=(folder/'draft.json').read_bytes()
            with self.assertRaises(Conflict):split_draft.save(folder,{'revision':0,'draft':draft},sources)
            self.assertEqual(before,(folder/'draft.json').read_bytes());self.assertEqual(value['draft']['pending_point'],'00:')
        self.assertEqual(self.source.read_bytes(),b'original')
    def test_space_minimum_and_low_disk(self):
        request=clip_contract.validate({'clips':[{'title':'a','start_ms':0,'end_ms':10000}]},self.src)
        small=studio_space.estimate(self.src,request);request['options']['caption']=True
        large=studio_space.estimate(self.src,request,100)
        self.assertGreater(large['required_max'],small['required_max']);self.assertGreater(large['required_min'],studio_space.RESERVE)
        with patch('archive.studio_space.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
            self.assertFalse(studio_space.preflight(self.path,self.src,request)['enough'])
            with self.assertRaisesRegex(ValueError,'공간이 부족'):studio_space.available(self.path)
    def test_cleanup_keeps_completed_and_source(self):
        file=self.job();check=clean.preview(self.path,file,'intermediate');self.assertEqual(check['names'],['clip-001-part.mp4'])
        trash=self.root/'trash';trash.mkdir()
        with patch.object(clean,'trash_path',side_effect=lambda f:f.rename(trash/f.name)):
            clean.clean(self.path,file,'intermediate',check['token'])
        self.assertTrue((file.parent/'clip-001.mp4').exists());self.assertTrue(self.source.exists());self.assertTrue(read_json(file)['intermediates_cleaned_at'])
    def test_cleanup_changed_or_unowned_or_original_blocks(self):
        file=self.job();check=clean.preview(self.path,file,'delete');(file.parent/'notes.txt').write_text('사용자 자료')
        with self.assertRaises(Conflict):clean.clean(self.path,file,'delete',check['token'])
        (file.parent/'notes.txt').unlink();(file.parent/'clip-001.mp4').write_bytes(b'changed')
        with self.assertRaises(Conflict):clean.preview(self.path,file,'delete')
        self.assertEqual(self.source.read_bytes(),b'original')
    def test_paused_intermediates_and_symlinks_block(self):
        file=self.job('paused')
        with self.assertRaises(Conflict):clean.preview(self.path,file,'intermediate')
        (file.parent/'linked').symlink_to(self.source)
        with self.assertRaises(Conflict):clean.preview(self.path,file,'delete')
    def test_failed_trash_keeps_record(self):
        file=self.job();check=clean.preview(self.path,file,'delete');before=file.read_bytes()
        with patch.object(clean,'trash_path',side_effect=OSError('볼륨 단절')),self.assertRaises(OSError):clean.clean(self.path,file,'delete',check['token'])
        self.assertEqual(file.read_bytes(),before)
    def test_metadata_and_modified_caption_protection(self):
        file=self.job();folder=file.parent
        (folder/'._clip-001-part.mp4').write_bytes(b'\x00\x05\x16\x07\x00\x02\x00\x00')
        (folder/'._clip-001.mp4').write_bytes(b'\x00\x05\x16\x07\x00\x02\x00\x00')
        check=clean.preview(self.path,file,'intermediate')
        self.assertIn('._clip-001-part.mp4',check['names']);self.assertNotIn('._clip-001.mp4',check['names'])
        (folder/'clip-001.srt').write_text('자막');value=read_json(file);output=value['outputs']['clip-001']
        output['assets']['srt']='clip-001.srt';output['asset_identities']={'srt':clean.identity(folder/'clip-001.srt')};save_json(file,value)
        (folder/'clip-001.srt').write_text('변경')
        with self.assertRaises(Conflict):clean.preview(self.path,file,'delete')
    def range_job(self):
        file=self.path/'studio/runs'/('c'*32)/'manifest.json';child=file.parent/'analysis/vod-1'
        save_json(child/'project.json',{'input':{'kind':'range','parent_vod':'1'}})
        (child/'range.mp4').write_bytes(b'range')
        save_json(file,dict(id=file.parent.name,kind='scope',state='complete',project={'root':str(child.parent),'path':str(child),'vod_id':'1'},outputs={}))
        return file,child
    def test_range_cleanup_locks_and_source_protection(self):
        from archive.storage import ProjectLock
        file,child=self.range_job();before=clean.preview(self.path,file,'delete')
        with ProjectLock(child):after=clean.preview(self.path,file,'delete')
        self.assertEqual(before['token'],after['token'])
        other=self.root/'vod-2/project.json'
        save_json(other,{'tasks':{'video':{'assets':{'original':str(child/'range.mp4')}}}})
        with self.assertRaisesRegex(Conflict,'원본 경로'):clean.preview(self.path,file,'delete')
        other.unlink();trash=self.root/'trash'
        with patch.object(clean,'trash_path',side_effect=lambda f:f.rename(trash)):
            clean.clean(self.path,file,'delete',before['token'])
        self.assertTrue((trash/'analysis/vod-1/range.mp4').exists());self.assertEqual(self.source.read_bytes(),b'original')
    def test_range_path_rejects_before_acquiring_child_lock(self):
        from archive.studio_range_cleanup import child_path
        file,child=self.range_job();value=read_json(file)
        value['project']['vod_id']='../../outside';save_json(file,value)
        with self.assertRaises(Conflict):child_path(file)
        value['project']['vod_id']='1';save_json(file,value)
        child.rename(child.with_name('backup'));child.symlink_to(child.with_name('backup'))
        with self.assertRaises(Conflict):child_path(file)
    def test_split_history_beyond_30_and_search(self):
        folder=self.root/'history';folder.mkdir();split=Splitter(SimpleNamespace(),folder)
        for i in range(35):
            name=f'{i:032x}';save_json(folder/name/'manifest.json',{'id':name,'created_at':str(i),'state':'complete','message':'완료','source_id':'x','source':{'name':f'영상{i:02}'}})
        first=split.dispatch('list',{});second=split.dispatch('list',{'offset':30})
        self.assertEqual(first['total'],35);self.assertEqual(len(first['runs'])+len(second['runs']),35)
        self.assertEqual(split.dispatch('list',{'query':'영상00'})['runs'][0]['name'],'영상00')
    def test_truthful_completion(self):
        self.assertEqual(completion_message([{'state':'complete'}]),'목록 처리 종료 · 완료 1개')
        self.assertIn('오류 1개',completion_message([{'state':'complete'},{'state':'error'}]))
        self.assertIn('일시정지',completion_message([{'state':'paused'}],True))
    def test_holdout_is_separate(self):
        corpus=json.loads(Path('tests/fixtures/context-quality/corpus.json').read_text())
        self.assertFalse({r['id'] for r in corpus['development']}&{r['id'] for r in corpus['holdout']})
        self.assertEqual(len({r['type'] for r in corpus['holdout']}),5)

if __name__=='__main__':unittest.main()
