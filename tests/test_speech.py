"""음성 시간축, 체크포인트, 원본·교정 보존과 API 경계 검사."""
from array import array
from http.client import HTTPConnection
import json
import io
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import urlsplit, urlencode
import wave

from archive import speech, speech_media as media, speech_store as store, speech_model as model
from archive.jobs import Manager
from archive.server import make_server
from archive.source import Cancelled
from archive.storage import Conflict, ProjectLock, create_or_load, save_json, read_json
from test_archive import metadata


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='음성 검증 ')
        self.root = Path(self.temp.name)
        self.path = self.root / 'vod-1'
        # 이 모음은 저장·복구 계약을 검사한다. 실제 발화 창은 별도 품질 테스트에서 검사한다.
        def recognize(binary, model_file, chunk, folder, index, duration, language, vad, stop, lock, options=None):
            prefix=folder/f'{index:05d}-raw'
            media.process([binary,'-f',str(chunk),'-of',str(prefix)],folder/f'{index:05d}-engine.log',stop,lock)
            return store.read_engine_output(prefix.with_suffix('.json'))
        for mock in [patch.object(speech.speech_vad,'prepare',return_value=self.root/'vad'),
                     patch.object(speech.speech_recognition,'recognize',side_effect=recognize)]:
            mock.start();self.addCleanup(mock.stop)
        with ProjectLock(self.path):
            self.data = create_or_load(self.path, metadata(), '360p')
        (self.path / 'media').mkdir()
        self.video = self.path / 'media/playback.mp4'
        self.video.write_bytes(b'original-media')
        self.data['tasks']['video'].update(state='complete', assets={'playback': 'media/playback.mp4'})
        save_json(self.path / 'project.json', self.data)

    def tearDown(self):
        self.temp.cleanup()

    def audio(self, ms=2500, silence=False):
        file = media.local(self.path, 'audio-test/source.wav'); file.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(file), 'wb') as out:
            out.setparams((1, 2, media.RATE, 0, 'NONE', 'not compressed'))
            out.writeframes(array('h', [0 if silence else 1000] * (ms * 16)).tobytes())
        value = {'file': 'audio-test/source.wav', 'duration_ms': ms, 'track': 1,
                 'source': media.identity(self.video, self.path), 'sha256': model.digest(file)}
        store.update(self.path, audio=value)
        return file

    def fake_engine(self, args, log, stop, lock):
        output = Path(args[args.index('-of') + 1]).with_suffix('.json')
        with wave.open(args[args.index('-f') + 1], 'rb') as audio:
            ms = audio.getnframes() * 1000 // audio.getframerate()
        save_json(output, {'transcription': [{'offsets': {'from': 0, 'to': ms}, 'text': '검증 문장'}]})

    def transcribe(self, stop=None, callback=None):
        with ProjectLock(self.path) as lock, patch.object(model, 'verify', return_value=self.root / 'model'), patch.object(model, 'engine_version', return_value=('검증 엔진', 'test')), patch.object(media, 'process', side_effect=callback or self.fake_engine), patch.object(store, 'CHUNK_MS', 1000):
            speech.transcribe(self.path, self.data, 'ko', stop or threading.Event(), lock, lambda **v: store.update(self.path, **v))

    def test_offsets_clipping_and_invalid_engine_output(self):
        raw = {'transcription': [{'offsets': {'from': 100, 'to': 1050}, 'text': ' 확인 '}]}
        rows = store.normalize(raw, 300000, 301000, 1)
        self.assertEqual((rows[0]['start_ms'], rows[0]['end_ms']), (300100, 301000))
        self.assertTrue(rows[0]['boundary_review'])
        self.assertTrue(rows[0]['timing_adjusted'])
        padded = store.normalize({'transcription': [{'offsets': {'from': 273940, 'to': 303900}, 'text': '패딩 검증'}]}, 1800000, 2100000, 6)
        self.assertEqual(padded[0]['end_ms'], 2100000)
        self.assertTrue(padded[0]['timing_adjusted'])
        for bad in ({}, {'transcription': [{'offsets': {'from': -1, 'to': 2}, 'text': 'x'}]}, {'transcription': [{'offsets': {'from': 0, 'to': float('nan')}, 'text': 'x'}]}):
            with self.assertRaises(ValueError): store.normalize(bad, 0, 1000, 0)
        with self.assertRaisesRegex(ValueError, '겹칩니다'):
            store.normalize({'transcription': raw['transcription'] * 2}, 0, 2000, 0)

    def test_resume_keeps_checkpoint_and_full_range(self):
        self.audio(); before = self.video.read_bytes(); stop = threading.Event(); calls=[]
        def interrupted(*args):
            calls.append(1)
            if len(calls)==2: stop.set(); raise Cancelled()
            self.fake_engine(*args)
        with self.assertRaises(Cancelled): self.transcribe(stop, interrupted)
        run=store.manifest(self.path); self.assertEqual(run['processed_ms'],1000); self.assertFalse(run['complete'])
        checkpoint=media.local(self.path,f"runs/{run['id']}/00000.json"); saved=checkpoint.read_bytes()
        self.transcribe()
        run=store.manifest(self.path); rows=store.segments(self.path,run)
        self.assertTrue(run['complete']);self.assertEqual(run['processed_ms'],2500)
        self.assertEqual([(r['start_ms'],r['end_ms']) for r in rows],[(0,1000),(1000,2000),(2000,2500)])
        self.assertEqual(checkpoint.read_bytes(),saved);self.assertEqual(self.video.read_bytes(),before)

    def test_invalid_engine_utf8_marks_only_affected_utterance(self):
        self.audio(ms=1000)
        payload = json.dumps({'transcription': [
            {'offsets': {'from': 0, 'to': 400}, 'text': '정상 한국어 👹'},
            {'offsets': {'from': 400, 'to': 700}, 'text': 'BROKEN'},
            {'offsets': {'from': 700, 'to': 1000}, 'text': '다음 문장'}]}, ensure_ascii=False).encode().replace(b'BROKEN', b'\xeb\x8a\x90\xeb')
        def engine(args, *_):
            Path(args[args.index('-of') + 1]).with_suffix('.json').write_bytes(payload)
        self.transcribe(callback=engine)
        run = store.manifest(self.path); rows = store.segments(self.path, run)
        self.assertTrue(run['complete'])
        self.assertEqual([r['text'] for r in rows], ['정상 한국어 👹', '[문자 인식 오류 · 원음 확인 필요]', '다음 문장'])
        self.assertEqual([r.get('encoding_review', False) for r in rows], [False, True, False])
        self.assertEqual((rows[1]['start_ms'], rows[1]['end_ms']), (400, 700))
        self.assertEqual(run['chunks'][0]['encoding_review_count'], 1)
        raw = media.local(self.path, f"runs/{run['id']}/00000-raw.json")
        self.assertEqual(raw.read_bytes(), payload)
        with self.assertRaises(UnicodeDecodeError): read_json(raw)
        exported = read_json(media.local(self.path, store.state(self.path)['exports']['json']))
        self.assertTrue(exported['segments'][1]['encoding_review'])
        store.correct(self.path, run['id'], rows[1]['id'], '원음 확인 후 교정')
        corrected = store.result(self.path)['items'][1]
        self.assertTrue(corrected['corrected']); self.assertEqual(corrected['text'], '원음 확인 후 교정')
        self.assertEqual(raw.read_bytes(), payload)

    def test_engine_metadata_and_json_corruption_still_block_checkpoint(self):
        self.audio(ms=1000)
        for payload in (b'{"model":"\xeb", "transcription":[]}', b'{"transcription":[', b'[]'):
            with self.subTest(payload=payload):
                def engine(args, *_):
                    Path(args[args.index('-of') + 1]).with_suffix('.json').write_bytes(payload)
                with self.assertRaisesRegex(ValueError, '전사 엔진 출력'):
                    self.transcribe(callback=engine)
                self.assertEqual(store.manifest(self.path)['processed_ms'], 0)

    def test_engine_output_symlink_and_invalid_unicode_escapes(self):
        file = self.root / 'engine.json'
        file.symlink_to(self.video)
        with self.assertRaisesRegex(ValueError, '연결 파일'): store.read_engine_output(file)
        file.unlink()
        file.write_bytes(b'{"transcription":[{"text":"\\ud800","offsets":{"from":0,"to":500}}]}')
        rows = store.normalize(store.read_engine_output(file), 0, 1000, 0)
        self.assertTrue(rows[0]['encoding_review'])

    def test_silence_is_not_failed_recognition(self):
        self.audio(silence=True);self.transcribe(callback=lambda *a:self.fail('무음은 엔진에 보내지 않음'))
        run=store.manifest(self.path);self.assertEqual({c['status'] for c in run['chunks']},{'silence'})
        self.assertTrue(run['complete']);self.assertEqual(run['segment_count'],0)
        # 별도 트랙의 소리가 있지만 텍스트가 없는 조각은 무음으로 확정하지 않는다.
        self.audio(silence=False)
        def empty(args,*_):save_json(Path(args[args.index('-of')+1]).with_suffix('.json'),{'transcription':[]})
        self.transcribe(callback=empty)
        self.assertEqual({c['status'] for c in store.manifest(self.path)['chunks']},{'unrecognized'})

    def test_corrections_originals_exports_and_atomic_failure(self):
        self.audio();self.transcribe();run=store.manifest(self.path);row=store.result(self.path)['items'][0]
        raw=media.local(self.path,f"runs/{run['id']}/00000-raw.json").read_bytes()
        store.correct(self.path,run['id'],row['id'],'=검증 교정')
        correction=media.local(self.path,f"runs/{run['id']}/corrections.json");before=correction.read_bytes()
        with patch('archive.storage.os.replace',side_effect=OSError('공간 부족')):
            with self.assertRaises(OSError):store.correct(self.path,run['id'],row['id'],'저장 실패')
        self.assertEqual(correction.read_bytes(),before)
        exports=store.export(self.path)
        csv=media.local(self.path,exports['csv']).read_text(encoding='utf-8-sig');self.assertIn("'=검증 교정",csv)
        values=read_json(media.local(self.path,exports['json']));self.assertEqual(values['segments'][0]['original_text'],'검증 문장')
        self.assertEqual(media.local(self.path,f"runs/{run['id']}/00000-raw.json").read_bytes(),raw)
        with self.assertRaises(ValueError):store.correct(self.path,'다른 실행',row['id'],'오염')
        store.correct(self.path,run['id'],row['id'],None)
        self.assertFalse(store.result(self.path)['items'][0]['corrected'])

    def test_changed_audio_and_invalid_checkpoint_are_not_reused(self):
        file=self.audio();self.transcribe();old=store.manifest(self.path)
        with file.open('r+b') as out:out.seek(100);out.write(b'xx')
        with self.assertRaisesRegex(ValueError,'변경'):self.transcribe()
        self.audio(ms=3000);self.transcribe();new=store.manifest(self.path)
        self.assertNotEqual(old['id'],new['id']);self.assertTrue(media.local(self.path,f"runs/{old['id']}/manifest.json").exists())
        new['chunks'][1]['start_ms']+=1
        with self.assertRaisesRegex(ValueError,'누락 또는 중복'):store.segments(self.path,new)

    def test_path_boundary_and_corrupt_speech_does_not_break_download_view(self):
        with self.assertRaises(ValueError):media.local(self.path,'../../outside')
        folder=self.path/'speech';folder.mkdir();(folder/'state.json').write_text('{bad')
        value=Manager(self.root).view(str(self.root),'1')
        self.assertEqual(value['tasks']['video']['state'],'complete');self.assertEqual(value['speech']['state'],'error')
        (folder/'state.json').unlink();folder.rmdir();folder.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(Conflict):store.update(self.path,state='running')

    def test_global_and_project_locks_stop_and_restart(self):
        manager=Manager(self.root);entered=threading.Event()
        def worker(stop,update):entered.set();stop.wait(3);raise Cancelled()
        with patch.object(model,'prepare',side_effect=worker):
            manager.speech_start(str(self.root),'1','model');self.assertTrue(entered.wait(1))
            self.assertTrue(manager.view(str(self.root),'1')['speech']['owned'])
            for action in [lambda:manager.start(str(self.root),'2','360p','all'),lambda:manager.analyze(str(self.root),'1',{}),lambda:Manager(self.root).speech_start(str(self.root),'1','model')]:
                with self.assertRaises(Conflict):action()
            manager.speech_stop(str(self.root),'1');manager.close()
        self.assertEqual(Manager(self.root).view(str(self.root),'1')['speech']['state'],'paused')
        store.update(self.path,state='running')
        self.assertEqual(Manager(self.root).view(str(self.root),'1')['speech']['state'],'paused')

    def test_http_transcript_correction_and_audio_range(self):
        self.audio();self.transcribe();m=Manager(self.root);server,url=make_server(m);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();parsed=urlsplit(url);conn=HTTPConnection(parsed.hostname,parsed.port,timeout=5)
        try:
            conn.request('POST',parsed.path+'api/speech-result',json.dumps({'root':str(self.root),'vod_id':'1'}),{'Content-Type':'application/json'})
            response=conn.getresponse();data=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(len(data['items']),3)
            conn.request('GET',parsed.path+'file?'+urlencode({'root':str(self.root),'vod_id':'1','kind':'speech','key':'audio'}),headers={'Range':'bytes=0-43'})
            response=conn.getresponse();self.assertEqual(response.status,206);self.assertEqual(response.getheader('Content-Type'),'audio/wav');self.assertEqual(len(response.read()),44)
            conn.request('POST',parsed.path+'api/speech-start',json.dumps({'root':str(self.root),'vod_id':'1','action':'unknown'}),{'Content-Type':'application/json'})
            response=conn.getresponse();response.read();self.assertEqual(response.status,400)
        finally:conn.close();server.shutdown();server.server_close();thread.join();m.close()

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg 필요')
    def test_actual_extraction_preserves_delayed_track_and_original(self):
        file=self.path/'media/delayed.mkv'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','color=size=32x32:rate=10:duration=2','-f','lavfi','-i','sine=frequency=440:duration=1:sample_rate=16000','-filter_complex','[1:a]asetpts=PTS+0.75/TB[a]','-map','0:v','-map','[a]','-c:v','libx264','-c:a','pcm_s16le',str(file)],check=True)
        self.data['tasks']['video']['assets']['playback']='media/delayed.mkv';before=model.digest(file)
        with ProjectLock(self.path) as lock:
            value=media.extract(self.path,self.data,1,threading.Event(),lock,lambda **_:None)
            with self.assertRaises(ValueError):media.extract(self.path,self.data,7,threading.Event(),lock,lambda **_:None)
            with patch.object(media.shutil,'disk_usage',return_value=MagicMock(free=0)):
                with self.assertRaises(OSError):media.extract(self.path,self.data,1,threading.Event(),lock,lambda **_:None)
        with wave.open(str(media.local(self.path,value['file'])),'rb') as audio:
            self.assertEqual(set(audio.readframes(11200)),{0});self.assertTrue(any(audio.readframes(4000)))
        self.assertEqual(model.digest(file),before)

    def test_model_download_pause_and_verified_resume(self):
        cache=self.root/'model-cache';payload=b'known model bytes';sha=hashlib.sha256(payload).hexdigest();stop=threading.Event()
        class Response(io.BytesIO):
            def __init__(self,data,status,headers):super().__init__(data);self.status=status;self.headers=headers
        with patch.object(model.model_paths,'root',return_value=cache),patch.object(model,'SIZE',len(payload)),patch.object(model,'SHA256',sha):
            first=Response(payload[:5],200,{})
            with patch.object(model,'urlopen',return_value=first):
                with self.assertRaises(Cancelled):model.prepare(stop,lambda **_:stop.set())
            self.assertFalse(model.model_path().exists());self.assertEqual(model.model_path().with_suffix('.part').read_bytes(),payload[:5])
            with patch.object(model,'urlopen',return_value=Response(payload[5:],206,{'Content-Range':f'bytes 5-{len(payload)-1}/{len(payload)}'})) as fetch:
                model.prepare(threading.Event(),lambda **_:None)
                self.assertEqual(fetch.call_args.args[0].headers['Range'],'bytes=5-')
            self.assertEqual(model.verify().read_bytes(),payload);self.assertTrue(model.status()['ready'])

    def test_model_invalid_hash_and_symlink_rejected(self):
        cache=self.root/'cache';cache.mkdir()
        with patch.object(model.model_paths,'root',return_value=cache),patch.object(model,'SIZE',3),patch.object(model,'SHA256','wrong'):
            model.model_path().write_bytes(b'bad')
            with self.assertRaises(ValueError):model.verify()
            model.model_path().unlink();model.model_path().symlink_to(self.video)
            with self.assertRaises(ValueError):model.prepare(threading.Event(),lambda **_:None)

    def test_resume_output_symlink_cannot_overwrite_video(self):
        self.audio();self.transcribe();run=store.manifest(self.path);before=self.video.read_bytes()
        media.local(self.path,f"runs/{run['id']}/working.wav").symlink_to(self.video)
        with self.assertRaisesRegex(ValueError,'연결 파일'):self.transcribe()
        self.assertEqual(self.video.read_bytes(),before)

    def test_wav_size_limit_is_checked_before_extraction(self):
        fake={'format':{'duration':'150000','start_time':'0'},'streams':[{'codec_type':'audio','index':1}]}
        with patch.object(media,'probe',return_value=fake):
            with self.assertRaisesRegex(ValueError,'20시간'):media.info(self.path,self.data)

    def test_cancel_new_transcript_keeps_active_original_and_its_corrections(self):
        self.audio();self.transcribe();old=store.manifest(self.path);old_bytes=media.local(self.path,f"runs/{old['id']}/manifest.json").read_bytes()
        store.correct(self.path,old['id'],'00000-00000','기존 교정');original=store.state(self.path)['audio']
        separated=dict(original);file=media.local(self.path,'separations/test/speech16.wav');file.parent.mkdir(parents=True)
        shutil.copyfile(media.local(self.path,original['file']),file)
        separated.update(file='separations/test/speech16.wav',sha256=model.digest(file),input_kind='sam')
        # 다른 언어는 새 실행을 만들어야 하며, 첫 조각 실패가 활성 결과를 바꾸면 안 된다.
        with ProjectLock(self.path) as lock, patch.object(model,'verify',return_value=self.root/'model'),patch.object(model,'engine_version',return_value=('엔진','test')),patch.object(media,'process',side_effect=Cancelled()):
            with self.assertRaises(Cancelled):speech.transcribe(self.path,self.data,'en',threading.Event(),lock,lambda **v:store.update(self.path,**v),separated,original)
        self.assertEqual(store.state(self.path)['run'],old['id']);self.assertNotEqual(store.state(self.path)['pending_run'],old['id'])
        self.assertEqual(media.local(self.path,f"runs/{old['id']}/manifest.json").read_bytes(),old_bytes)
        self.assertEqual(store.result(self.path)['items'][0]['text'],'기존 교정')


if __name__=='__main__':unittest.main()
