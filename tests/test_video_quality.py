"""화질 전환 후 예전 영상 조각과 채팅을 재사용하는 경계를 검사한다."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from archive import download_scope, range_download, video, video_quality
from archive.automation import options
from archive.jobs import Job, Manager
from archive.storage import Conflict, Project, ProjectLock, load_project, save_json
from test_automation_reports import meta


class QualityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = str(Path(tmp.name).resolve())
        self.manager = Manager(self.base)
        self.addCleanup(self.manager.close)
        self.meta = meta('1')
        self.meta['formats'] = [dict(id=f'f{n}', height=n, fps=30, label=f'{n}p') for n in (480,1080)]
        lookup = patch('archive.source.inspect', return_value=self.meta)
        lookup.start()
        self.addCleanup(lookup.stop)

    def prepare(self, scope=None):
        item = self.manager.automation.add(self.base, self.meta['url'], {'download_range':scope})['items'][0]
        self.root = item['project_root']
        self.path = Path(self.root)/'vod-1'
        data = load_project(self.path, '1')
        data['tasks']['video']['state'] = 'paused'
        (self.path/'media').mkdir()
        self.part = self.path/'media/original.mp4.part'
        self.part.write_bytes(b'old partial')
        self.chat = self.path/'chat-pages/000000.json'
        save_json(self.chat, {'example':'preserved'})
        data['tasks']['chat'].update(state='complete', assets={'json':'chat-pages/000000.json'})
        save_json(self.path/'project.json',data)
        return data

    def change(self):
        return video_quality.change(self.manager,self.root,'1','f480','f1080')

    def test_full_restart_uses_new_path_and_queue_format(self):
        old = self.prepare()
        view = self.change()
        row = self.manager.automation.status(self.base)['items'][0]
        self.assertEqual((view['format_id'],row['format'],row['options']['height']), ('f1080','f1080',1080))
        self.assertEqual(view['tasks']['chat'], old['tasks']['chat'])
        with ProjectLock(self.path) as lock:
            project = Project(self.path,load_project(self.path,'1'),lock)
            # 새 전송까지 진행하되 실제 네트워크에서 영상은 받지 않는다.
            with patch.object(video, 'YoutubeDL') as factory:
                dl = factory.return_value.__enter__.return_value
                dl.extract_info.return_value = {'format_id':'f1080','id':'1','protocol':'https','ext':'mp4'}
                dl.process_info.side_effect = InterruptedError('전송 진입')
                with self.assertRaisesRegex(InterruptedError,'전송 진입'):
                    video.download(project, threading.Event())
                dest = Path(factory.call_args.args[0]['outtmpl'])
                self.assertNotEqual(dest.parent,self.part.parent)
                self.assertEqual(dest.parent,video_quality.media_directory(project))
                self.assertTrue((dest.parent/'source.json').is_file())
        self.assertEqual(self.part.read_bytes(),b'old partial')
        self.assertTrue(self.chat.is_file())
        with self.assertRaises(Conflict): self.change()

    def test_range_selects_new_file_and_can_register_old_quality_again(self):
        scope={'start_ms':1000,'end_ms':3000}
        self.prepare(scope)
        old_target=self.path/'media/range.mp4'
        old_target.write_bytes(b'old quality')
        self.change()
        with ProjectLock(self.path) as lock:
            project=Project(self.path,load_project(self.path,'1'),lock)
            def receive(vod,a,b,target,event,fd,update,**kwargs):
                self.assertEqual((a,b,kwargs['format_id']), (1000,3000,'f1080'))
                target.write_bytes(b'new quality')
                return {'duration':2}
            with patch.object(range_download.remote_media,'receive',side_effect=receive), patch.object(range_download.clip_render,'probe',return_value={}):
                range_download.download(project,threading.Event())
            asset=self.path/project.data['tasks']['video']['assets']['original']
            self.assertEqual(asset.read_bytes(),b'new quality')
        self.assertEqual(old_target.read_bytes(),b'old quality')
        def register(height):
            return download_scope.prepare(self.base,self.meta,options({'download_range':scope,'height':height}))[0]
        self.assertEqual(register(1080),self.root)
        old_root=register(480)
        self.assertNotEqual(old_root,self.root)
        self.assertEqual(register(480),old_root)
        with self.assertRaisesRegex(Conflict,'이미 있습니다'):
            video_quality.change(self.manager,old_root,'1','f480','f1080')

    def test_running_complete_and_unavailable_do_not_modify_anything(self):
        data=self.prepare()
        for state in ('running','stopping','complete','paused'):
            data['tasks']['video']['state']=state
            save_json(self.path/'project.json',data)
            before=(self.path/'project.json').read_bytes()
            formats=self.meta['formats'][:1] if state=='paused' else self.meta['formats']
            with patch('archive.source.inspect',return_value=self.meta | {'formats':formats}), self.assertRaises(ValueError):
                self.change()
            self.assertEqual((self.path/'project.json').read_bytes(),before)

    def test_chat_worker_can_checkpoint_after_video_switch(self):
        self.prepare()
        with ProjectLock(self.path) as lock:
            project=Project(self.path,load_project(self.path,'1'),lock)
            self.manager.job=Job(project,self.manager.guard)
            try:
                project.update('chat',state='running',progress={'pages':2})
                self.change()
                project.update('chat',progress={'pages':3})
                data=load_project(self.path,'1')
                self.assertEqual(data['tasks']['chat']['progress'],{'pages':3})
                self.assertEqual(data['format_id'],'f1080')
                self.assertTrue(data['video_generation'])
            finally:
                self.manager.job=None
