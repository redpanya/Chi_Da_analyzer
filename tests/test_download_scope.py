"""전체/구간 보존, 목록 재연결, 원본 시각과 재생 시각의 공통 계약 검사."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from archive import download_scope as scope, automation, automation_steps, range_download, analysis_store, chat
from archive.jobs import Manager
from archive.storage import Conflict, Project, ProjectLock, load_project, project_path, read_json, save_json
from archive.source import Cancelled
from test_automation_reports import meta, HARDWARE
from test_archive import message, page


class DownloadScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.manager=Manager(str(self.root));self.addCleanup(self.manager.close)
        self.metadata=meta('1') | {'duration':100}
        p=patch.object(self.manager,'inspect',return_value=self.metadata);p.start();self.addCleanup(p.stop)
        p=patch('archive.report_hardware.collect',return_value=HARDWARE);p.start();self.addCleanup(p.stop)
        self.range={'start_ms':10000,'end_ms':12000}

    def add(self, value=None):
        return self.manager.automation.add(str(self.root),'https://chzzk.naver.com/video/1',value or {})['items'][-1]

    def project(self):
        root,data=scope.prepare(self.root,self.metadata,automation.options({'download_range':self.range}))
        path=project_path(root,'1');lock=ProjectLock(path);self.addCleanup(lock.close)
        return Project(path,data,lock)

    def test_input_bounds_and_legacy(self):
        self.assertIsNone(automation.options({})['download_range'])
        for r in [{'start_ms':0,'end_ms':999},{'start_ms':-1,'end_ms':3000},
                  {'start_ms':True,'end_ms':3000},{'start_ms':0.0,'end_ms':3000},
                  {'start_ms':5000,'end_ms':3000},{'start_ms':0,'end_ms':72000001}, {'start_ms':0}]:
            with self.subTest(r=r),self.assertRaises(ValueError):automation.options({'download_range':r})
        with self.assertRaises(ValueError):self.add({'download_range':{'start_ms':0,'end_ms':101000}})
        with self.assertRaises(ValueError):automation.options({'steps':['context'],'download_range':self.range})
        self.assertFalse(list(self.root.glob('vod-*')))

    def test_full_and_ranges_have_separate_identity_and_no_overwrite(self):
        full=self.add();original=project_path(self.root,'1')/'original.mp4';original.write_bytes(b'preserve')
        before=(original.parent/'project.json').read_bytes()
        ranged=self.add({'download_range':self.range})
        high=self.add({'download_range':self.range,'height':720})
        other=self.add({'download_range':{'start_ms':12000,'end_ms':14000}})
        self.assertEqual(len({i['project_root'] for i in (full,ranged,high,other)}),4)
        self.assertEqual(original.read_bytes(),b'preserve');self.assertEqual((original.parent/'project.json').read_bytes(),before)
        with self.assertRaises(Conflict):self.add({'download_range':self.range})
        self.assertEqual(len(self.manager.projects(str(self.root))),4)
        view=self.manager.view(ranged['project_root'],'1')
        self.assertEqual(view['library_root'],str(self.root));self.assertEqual(view['input']['start_vod_ms'],10000)

    def test_pending_settings_retarget_and_new_manager_resume(self):
        queue=self.manager.automation;item=self.add()
        before=(self.root/'vod-1/project.json').read_bytes()
        queue.update_settings(str(self.root),[item['id']],{'download_range':self.range,'steps':['download','audio']})
        updated=queue.read(str(self.root))['items'][0]
        self.assertNotEqual(updated['project_root'],str(self.root));self.assertEqual((self.root/'vod-1/project.json').read_bytes(),before)
        fresh=Manager(str(self.root));self.addCleanup(fresh.close)
        self.assertEqual(fresh.automation.status(str(self.root))['items'][0]['project_root'],updated['project_root'])
        queue.remove_or_retry(str(self.root),item['id'])
        saved=queue.add_saved(str(self.root),['1'],{'steps':['audio']},updated['project_root'])
        self.assertFalse(saved['errors']);self.assertEqual(saved['items'][0]['project_root'],updated['project_root'])

    def test_paths_cannot_escape_managed_roots(self):
        for path in (self.root/'other',self.root/'..'/'other',self.root/'.download-ranges'/'invalid'):
            with self.assertRaises(ValueError):scope.checked_root(self.root,path)
        outside=self.root/'outside';outside.mkdir()
        (self.root/'.download-ranges').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(Conflict):self.add({'download_range':self.range})

    def test_followup_stage_uses_selected_range_root(self):
        item=self.add({'download_range':self.range,'steps':['download','audio']})
        queue=self.manager.automation;queue.root=str(self.root)
        class Job:closed=True
        with patch('archive.automation_steps.check_inputs'),patch.object(self.manager,'speech_info',return_value={'tracks':[{'index':1}]}), \
             patch.object(self.manager,'speech_start') as start,patch('archive.automation_steps.speech_store.state',side_effect=[{}, {'state':'complete'}]):
            self.manager.speech_job=Job()
            self.assertEqual(automation_steps.execute(queue,item,'audio'),'complete')
            start.assert_called_once_with(item['project_root'],'1','audio',track=1)
            self.manager.speech_job=None

    def test_completed_range_reused_without_network_and_partial_kept(self):
        project=self.project();media=project.path/'media';media.mkdir(exist_ok=True)
        target=media/'range.mp4';target.write_bytes(b'finished');part=media/'old.part.mp4';part.write_bytes(b'partial')
        with patch('archive.range_download.remote_media.receive',side_effect=AssertionError('재다운로드 금지')), \
             patch('archive.range_download.clip_render.verify',return_value={'duration':2}),patch('archive.range_download.clip_render.probe',return_value={}):
            range_download.download(project,threading.Event())
        task=project.snapshot()['tasks']['video'];self.assertEqual(task['state'],'complete')
        self.assertEqual(task['assets']['original'],task['assets']['playback']);self.assertEqual(part.read_bytes(),b'partial')
        self.assertEqual(task['verification']['range_ms'],[10000,12000])

    def test_cancelled_video_is_kept_and_retry_uses_new_temporary_file(self):
        project=self.project();stop=threading.Event();attempts=[]
        def receive(vod,a,b,target,event,lock,update,**kwargs):
            self.assertEqual((vod,a,b,kwargs['format_id']),('1',10000,12000,'480p'))
            attempts.append(target);target.write_bytes(b'partial' if len(attempts)==1 else b'complete')
            if len(attempts)==1:raise Cancelled()
            return {'duration':2}
        with patch('archive.range_download.remote_media.receive',side_effect=receive),patch('archive.range_download.clip_render.probe',return_value={}):
            with self.assertRaises(Cancelled):range_download.download(project,stop)
            self.assertFalse((project.path/'media/range.mp4').exists())
            range_download.download(project,stop)
        self.assertNotEqual(attempts[0],attempts[1]);self.assertEqual(attempts[0].read_bytes(),b'partial')
        self.assertEqual((project.path/'media/range.mp4').read_bytes(),b'complete')

    def test_chat_range_boundary_repair_repeat_resume_and_analysis_clock(self):
        project=self.project();stop=threading.Event();repeated=message(11000,'실제 반복') | {'userIdHash':'같은 이용자'}
        first=page([message(9999,'범위 밖'),message(10000),repeated],11000)
        last=page([message(11999),message(12000,'범위 밖')],12000)
        def paused(vod,cursor,event):stop.set();return first
        with patch('archive.chat.fetch',side_effect=paused):chat.collect(project,stop)
        self.assertEqual(project.data['tasks']['chat']['state'],'paused')
        old=project.data['tasks']['chat']['assets']['json'];raw=(project.path/'chat-pages/000000.json').read_bytes()
        stop.clear();responses={11000:last,9999:first,10999:page([repeated,repeated,message(11999)],12000),11999:page([message(12000)],None)}
        with patch('archive.chat.fetch',side_effect=lambda vod,cursor,event:responses[cursor]):chat.collect(project,stop)
        task=project.data['tasks']['chat'];self.assertEqual(task['state'],'complete');self.assertEqual(task['verification']['recovered'],1)
        rows=read_json(project.path/task['assets']['json'])['messages']
        self.assertEqual([r['offset_ms'] for r in rows],[10000,11000,11000,11999])
        self.assertEqual([r['clip_offset_ms'] for r in rows],[0,1000,1000,1999])
        self.assertTrue((project.path/old).exists());self.assertEqual((project.path/'chat-pages/000000.json').read_bytes(),raw)
        project.update('video',state='complete',verification={'duration':2})
        self.assertEqual([r['offset_ms'] for r in analysis_store.rows(project.path,project.data)],[0,1000,1000,1999])
        analysis_store.run(project.path,project.data,{},False)
        with patch('archive.chat.fetch',side_effect=AssertionError('보존 자료만으로 복구')):chat.collect(project,stop)
        self.assertEqual(project.data['tasks']['chat']['verification']['network_requests'],0)


if __name__=='__main__':unittest.main()
