"""완료본 교체의 커밋 경계와 기존 분석 입력 보존을 실제 수신 작업 경로로 검사한다."""
from pathlib import Path
import shutil
import threading
import unittest
from unittest.mock import patch

from archive import context_input, speech_media, speech_store, video, video_quality, video_replacement, range_download
from archive import replacement_timeline
from archive.jobs import Manager
from archive.storage import ProjectLock, load_project, save_json, recover
import test_speech

FIXTURE = Path(__file__).parent/'fixtures/https-media.mp4'


class ReplacementTests(unittest.TestCase):
    def setUp(self):
        fixture = test_speech.SpeechTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        self.root, self.path = str(fixture.root), fixture.path
        d=fixture.data
        self.meta=d['metadata']
        self.meta.update(duration=4,formats=[dict(id=f, height=h, fps=30, label=f) for f,h in [('360p',360),('new',72)]])
        self.old=fixture.video
        shutil.copyfile(FIXTURE,self.old)
        self.original=self.path/'media/original.mp4'
        shutil.copyfile(FIXTURE,self.original)
        d['tasks']['video'].update(verification={'duration':4.05},assets={'original':'media/original.mp4','playback':'media/playback.mp4'})
        save_json(self.path/'project.json',d)
        fixture.audio()
        fixture.transcribe()
        self.run=speech_store.manifest(self.path)
        self.selection={'transcript_run':self.run['id'],'speaker_run':None}
        save_json(self.path/'context/existing-result.json',{'title':'기존 분석'})
        self.manager=Manager(self.root)
        self.addCleanup(self.manager.close)
        for mock in [patch('archive.source.inspect',return_value=self.meta),
                     patch.object(video,'metadata',return_value=self.meta),
                     patch.object(self.manager.reports,'watch'),patch('archive.chat.collect',side_effect=AssertionError('채팅 재수집'))]:
            mock.start()
            self.addCleanup(mock.stop)

    def project(self):
        return load_project(self.path,'1')

    def input(self):
        return context_input.source(self.path,'1',selection=self.selection)

    def receive(self, policy, *, fail=False, changing_duration=False):
        started, finish = threading.Event(), threading.Event()
        original_input = self.input()
        original_files = {f:f.read_bytes() for folder in ('speech','context') for f in (self.path/folder).rglob('*') if f.is_file()}
        def factory(options):
            from unittest.mock import MagicMock
            dl=MagicMock()
            dl.extract_info.return_value={'id':'1','format_id':'new','height':72,'ext':'mp4','protocol':'https','duration':4}
            def transfer(info):
                started.set()
                if not finish.wait(6):
                    raise AssertionError('검사 대기 시간 초과')
                if fail:raise ValueError('수신 실패')
                shutil.copyfile(FIXTURE,options['outtmpl'])
            dl.process_info.side_effect=transfer
            dl.__enter__.return_value=dl
            return dl
        if changing_duration:
            data=self.project()
            data['tasks']['video']['verification']['duration']=80
            save_json(self.path/'project.json',data)
            original_input=self.input()
        with patch.object(video,'YoutubeDL',side_effect=factory):
            video_quality.change(self.manager,self.root,'1','360p','new',policy)
            try:
                self.assertTrue(started.wait(5))
                data=self.project()
                self.assertEqual(speech_media.source(self.path,data),self.old)
                self.assertEqual(original_input,self.input())
                self.assertTrue(self.original.is_file())
            finally:
                finish.set()
                self.manager.job.thread.join(10)
        self.assertFalse(self.manager.job.thread.is_alive())
        self.assertEqual(original_input,self.input())
        self.assertEqual(original_files,{f:f.read_bytes() for f in original_files})
        return self.project()

    def test_keep_and_reuse_existing_transcript(self):
        data=self.receive('keep')
        self.assertEqual(data['format_id'],'new')
        self.assertFalse(data.get('video_replacement'))
        self.assertEqual(len(data['saved_video_versions']),1)
        self.assertTrue(self.original.is_file() and self.old.is_file())
        self.assertNotEqual(speech_media.source(self.path,data),self.old)
        self.assertFalse(speech_store.view(self.path,data)['stale'])
        # 실제 재생 파일이 외부에서 달라지면 기존 검증은 계속 적용된다.
        with speech_media.source(self.path,data).open('ab') as file:file.write(b'changed')
        self.assertTrue(speech_store.view(self.path,data)['stale'])

    def test_delete_only_old_verified_video(self):
        stray=self.path/'media/other.mp4';stray.write_bytes(b'preserve')
        before=self.project()['tasks']['chat']
        data=self.receive('delete')
        self.assertEqual(data['format_id'],'new')
        self.assertFalse(data.get('video_cleanup'))
        self.assertFalse(self.old.exists() or self.original.exists())
        self.assertEqual(stray.read_bytes(),b'preserve')
        self.assertEqual(data['tasks']['chat'],before)
        self.assertFalse(speech_store.view(self.path,data)['stale'])

    def test_failure_and_timeline_mismatch_keep_playback(self):
        for fail in (True,False):
            with self.subTest(fail=fail):
                data=self.receive('delete',fail=fail,changing_duration=not fail)
                self.assertEqual(data['video_replacement']['task']['state'],'error')
                self.assertEqual(data['format_id'],'360p')
                self.assertTrue(self.original.is_file() and self.old.is_file())
                self.assertFalse(data.get('video_cleanup'))

    def test_cleanup_refuses_modified_symlink_active_and_non_media(self):
        data=self.project()
        extra=self.path/'media/range.mp4';extra.write_bytes(b'other')
        copy=self.path/'media/playback.tmp.mp4';copy.symlink_to(extra)
        def mark(file):
            s=file.stat()
            return dict(file=str(file.relative_to(self.path)),bytes=s.st_size,mtime_ns=s.st_mtime_ns)
        data['tasks']['video']['verification']['files']={'playback':mark(self.old),'original':mark(self.original)}
        # 과거 JSON의 표기와 현재 OS에서 만든 정리 경로가 달라도 활성 파일을 보호한다.
        data['tasks']['video']['assets']['playback']='media/./playback.mp4'
        kept=self.path/'media/playback-00000000000000000000000000000000.mp4'
        kept.write_bytes(b'previous')
        data['saved_video_versions']=[{'assets':{'playback':'media/./'+kept.name}}]
        data['video_cleanup']=[mark(extra),mark(copy),mark(self.old),mark(self.path/'project.json')]
        data['video_cleanup'].append(mark(kept))
        extra.write_bytes(b'different')
        self.assertFalse(video_replacement.cleanup(self.path,data))
        self.assertTrue(extra.exists() and copy.is_symlink() and self.old.exists() and kept.exists())

    def test_cleanup_after_restart_requires_intact_new_files(self):
        with patch('archive.jobs.cleanup',return_value=False), patch.object(video_replacement,'cleanup',return_value=False):
            data=self.receive('delete')
        self.assertTrue(self.old.exists() and data['video_cleanup'])
        new=speech_media.source(self.path,data)
        hidden=new.with_name('moved.mp4')
        with ProjectLock(self.path):
            new.rename(hidden)
            self.assertFalse(video_replacement.cleanup(self.path,data))
            hidden.rename(new)
            recover(self.path,data)
        self.assertFalse(self.old.exists() or self.original.exists())
        self.assertFalse(self.project().get('video_cleanup'))

    def test_range_replacement_receives_same_bounds_and_only_video(self):
        data=self.project()
        span={'start_ms':10000,'end_ms':14000}
        data.update(input={'kind':'range','start_vod_ms':10000,'end_vod_ms':14000},download_range=span)
        self.meta['duration']=20
        data['metadata'].update(source_title='원본 제목',duration=20)
        save_json(self.path/'project.json',data)
        before=self.input()
        def receive(vod,a,b,target,stop,lock,update,**kwargs):
            self.assertEqual((vod,a,b,kwargs['format_id']),('1',10000,14000,'new'))
            shutil.copyfile(FIXTURE,target)
            return {'duration':4}
        with patch.object(range_download.remote_media,'receive',side_effect=receive):
            video_quality.change(self.manager,self.root,'1','360p','new','keep')
            self.manager.job.thread.join(10)
        self.assertEqual(self.project()['tasks']['video']['verification']['range_ms'],[10000,14000])
        self.assertEqual(before,self.input())

    def test_stop_resume_after_app_restart_preserves_committed_video(self):
        from archive.source import Cancelled
        started=threading.Event()
        def interrupted(project, stop):
            project.update('video',state='downloading')
            started.set()
            if not stop.wait(5):
                raise AssertionError('중단 신호 누락')
            raise Cancelled()
        with patch.object(video,'download',side_effect=interrupted):
            video_quality.change(self.manager,self.root,'1','360p','new','delete')
            self.assertTrue(started.wait(4))
            self.manager.stop(self.root,'1','video')
            self.manager.job.thread.join(8)
        data=self.project()
        generation=data['video_replacement']['generation']
        self.assertEqual(data['video_replacement']['task']['state'],'paused')
        self.assertTrue(self.original.exists() and self.old.exists())
        manager=Manager(self.root)
        self.addCleanup(manager.close)
        def resumed(project, stop):
            self.assertEqual((project.data['video_generation'],project.data['format_id']),(generation,'new'))
            folder=video_quality.media_directory(project);folder.mkdir(parents=True)
            target=folder/'original.mp4';shutil.copyfile(FIXTURE,target)
            relative=str(target.relative_to(project.path))
            project.update('video', state='complete',assets=dict.fromkeys(('original','playback'),relative),
                           verification={'duration':4,'decode_exit_code':0,'files':dict.fromkeys(('original','playback'),video.media_timeline.identity(target))})
        with patch.object(video,'download',side_effect=resumed), patch.object(manager.reports,'watch'):
            manager.start(self.root,'1','360p','video')
            manager.job.thread.join(8)
        self.assertEqual(self.project()['format_id'],'new',self.project().get('video_replacement',{}).get('task'))
        self.assertFalse(self.original.exists() or self.old.exists())

    def test_preserved_file_can_be_retrieved_by_version(self):
        from urllib.request import urlopen
        from urllib.parse import urlencode
        from archive.server import make_server
        data=self.receive('keep')
        server,url=make_server(self.manager)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            query=urlencode({'root':self.root,'vod_id':'1','kind':'saved-video','key':'original',
                             'version':data['saved_video_versions'][0]['id']})
            with urlopen(url+'file?'+query,timeout=5) as response:
                self.assertEqual(response.read(),self.original.read_bytes())
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_verified_failed_swap_retries_only_final_check(self):
        with patch.object(replacement_timeline,'compare',side_effect=ValueError('시각 대조 보류')):
            failed=self.receive('keep')
        self.assertEqual(failed['video_replacement']['task']['state'],'error')
        saved=video_replacement.verified_download(self.path.resolve(),failed)
        self.assertIsNotNone(saved)
        with patch.object(video,'download',side_effect=AssertionError('중복 수신 또는 디코딩')):
            self.manager.start(self.root,'1','360p','video')
            self.manager.job.thread.join(10)
        self.assertEqual(self.project()['format_id'],'new')
        self.assertEqual(saved['assets'],self.project()['tasks']['video']['assets'])

    def test_modified_media_or_source_is_not_a_verified_retry(self):
        with patch.object(replacement_timeline,'compare',side_effect=ValueError('시각 대조 보류')):
            failed=self.receive('keep')
        folder=self.path.resolve()/'media'/failed['video_replacement']['generation']
        source=folder/'source.json';original_source=source.read_bytes()
        save_json(source,{'id':'2','format_id':'new'})
        self.assertIsNone(video_replacement.verified_download(self.path.resolve(),failed))
        source.write_bytes(original_source)
        with (folder/'original.mp4').open('ab') as f:f.write(b'changed')
        self.assertIsNone(video_replacement.verified_download(self.path.resolve(),failed))
