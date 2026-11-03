"""같은 길이의 교체 영상에 앞당겨진 대사가 있을 때 실제 자막 출력까지 확인한다."""
from array import array
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import patch

from archive import caption_sync, speech_media
from archive.jobs import Manager
from archive.storage import ProjectLock, create_or_load, save_json


class CaptionSyncTests(unittest.TestCase):
    def test_replaced_video_preview_burn_and_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = root/'vod-1'
            with ProjectLock(path):
                data = create_or_load(path, {'id':'1','title':'자막 보정 검사','duration':32,
                                             'formats':[{'id':'new'}]}, 'new')
            wav = path/'speech/audio-old/source.wav'
            wav.parent.mkdir(parents=True)
            rng = random.Random(41)
            with wave.open(str(wav), 'wb') as out:
                out.setparams((1,2,16000,0,'NONE',''))
                for i in range(32*50):
                    amp = rng.randint(50,16000)
                    samples = ([amp]*20 + [-amp]*20)*8 if i%3 else [0]*320
                    out.writeframes(array('h', samples).tobytes())
            (path/'media').mkdir()
            video = path/'media/new.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=160x90:r=10:d=32',
                            '-ss','1.2','-i',str(wav),'-af','apad','-t','32','-c:v','libx264',
                            '-c:a','aac',str(video)], check=True)
            previous = {'file':'media/removed.mp4','bytes':123,'mtime_ns':1000}
            current = speech_media.identity(video,path)
            data['tasks']['video'].update(state='complete',assets={'playback':'media/new.mp4'},
                                          verification={'duration':32})
            data['analysis_video'] = dict(source=previous,playback=current,duration=32)
            data['input'] = {'kind':'range','start_vod_ms':900000}
            save_json(path/'project.json',data)
            audio = dict(file='audio-old/source.wav',duration_ms=32000,source=previous,sha256='test')
            run_id = 'a'*32
            folder = path/'speech/runs'/run_id
            rows = [{'id':'r','start_ms':4200,'end_ms':5000,'text':'원문'}]
            save_json(folder/'00000.json',dict(start_ms=0,end_ms=32000,segments=rows))
            save_json(folder/'manifest.json',dict(id=run_id,created_at='2026',complete=True,
                duration_ms=32000,processed_ms=32000,segment_count=1,source_audio=audio,audio_sha256='test',
                chunks=[dict(file='00000.json',start_ms=0,end_ms=32000)]))
            save_json(folder/'corrections.json',{'r':'사용자 교정'})
            save_json(path/'speech/state.json',dict(run=run_id,state='complete',audio=audio))
            before = {f:f.read_bytes() for f in folder.iterdir()}
            manager = Manager(root)
            self.addCleanup(manager.close)
            args = dict(root=str(root),vod_id='1')
            selection = dict(transcript_run=run_id,speaker_run=None)
            preview = manager.studio.dispatch('captions',args|{'selection':selection})
            row = preview['rows'][0]
            self.assertEqual((row['start_ms'],row['end_ms'],row['text']),(903000,903800,'사용자 교정'))
            self.assertIn('1.20초 앞으로',preview['sync_message'])
            speech = manager.speech_result(str(root),'1')['items'][0]
            self.assertEqual((speech['start_ms'],speech['video_start_ms']),(4200,3000))
            manager.studio.dispatch('transcript-add',args|dict(run=run_id,segment='r'))
            draft = manager.studio.dispatch('info',args)['draft']['request']['clips'][0]
            self.assertEqual((draft['start_ms'],draft['end_ms']),(903000,903800))
            req = dict(clips=[dict(title='확인',start_ms=902500,end_ms=904000)],selection=selection,
                       options=dict(caption=True,sidecar=True,size='source',ratio='original'))
            job = manager.studio.dispatch('start',args|{'request':req})
            manager.studio.job.thread.join(45)
            self.assertEqual(manager.studio.job.value['state'],'complete',manager.studio.job.value['message'])
            outputs = {key:manager.studio.file(path,job['id'],'clip-001:'+key)
                       for key in ('srt','ass','video')}
            self.assertIn('00:00:00,500 --> 00:00:01,300',outputs['srt'].read_text(encoding='utf-8-sig'))
            self.assertIn('0:00:00.50,0:00:01.30',outputs['ass'].read_text(encoding='utf-8-sig'))
            def brightest(at):
                frame = subprocess.check_output(['ffmpeg','-v','error','-ss',at,'-i',str(outputs['video']),
                    '-frames:v','1','-f','rawvideo','-pix_fmt','gray','pipe:1'])
                return max(frame)
            self.assertLess(brightest('0.1'),40)
            self.assertGreater(brightest('0.8'),180)
            self.assertEqual(before,{f:f.read_bytes() for f in folder.iterdir()})
            # 같은 저장 경로의 다음 화질 교체 및 해당 화질에서 새로 추출한 원음.
            with patch.object(caption_sync,'_measure',return_value=800):
                sync = caption_sync.resolve(path,data,audio)
                self.assertEqual(sync['offset_ms'],800)
                self.assertEqual(caption_sync.interval({'start_ms':31000,'end_ms':31900},sync),(31800,32000))
                self.assertEqual(caption_sync.resolve(path,data,audio|{'playback_source':current})['offset_ms'],0)
            with patch.object(caption_sync,'_measure',return_value=None):
                sync = caption_sync.resolve(path,data,audio)
                self.assertEqual(sync['offset_ms'],0)
                self.assertIn('기존 자막 시각',sync['message'])
