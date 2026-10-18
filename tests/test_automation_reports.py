"""실자료를 건드리지 않는 순차 실행·중단·이메일 리포트 경계 검사."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from archive.jobs import Manager
from archive.automation import options
from archive.automation_steps import Paused, Prerequisite, wait
from archive import report_schema
from archive.storage import Conflict, ProjectLock, project_path, save_json

HARDWARE = dict(os='Darwin', os_version='25', architecture='arm64', cpu='Apple M1', gpu='Apple M1', cores=8, threads=8, ram_bytes=16*1024**3)


def meta(vod):
    return {'id': vod, 'title': '비공개 제목', 'channel': '채널 이름', 'duration': 5,
            'chat_enabled': True, 'formats': [{'id': '720p', 'height': 720, 'estimated_bytes': 10}],
            'url': 'https://chzzk.naver.com/video/' + vod}


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self.tmp.name))
        self.manager = Manager(self.root)
        self.hardware = patch('archive.report_hardware.collect', return_value=HARDWARE)
        self.hardware.start()
        self.inspect = patch.object(self.manager, 'inspect', side_effect=lambda url: meta(url[-1]))
        self.inspect.start()

    def tearDown(self):
        self.manager.close()
        self.hardware.stop()
        self.inspect.stop()
        self.tmp.cleanup()

    def add(self, vod='1', settings=None):
        return self.manager.automation.add(self.root, 'https://chzzk.naver.com/video/'+vod, settings or {})['items'][-1]

    def finish(self):
        self.manager.automation.thread.join(5)
        self.assertFalse(self.manager.automation.thread.is_alive())
        return self.manager.automation.status(self.root)

    def test_order_optional_speakers_and_no_separation(self):
        self.add('1', {'mode': 'analysis', 'speakers_enabled': True})
        self.add('2')
        calls = []
        with patch('archive.automation.steps.execute', side_effect=lambda q,e,s: calls.append((e['vod'],s)) or 'complete'):
            self.manager.automation.start(self.root)
            result = self.finish()
        self.assertEqual(calls, [('1', s) for s in ['download','audio','transcribe','diarize','reactions','summary']] + [('2','download')])
        self.assertTrue(all(i['state']=='complete' for i in result['items']))
        with self.assertRaises(ValueError):
            options({'separation': True})

    def test_duplicate_and_remove_preserve_project_and_sources(self):
        item = self.add()
        file = project_path(self.root, '1')/'original.mp4'
        file.write_bytes(b'keep original')
        with self.assertRaises(Conflict):
            self.add()
        self.manager.automation.remove_or_retry(self.root, item['id'])
        self.assertEqual(file.read_bytes(), b'keep original')
        self.assertTrue((file.parent/'project.json').exists())

    def test_error_does_not_block_next_vod(self):
        self.add('1'); self.add('2')
        def execute(queue, entry, stage):
            if entry['vod']=='1': raise ValueError('작업 오류')
            return 'complete'
        with patch('archive.automation.steps.execute', side_effect=execute):
            self.manager.automation.start(self.root)
            result = self.finish()
        self.assertEqual([i['state'] for i in result['items']], ['error', 'complete'])
        saved=self.manager.reports.snapshot(self.root,'1',result['items'][0]['report'])
        self.assertEqual(saved['payload']['stages'][0]['state'],'error')

    def test_missing_prerequisite_pauses_all(self):
        self.add('1');self.add('2')
        with patch('archive.automation.steps.execute', side_effect=Prerequisite('모델 준비 필요')):
            self.manager.automation.start(self.root)
            result = self.finish()
        self.assertEqual(result['state'], 'paused')
        self.assertEqual([i['state'] for i in result['items']], ['paused', 'queued'])

    def test_pause_manual_exclusion_and_resume(self):
        self.add('1');self.add('2')
        entered=threading.Event()
        def execute(queue, entry, stage):
            entered.set();queue.stop.wait(3);raise Paused()
        with patch('archive.automation.steps.execute', side_effect=execute):
            self.manager.automation.start(self.root)
            self.assertTrue(entered.wait(2))
            with self.assertRaises(Conflict): self.manager.speech_idle()
            with self.assertRaises(Conflict): self.manager.start(self.root, '2', '720p', 'all')
            item=self.manager.automation.status(self.root)['items'][0]
            with self.assertRaises(Conflict): self.manager.automation.remove_or_retry(self.root,item['id'])
            self.manager.automation.pause();result=self.finish()
        self.assertEqual(result['items'][0]['state'],'paused')
        with patch('archive.automation.steps.execute', return_value='complete'):
            self.manager.automation.start(self.root);result=self.finish()
        self.assertEqual([i['state'] for i in result['items']],['complete','complete'])

    def test_restart_is_paused_not_autostart(self):
        self.add()
        def interrupted(data):
            data['state']='running';data['items'][0]['state']='running'
        self.manager.automation.change(self.root,interrupted)
        restarted=Manager(self.root)
        result=restarted.automation.status(self.root)
        self.assertEqual(result['state'],'paused');self.assertIsNone(restarted.automation.thread)
        restarted.close()

    def test_second_process_cannot_edit_active_queue(self):
        item=self.add()
        with ProjectLock(Path(self.root)/'.automation'):
            with self.assertRaises(Conflict):
                Manager(self.root).automation.remove_or_retry(self.root,item['id'])

    def test_watch_manual_download_records_and_preserves_existing(self):
        self.add()
        def done(project,stop):project.update('video',state='complete',message='검증 완료')
        def chat(project,stop):project.update('chat',state='empty',message='제공 없음')
        with patch('archive.jobs.video.download',done), patch('archive.jobs.chat.collect',chat):
            self.manager.start(self.root,'1','720p','all')
            self.manager.job.thread.join(3);self.manager.job.report_thread.join(3)
        ids=self.manager.reports.list(self.root,'1')
        value=self.manager.reports.snapshot(self.root,'1',ids[0]['id'])
        self.assertEqual(value['payload']['stages'][0]['state'],'complete')
        report_schema.validate(value['payload'])


    def test_full_pipeline_with_real_manager_and_simulated_engines(self):
        from contextlib import ExitStack
        from archive import speech_media, speech_store, context_job
        self.add('1', {'mode':'analysis'})
        calls=[]
        def video(project,stop):
            (project.path/'original.mp4').write_bytes(b'original-video')
            project.update('video',state='complete',message='검증 완료',assets={'original':'original.mp4','playback':'original.mp4'},verification={'duration':5})
        def chat(project,stop):
            save_json(project.path/'exports/summary.json',{'status':'현재 제공된 채팅 없음','messages':0})
            (project.path/'exports/chat.jsonl').write_bytes(b'')
            project.update('chat',state='empty',message='제공 없음',assets={'jsonl':'exports/chat.jsonl'})
        def extract(path,data,track,stop,lock,update):
            calls.append('audio')
            return {'file':'audio/source.wav','duration_ms':5000,'sha256':'test','source':speech_media.identity(path/'original.mp4',path)}
        def transcribe(path,data,language,stop,lock,update,input_audio=None,raw_audio=None,options=None):
            calls.append('transcribe')
            self.assertEqual(input_audio['input_kind'],'original')
            run={'id':'abc','language':'ko','duration_ms':5000,'processed_ms':5000,'complete':True,'segment_count':1,'chunks':[{'start_ms':0,'end_ms':5000,'file':'chunk.json'}],'audio_sha256':'test','created_at':'2026-10-18','input_kind':'original','asr_options':options}
            save_json(path/'speech/runs/abc/manifest.json',run)
            save_json(path/'speech/runs/abc/chunk.json',{'start_ms':0,'end_ms':5000,'segments':[{'id':'1','start_ms':0,'end_ms':1000,'text':'검증용 대사'}]})
            update(run='abc',audio=input_audio)
        def summary(job):
            try:
                calls.append('summary');job.update(state='complete',message='모의 요약 완료')
            finally:
                job.lock.close();job.closed=True
        with ExitStack() as stack:
            for target,value in [('archive.jobs.video.download',video),('archive.jobs.chat.collect',chat),('archive.speech.media.extract',extract),('archive.speech.transcribe',transcribe),('archive.context_job.ContextJob.run',summary)]:stack.enter_context(patch(target,value))
            stack.enter_context(patch.object(self.manager,'speech_info',return_value={'tracks':[{'index':0}]}))
            stack.enter_context(patch('archive.automation_steps.ready'))
            stack.enter_context(patch('archive.context_full.prepare',return_value={'inference':None,'source':{}}))
            self.manager.automation.start(self.root)
            result=self.finish()
        self.assertEqual(result['items'][0]['state'],'complete',result['items'][0]['message'])
        self.assertEqual(calls,['audio','transcribe','summary'])
        payload=self.manager.reports.snapshot(self.root,'1',result['items'][0]['report'])['payload']
        self.assertEqual([s['stage'] for s in payload['stages']],['download','audio','transcribe','reactions','summary'])
        self.assertEqual(payload['counts']['transcript_segments'],1)
        self.assertEqual((project_path(self.root,'1')/'original.mp4').read_bytes(),b'original-video')


class ReportExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=self.tmp.name;self.manager=Manager(self.root)
        with patch('archive.report_hardware.collect',return_value=HARDWARE):
            self.report=self.manager.reports.new(self.root,'15655103')
        self.path=project_path(self.root,'15655103')
        self.file=self.path/'diagnostics/reports'/(self.report+'.json')

    def tearDown(self):self.manager.close();self.tmp.cleanup()

    def snapshot(self):
        return self.manager.reports.snapshot(self.root,'15655103',self.report)

    def test_unknown_fields_text_nonfinite_and_invalid_vod_rejected(self):
        value=self.snapshot()['payload']
        self.assertEqual(value['schema'],2)
        self.assertEqual(value['vod_id'],'15655103')
        for bad in [value|{'chat':'원문'},value|{'counts':{'transcript':'원문'}},value|{'counts':{'chat_messages':float('nan')}}]:
            with self.assertRaises(ValueError):report_schema.validate(bad)
        for vod in [None,15655103,'0','../1','1a','１','https://chzzk.naver.com/video/1','9'*19]:
            with self.subTest(vod=vod),self.assertRaises(ValueError):
                report_schema.validate(value|{'vod_id':vod})
        report_schema.validate(value|{'vod_id':'999999999999990001'})

    def test_legacy_copy_adds_vod_without_overwriting_file(self):
        saved=json.loads(self.file.read_text())
        saved['payload'].pop('vod_id')
        saved['payload'].update(schema=1,policy='2026-10-18.1')
        saved['payload']['stages']=[dict(stage='transcribe',state='running',seconds=3,error_code='none')]
        save_json(self.file,saved)
        original=self.file.read_bytes()
        copy=self.snapshot()['payload']
        self.assertEqual(copy['vod_id'],'15655103')
        self.assertEqual(copy['schema'],2)
        self.assertEqual(copy['stages'][0]['state'],'paused')
        self.assertIsNone(copy['stages'][0]['seconds'])
        self.assertEqual(self.file.read_bytes(),original)

    def test_mismatched_vod_and_unknown_policy_do_not_get_relabelled(self):
        saved=json.loads(self.file.read_text())
        saved['payload']['vod_id']='2';save_json(self.file,saved)
        with self.assertRaises(ValueError):self.snapshot()
        saved['payload'].update(schema=1,policy='unknown')
        saved['payload'].pop('vod_id');save_json(self.file,saved)
        with self.assertRaises(ValueError):self.snapshot()

    def test_local_details_are_not_in_export_and_snapshot_is_independent(self):
        self.manager.reports.edit(self.path,self.report,lambda v:v['details'].append({'stage':'download','message':'/Users/개인/secret token=ABC 채팅원문'}))
        snapshot=self.snapshot()
        public=json.dumps(snapshot['payload'],ensure_ascii=False)
        self.assertIn('개인',json.dumps(snapshot,ensure_ascii=False))
        self.assertNotIn('개인',public);self.assertNotIn('ABC',public)
        self.manager.reports.edit(self.path,self.report,lambda v:v['payload']['counts'].update(chat_messages=999))
        self.assertNotIn('chat_messages',snapshot['payload']['counts'])

    def test_same_vod_keeps_each_execution_hardware_and_time(self):
        other=HARDWARE|{'os':'Windows','architecture':'AMD64','cpu':'비교용 CPU','gpu':'비교용 GPU'}
        with patch('archive.report_hardware.collect',return_value=other):
            report2=self.manager.reports.new(self.root,'15655103')
        for report,seconds in [(self.report,120),(report2,240)]:
            self.manager.reports.edit(self.path,report,lambda v,s=seconds:v['payload']['stages'].append(dict(stage='transcribe',state='complete',seconds=s,error_code='none')))
        first=self.snapshot()['payload']
        second=self.manager.reports.snapshot(self.root,'15655103',report2)['payload']
        self.assertEqual(first['vod_id'],second['vod_id'])
        self.assertNotEqual(first['report_id'],second['report_id'])
        self.assertEqual(first['hardware'],HARDWARE);self.assertEqual(second['hardware'],other)
        self.assertEqual([first['stages'][0]['seconds'],second['stages'][0]['seconds']],[120,240])


if __name__=='__main__':unittest.main()
