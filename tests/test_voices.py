from pathlib import Path
import json
import threading
import time
import unittest
from unittest.mock import patch

import test_speech as fixture
from archive import voice_store as store, voices, speech_store, speech_media, voice_models
from archive.jobs import Manager
from archive.storage import ProjectLock, Conflict, save_json, read_json
from archive.source import Cancelled


class VoiceTests(unittest.TestCase):
    setUp = fixture.SpeechTests.setUp
    tearDown = fixture.SpeechTests.tearDown
    audio = fixture.SpeechTests.audio
    fake_engine = fixture.SpeechTests.fake_engine
    transcribe = fixture.SpeechTests.transcribe

    def prepare(self):
        self.audio(); self.transcribe()
        run = speech_store.manifest(self.path)
        rows = speech_store.segments(self.path, run)
        speakers, assignments = store.assign(rows, [{'speaker':0,'start_ms':0,'end_ms':1000},
                                                   {'speaker':1,'start_ms':1000,'end_ms':2500}], 'test')
        folder = store.local(self.path,'runs/test'); folder.mkdir(parents=True)
        save_json(folder/'result.json', {'id':'test','speakers':speakers,'assignments':assignments,
                   'duration_ms':2500,'audio_sha256':run['audio_sha256'],'transcript_run':run['id']})
        store.update(self.path, run='test', runs=['test'])
        return speakers

    def change(self, action, **kwargs):
        store.edit(self.path, 'test', store.edits(self.path,'test')['revision'], action, **kwargs)

    def test_assignment_failures_and_overlap_without_fake_confidence(self):
        rows=[{'id':'a','start_ms':0,'end_ms':2000}]
        for turns,reason in [([], 'no_voice'),([{'speaker':0,'start_ms':0,'end_ms':500}],'short'),
                              ([{'speaker':0,'start_ms':0,'end_ms':2000},{'speaker':1,'start_ms':1000,'end_ms':1800}], 'mixed')]:
            _, mapped=store.assign(rows, turns,'x'); self.assertEqual(mapped['a']['reason'],reason);self.assertIsNone(mapped['a']['speaker'])
        _, mapped=store.assign(rows,[{'speaker':0,'start_ms':0,'end_ms':1800}], 'x')
        self.assertEqual(mapped['a']['status'],'automatic');self.assertNotIn('confidence',mapped['a'])

    def test_zero_transcripts_have_detected_audio_sample(self):
        self.prepare()
        result = store.result(self.path)
        turns = [{'speaker': 0, 'start_ms': 0, 'end_ms': 400},
                 {'speaker': 1, 'start_ms': 1000, 'end_ms': 2000}]
        result['speakers'], result['assignments'] = store.assign(store.rows(self.path), turns, 'test')
        result['turns'] = turns
        save_json(store.local(self.path, 'runs/test/result.json'), result)
        speakers = store.browse(self.path)['speakers']
        self.assertEqual(speakers[0]['count'], 0)
        self.assertEqual(speakers[0]['turn_count'], 1)
        self.assertEqual(speakers[0]['sample_kind'], 'detected')
        self.assertEqual(speakers[0]['sample']['end_ms'], 400)
        self.assertEqual(speakers[1]['sample_kind'], 'transcript')

    def test_name_search_export_and_original_preservation(self):
        ids=list(self.prepare()); original={str(p):p.read_bytes() for p in (self.path/'speech').rglob('*') if p.is_file()}
        self.change('rename',speaker=ids[0],name='=김모모')
        self.assertEqual(store.browse(self.path,'김모모')['total'],1)
        self.assertEqual(speech_store.result(self.path,'김모모')['total'],1)
        store.export(self.path); exported=store.state(self.path)['exports']
        self.assertIn("'=김모모",store.local(self.path,exported['csv']).read_text(encoding='utf-8-sig'))
        self.assertIn('=김모모',store.local(self.path,exported['txt']).read_text())
        self.change('rename',speaker=ids[0],name='이름 변경')
        self.assertEqual(store.view(self.path)['exports'],{})
        self.assertIn('=김모모',store.local(self.path,exported['json']).read_text())
        self.assertEqual(original,{str(p):p.read_bytes() for p in (self.path/'speech').rglob('*') if p.is_file()})
        store.export(self.path)
        self.assertTrue(store.view(self.path)['exports'])
        speech_store.update(self.path, message='교정 변경')
        self.assertFalse(store.view(self.path)['exports'])
        self.assertEqual(Manager(self.root).voices_result(str(self.root),'1')['speakers'][0]['name'],'이름 변경')

    def test_assign_split_merge_failure_undo_and_revision_conflict(self):
        ids=list(self.prepare())
        self.change('assign',speaker=None,start_ms=0,end_ms=1000,reason='ambiguous')
        self.assertEqual(store.browse(self.path)['items'][0]['speaker_name'],'화자인식 실패')
        self.change('undo');self.assertEqual(store.browse(self.path)['items'][0]['speaker'],ids[0])
        self.change('split',start_ms=0,end_ms=1000)
        new=store.browse(self.path)['items'][0]['speaker'];self.assertNotIn(new,ids)
        self.change('merge',source=new,speaker=ids[1])
        self.assertEqual(store.browse(self.path)['items'][0]['speaker'],ids[1])
        self.assertEqual(store.browse(self.path)['items'][0]['status'],'confirmed')
        with self.assertRaises(Conflict):store.edit(self.path,'test',0,'rename',speaker=ids[0],name='경쟁 요청')
        with self.assertRaises(Conflict):store.edit(self.path,'다른 버전',0,'undo')

    def test_stale_version_and_atomic_save_failure(self):
        ids=list(self.prepare());self.change('rename',speaker=ids[0],name='보존')
        before=store.local(self.path,'runs/test/edits.json').read_bytes()
        with patch('archive.storage.os.replace',side_effect=OSError('공간 부족')):
            with self.assertRaises(OSError):self.change('rename',speaker=ids[0],name='저장 실패')
        self.assertEqual(before,store.local(self.path,'runs/test/edits.json').read_bytes())
        speech_store.update(self.path,run=None)
        self.assertTrue(store.view(self.path)['stale'])
        self.assertEqual(store.browse(self.path)['items'],[])
        with self.assertRaises(Conflict):self.change('rename',speaker=ids[0],name='오염')

    def test_boundaries_paths_and_engine_result_validation(self):
        for a,b in [(0,999),(0,300001),(-1,2000),(float('nan'),2000),(True,2000),(2000,1000),(0,6000)]:
            with self.assertRaises(ValueError):voices.validate_range(a,b,5000)
        voices.validate_range(1000,5000,5000)
        with self.assertRaises(ValueError):store.local(self.path,'../../탈출')
        (self.path/'voices').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(Conflict):store.local(self.path,'state.json')
        for turn in [{'start_ms':-1,'end_ms':100,'speaker':0},{'start_ms':0,'end_ms':9000,'speaker':0}]:
            with self.assertRaises(ValueError):voices.validate_turns([turn],5000)

    def test_cancel_preserves_previous_result_and_blocks_other_jobs(self):
        self.prepare(); before=store.local(self.path,'runs/test/result.json').read_bytes()
        manager=Manager(self.root); entered=threading.Event()
        def worker(job,*args,**kwargs):
            entered.set();job.stop.wait(5);raise Cancelled()
        with patch.object(voices.VoiceJob,'worker',worker):
            manager.voices_start(str(self.root),'1','diarize',{})
            self.assertTrue(entered.wait(2))
            with self.assertRaises(Conflict):manager.speech_start(str(self.root),'1','model')
            with self.assertRaises(Conflict):manager.start(str(self.root),'1','360p','video')
            with self.assertRaises(Conflict):manager.analyze(str(self.root),'1',{})
            with self.assertRaises(Conflict):ProjectLock(self.path)
            manager.voices_stop(str(self.root),'1');manager.voice_job.thread.join(3)
        self.assertTrue(manager.voice_job.closed)
        self.assertEqual(store.state(self.path)['run'],'test')
        self.assertEqual(store.state(self.path)['state'],'paused')
        self.assertEqual(store.local(self.path,'runs/test/result.json').read_bytes(),before)
        with ProjectLock(self.path):pass
        self.assertFalse(manager.view(str(self.root),'1')['locked'])

    def test_http_names_export_and_stem_range(self):
        from http.client import HTTPConnection
        from urllib.parse import urlsplit, urlencode
        from archive.server import make_server
        ids=list(self.prepare());m=Manager(self.root);server,url=make_server(m)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();parsed=urlsplit(url)
        conn=HTTPConnection(parsed.hostname,parsed.port,timeout=5)
        def post(action, values):
            conn.request('POST',parsed.path+'api/'+action,json.dumps({'root':str(self.root),'vod_id':'1'}|values),{'Content-Type':'application/json'})
            response=conn.getresponse();body=json.loads(response.read());self.assertEqual(response.status,200,body);return body
        try:
            post('voices-edit',{'action':'rename','options':{'run':'test','revision':0,'speaker':ids[0],'name':'김모모'}})
            self.assertEqual(post('voices-result',{'query':'김모모'})['total'],1)
            speech_before=speech_store.local(self.path,'state.json').read_bytes()
            post('speech-edit',{'action':'export'})
            self.assertTrue(m.view(str(self.root),'1')['voices']['exports'])
            self.assertEqual(speech_store.local(self.path,'state.json').read_bytes(),speech_before)
            stem=store.local(self.path,'stems/fixture/original.wav');stem.parent.mkdir(parents=True);stem.write_bytes(b'RIFF'+b'0'*100)
            save_json(stem.parent/'result.json',{'files':{'original':'stems/fixture/original.wav'}})
            store.update(self.path,stem='fixture')
            conn.request('GET',parsed.path+'file?'+urlencode({'root':str(self.root),'vod_id':'1','kind':'voices','key':'original'}),headers={'Range':'bytes=0-43'})
            response=conn.getresponse();self.assertEqual(response.status,206);self.assertEqual(response.getheader('Content-Type'),'audio/wav');self.assertEqual(len(response.read()),44)
        finally:
            conn.close();server.shutdown();server.server_close();thread.join();m.close()

    def test_restart_marks_running_paused_and_bad_m4_keeps_m3(self):
        self.prepare();store.update(self.path,state='running')
        self.assertEqual(Manager(self.root).view(str(self.root),'1')['voices']['state'],'paused')
        store.local(self.path,'state.json').write_text('{')
        self.assertEqual(Manager(self.root).view(str(self.root),'1')['voices']['state'],'error')
        self.assertEqual(speech_store.result(self.path)['total'],3)


    def test_pending_voice_run_reuses_only_same_input(self):
        self.prepare();captured=[]
        def interrupted(job,folder,*args,**kwargs):
            captured.append(folder.name);raise Cancelled()
        def completed(job,folder,*args,**kwargs):
            captured.append(folder.name);return {'turns':[{'speaker':0,'start_ms':0,'end_ms':2500}]}
        with patch.object(voices.VoiceJob,'worker',interrupted):
            voices.VoiceJob(self.path,self.data,ProjectLock(self.path),'diarize',{}).run()
        first=store.state(self.path)['pending_diarization']['id']
        self.assertEqual(store.state(self.path)['run'],'test')
        with patch.object(voices.VoiceJob,'worker',completed):
            voices.VoiceJob(self.path,self.data,ProjectLock(self.path),'diarize',{}).run()
        self.assertEqual(captured,[first,first]);self.assertIsNone(store.state(self.path)['pending_diarization'])
        self.assertIn('test',store.state(self.path)['runs'])

    def test_changed_speaker_settings_keep_old_pending_run(self):
        self.prepare();captured=[]
        def interrupted(job,folder,*args,**kwargs):
            captured.append(folder.name);(folder/'saved.txt').write_text('완료 조각 보존');raise Cancelled()
        with patch.object(voices.VoiceJob,'worker',interrupted):
            for count in (-1,2):
                voices.VoiceJob(self.path,self.data,ProjectLock(self.path),'diarize',{'speakers':count}).run()
        self.assertNotEqual(captured[0],captured[1])
        self.assertEqual(store.state(self.path)['run'],'test')
        self.assertEqual(store.local(self.path,f'runs/{captured[0]}/saved.txt').read_text(),'완료 조각 보존')

if __name__ == '__main__':unittest.main()
