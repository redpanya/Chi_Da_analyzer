"""목록 통합: 실제 사용자 보관함·네트워크·모델을 사용하지 않는 회귀 검사."""
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from archive import automation_steps, media_timeline
from archive.automation import options
from archive.jobs import Manager
from archive.source import Cancelled
from archive.storage import Conflict, ProjectLock, create_or_load, project_path, load_project, save_json
from test_automation_reports import meta, HARDWARE


class QueueRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.manager = Manager(self.root)
        self.queue = self.manager.automation
        self.hardware = patch('archive.report_hardware.collect', return_value=HARDWARE)
        self.hardware.start()

    def tearDown(self):
        self.manager.close()
        self.hardware.stop()
        self.tmp.cleanup()

    def project(self, vod='1', *, complete=True, local=False, legacy=False):
        path = project_path(self.root, vod)
        with ProjectLock(path):
            data = create_or_load(path, meta(vod), '720p', {'name': 'video.mp4'} if local else None)
            if complete:
                file = path/'media/original.mp4'
                file.parent.mkdir(exist_ok=True)
                file.write_bytes(b'original-video-'+vod.encode())
                chat = path/'exports/chat.jsonl'
                chat.parent.mkdir(exist_ok=True)
                chat.write_text('{"text":"받아둔 채팅"}\n')
                proof = {'duration': 5, 'decode_exit_code': 0, 'original_sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
                if local:
                    proof.update(source='local', sha256=proof.pop('original_sha256'))
                if not legacy:
                    proof['files'] = {k: media_timeline.identity(file) for k in ('original','playback')}
                data['tasks']['video'].update(state='complete', assets={'original':'media/original.mp4','playback':'media/original.mp4'}, verification=proof)
                data['tasks']['chat'].update(state='complete', assets={'jsonl':'exports/chat.jsonl'})
                save_json(path/'project.json', data)
        return path

    def register(self, vod='1', settings=None):
        return self.queue.add_saved(self.root, [vod], settings or {})['items'][-1]

    def test_per_vod_background_is_kept_when_applying_common_settings(self):
        self.project('1');self.project('2')
        a=self.register('1',{'background':'게임 방송'})
        b=self.register('2',{'background':'노래 방송'})
        result=self.queue.update_settings(self.root,[a['id'],b['id']],{'mode':'analysis'})
        self.assertEqual([i['options']['background'] for i in result['items']],['게임 방송','노래 방송'])
        self.assertEqual(self.manager.context_background(self.root,'1')['text'],'')
        self.manager.context_background(self.root,'1','저장 설명')
        self.assertEqual(self.manager.context_background(self.root,'1')['text'],'저장 설명')
        with ProjectLock(project_path(self.root,'1')):
            with self.assertRaises(Conflict):self.manager.context_background(self.root,'1','동시 변경')

    def run_queue(self):
        self.queue.start(self.root)
        self.queue.thread.join(5)
        self.assertFalse(self.queue.thread.is_alive())
        return self.queue.status(self.root)

    def execute(self, entry, stage='download'):
        self.queue.root = self.root
        with patch.object(self.manager.reports, 'skipped'):
            return automation_steps.execute(self.queue, entry, stage)

    def test_saved_offline_order_partial_registration_and_no_phantom_folder(self):
        self.project('2'); self.project('1')
        with patch.object(self.manager, 'inspect', side_effect=AssertionError('외부 조회 금지')):
            result = self.queue.dispatch('add-saved', dict(root=self.root, vod_ids=['2','999','1'], options={'mode':'analysis'}))
        self.assertEqual(result['added'], ['2','1'])
        self.assertEqual([i['vod'] for i in result['items']], ['2','1'])
        self.assertEqual(result['errors'][0]['vod'], '999')
        self.assertFalse(project_path(self.root, '999').exists())
        self.assertIsNone(self.queue.thread)

    def test_download_quality_selection_default_and_ceiling(self):
        for height in (1080, 720, 480):
            self.assertEqual(options({'height':height})['height'],height)
        self.assertEqual(options({})['height'],480)
        self.assertEqual(options({'height':0})['height'],1080)
        for invalid in (2160,360,'1080',True,None):
            with self.assertRaises(ValueError): options({'height':invalid})
        for vod,settings,expected in [('1',{},480),('2',{'height':720},720),('3',{'height':1080},1080),('4',{'height':0},1080)]:
            source=meta(vod)
            source['formats']=[{'id':f'{h}p','height':h} for h in (2160,1080,720,480)]
            with patch.object(self.manager,'inspect',return_value=source):
                item=self.queue.add(self.root,'https://naver.me/test',settings)['items'][-1]
            self.assertEqual(item['format'],f'{expected}p')
            self.assertEqual(load_project(project_path(self.root,vod),vod)['format_id'],f'{expected}p')

    def test_quality_uses_available_lower_format_and_rejects_only_higher(self):
        with patch.object(self.manager,'inspect',return_value=meta('1')):
            item=self.queue.add(self.root,'https://naver.me/test',{'height':1080})['items'][0]
        self.assertEqual(item['format'],'720p')
        missing=meta('2');missing['formats']=[{'id':'720p','height':720},{'id':'unknown','height':None}]
        with patch.object(self.manager,'inspect',return_value=missing):
            with self.assertRaisesRegex(ValueError,'480p'):
                self.queue.add(self.root,'https://naver.me/test',{})
        self.assertEqual(len(self.queue.read(self.root)['items']),1)
        self.assertFalse((project_path(self.root,'2')/'project.json').exists())

    def test_url_then_saved_identity_dedup_and_quality_preserved(self):
        self.project()
        with patch.object(self.manager,'inspect',return_value=meta('1')):
            first = self.queue.add(self.root,'https://naver.me/test',{'height':1080})['items'][0]
        result = self.queue.add_saved(self.root,['1'],{'height':480})
        self.assertEqual(len(result['errors']),1)
        self.assertEqual(first['format'],'720p')
        self.assertEqual(len(result['items']),1)
        for state in ('queued','paused','error','partial','running'):
            self.queue.change(self.root,lambda data: data['items'][0].update(state=state))
            self.assertEqual(len(self.queue.add_saved(self.root,['1'],{})['errors']),1)

    def test_completed_followup_keeps_old_report_and_never_starts_downloader(self):
        path=self.project()
        manual=path/'speech/manual.json';manual.parent.mkdir();manual.write_text('보존할 수동 교정')
        self.register()
        with patch.object(self.manager,'start',side_effect=AssertionError('다운로드 재실행 금지')):
            first=self.run_queue()['items'][0]
            old_report=path/'diagnostics/reports'/(first['report']+'.json');original_report=old_report.read_bytes()
            followup=self.register(settings={'mode':'analysis'})
            self.assertEqual(self.queue.status(self.root)['state'], 'idle')
            self.assertNotEqual(followup['id'],first['id'])
            real_execute=automation_steps.execute
            def run(queue,entry,stage):
                return real_execute(queue,entry,stage) if stage=='download' else 'reused'
            with patch('archive.automation.steps.execute',side_effect=run):
                last=self.run_queue()['items'][-1]
        self.assertNotEqual(first['report'],last['report'])
        self.assertEqual(last['stages']['download'],'reused')
        self.assertEqual(old_report.read_bytes(),original_report)
        self.assertEqual(manual.read_text(),'보존할 수동 교정')
        payload=self.manager.reports.snapshot(self.root,'1',last['report'])['payload']
        self.assertEqual(payload['stages'][0]['state'],'reused')
        with self.assertRaises(Conflict):self.queue.remove_or_retry(self.root,first['id'],retry=True)

    def test_chat_only_resume_preserves_video_and_saved_pages(self):
        path=self.project();data=load_project(path,'1');data['tasks']['chat']['state']='paused';save_json(path/'project.json',data)
        page=path/'chat-pages/000001.json';page.parent.mkdir();page.write_text('저장 응답 유지')
        item=self.register()
        def collect(project,stop):
            self.assertEqual(page.read_text(),'저장 응답 유지')
            project.update('chat',state='complete')
        with patch('archive.jobs.video.download',side_effect=AssertionError('영상 재수신 금지')),patch('archive.jobs.chat.collect',collect),patch.object(self.manager,'start',wraps=self.manager.start) as start:
            self.assertEqual(self.run_queue()['items'][0]['state'],'complete')
        self.assertEqual(start.call_args.args[-1],'chat')
        self.assertEqual((path/'media/original.mp4').read_bytes(),b'original-video-1')

    def test_unverified_video_uses_existing_verification_worker(self):
        path=self.project();data=load_project(path,'1');data['tasks']['video'].pop('verification');save_json(path/'project.json',data)
        self.register()
        def verify(project,stop):project.update('video',state='complete',verification={'duration':5})
        with patch('archive.jobs.video.download',verify),patch('archive.jobs.chat.collect',side_effect=AssertionError('채팅 재수신 금지')),patch.object(self.manager,'start',wraps=self.manager.start) as start:
            self.assertEqual(self.run_queue()['items'][0]['state'],'complete')
        self.assertEqual(start.call_args.args[-1],'video')

    def test_legacy_local_ready_and_incomplete_local_never_online_download(self):
        path=self.project(local=True,legacy=True);item=self.register()
        with patch.object(self.manager,'start',side_effect=AssertionError('온라인 대체 금지')):
            self.assertEqual(self.execute(item),'reused')
        self.assertTrue((path/'diagnostics/automation-media.json').exists())
        path2=self.project('2',complete=False,local=True);item2=self.register('2')
        with patch.object(self.manager,'start',side_effect=AssertionError('온라인 대체 금지')),self.assertRaisesRegex(ValueError,'같은 파일'):
            self.execute(item2)

    def test_changed_original_is_preserved_and_not_overwritten(self):
        path=self.project();item=self.register();file=path/'media/original.mp4';file.write_bytes(b'user-replaced-file')
        with patch.object(self.manager,'start',side_effect=AssertionError('덮어쓰기 금지')),self.assertRaisesRegex(ValueError,'원본 영상이 다릅니다'):
            self.execute(item)
        self.assertEqual(file.read_bytes(),b'user-replaced-file')

    def test_review_chat_requires_opt_in_and_missing_export_not_reused(self):
        path=self.project();data=load_project(path,'1');data['tasks']['chat']['state']='review';save_json(path/'project.json',data)
        item=self.register(settings={'allow_partial_chat':True})
        with patch.object(self.manager,'start',side_effect=AssertionError('수신 금지')):
            self.assertEqual(self.execute(item),'partial')
        from archive.automation_media import chat_ready
        self.assertFalse(chat_ready(path,data['tasks']['chat'],False))
        (path/'exports/chat.jsonl').unlink()
        self.assertFalse(chat_ready(path,data['tasks']['chat'],True))

    def test_settings_atomic_and_execution_history_guard(self):
        self.project('1');self.project('2');one=self.register('1');two=self.register('2')
        data=self.queue.update_settings(self.root,[one['id']],{'mode':'analysis','height':480})
        self.assertEqual(data['items'][0]['options']['mode'],'analysis')
        self.assertEqual(data['items'][1]['options']['mode'],'download')
        self.assertEqual(data['items'][0]['format'],'720p')
        self.queue.change(self.root,lambda d:d['items'][1].update(report='old-report'))
        with self.assertRaises(Conflict):self.queue.update_settings(self.root,[one['id'],two['id']],{})
        self.assertEqual(self.queue.read(self.root)['items'][0]['options']['mode'],'analysis')
        self.queue.running=True
        try:
            with self.assertRaises(Conflict):self.queue.update_settings(self.root,[one['id']],{})
        finally:self.queue.running=False

    def test_missing_or_linked_saved_project_rejected(self):
        outside=Path(self.tmp.name)/'outside';outside.mkdir();(Path(self.root)/'vod-1').symlink_to(outside)
        result=self.queue.add_saved(self.root,['1','../outside'],{})
        self.assertEqual(len(result['errors']),2);self.assertEqual(result['items'],[])

    def test_cancel_during_legacy_validation_is_paused(self):
        self.project(legacy=True);item=self.register()
        with patch('archive.automation_media.video_ready',side_effect=Cancelled()),self.assertRaises(automation_steps.Paused):
            self.execute(item)
