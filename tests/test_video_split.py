"""무인코딩·다중 오디오·중단 복구·입력 경계 회귀 검사."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from archive.jobs import Manager
from archive import split_contract as contract, split_media as media
from archive import split_audio
from archive.split_jobs import Splitter
from archive.split_storage import check_volume
from archive.storage import Conflict


def packets(path):
    data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_packets', '-show_data_hash', 'sha256',
        '-show_entries', 'packet=stream_index,data_hash,pts_time', '-of', 'json', str(path)]))
    streams = {}
    for row in data['packets']:
        streams.setdefault(row['stream_index'], []).append(row['data_hash'])
    return streams


def packet_times(path, offset=0):
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_packets',
        '-show_entries','packet=stream_index,pts_time','-of','json',str(path)]))
    streams={}
    for row in data['packets']:
        streams.setdefault(row['stream_index'],[]).append(round((float(row['pts_time'])+offset)*1000))
    return streams


class VideoSplit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.source = Path(cls.fixture.name)/'한글 6개 오디오.mp4'
        args = ['ffmpeg','-v','error','-nostdin','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=8']
        for i in range(6):args += ['-f','lavfi','-i',f'sine=frequency={220+i*110}:sample_rate=48000:duration=8']
        args += ['-map','0:v']
        for i in range(6): args += ['-map',f'{i+1}:a']
        args += ['-c:v','libx264','-g','30','-bf','2','-c:a','aac']
        for i in range(6): args += [f'-metadata:s:a:{i}',f'handler_name=Track{i+1}',f'-disposition:a:{i}','default' if i == 0 else '0']
        subprocess.run([*args,str(cls.source)],check=True)
        cls.digest = hashlib.sha256(cls.source.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls): cls.fixture.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.manager = Manager(self.root/'unmounted-library')
        self.manager.splitter = Splitter(self.manager,self.root/'state')
        self.splitter = self.manager.splitter
        self.registered = self.splitter.dispatch('register',{'path':str(self.source)})

    def tearDown(self):
        self.manager.close(); self.temp.cleanup()
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),self.digest)

    def finish(self):
        self.splitter.job.thread.join(30)
        self.assertTrue(self.splitter.job.closed)
        return self.splitter.state(self.splitter.job.value['id'])

    def plan(self):
        self.splitter.dispatch('plan',{'source_id':self.registered['source_id'],'points':[5.2,2.4]})
        result=self.finish(); self.assertEqual(result['state'],'ready',result['message'])
        return result

    def test_copy_every_packet_and_track(self):
        result=self.plan();self.assertEqual([c['actual'] for c in result['plan']['cuts']],[3,6])
        self.splitter.dispatch('start',{'id':result['id'],'folder':str(self.root)})
        result=self.finish();self.assertEqual(result['state'],'complete',result['message'])
        expected=packets(self.source);actual={i:[] for i in expected}
        for index,record in result['outputs'].items():
            self.assertEqual(record['audio_tracks'],6)
            file=self.splitter.media_file(run=result['id'],index=index)
            for i,rows in packets(file).items():actual[i].extend(rows)
        self.assertEqual(expected,actual)
        self.assertEqual(result['command'][result['command'].index('-c')+1],'copy')
        self.assertFalse((self.root/'unmounted-library').exists())

    def test_cancel_resume_keeps_completed_files(self):
        result=self.plan();original=media.verify
        def interrupted(*args):
            checked=original(*args);self.splitter.job.stop.set();return checked
        with patch('archive.split_render.media.verify',side_effect=interrupted):
            self.splitter.dispatch('start',{'id':result['id'],'folder':str(self.root)})
            result=self.finish()
        self.assertEqual(result['state'],'paused');self.assertEqual(len(result['outputs']),1)
        kept=self.splitter.media_file(run=result['id'],index='0');before=contract.identity(kept)
        second=Splitter(self.manager,self.root/'state');self.manager.splitter=second;self.splitter=second
        self.splitter.dispatch('resume',{'id':result['id']});result=self.finish()
        self.assertEqual(result['state'],'complete',result['message']);self.assertEqual(contract.identity(kept),before)
        expected=packets(self.source);actual={i:[] for i in expected}
        for i in range(3):
            for stream,rows in packets(self.splitter.media_file(run=result['id'],index=str(i))).items():actual[stream].extend(rows)
        self.assertEqual(expected,actual)

    def test_selected_tracks_packet_copy_and_resume(self):
        selected={'mode':'selected','tracks':[6,3]}
        self.splitter.dispatch('plan',{'source_id':self.registered['source_id'],'points':[2.4,5.2], 'audio_selection':selected})
        result=self.finish()
        self.assertEqual(result['audio_selection']['tracks'],[3,6])
        original=media.verify
        def interrupted(*args):
            checked=original(*args);self.splitter.job.stop.set();return checked
        with patch('archive.split_render.media.verify',side_effect=interrupted):
            self.splitter.dispatch('start',{'id':result['id'],'folder':str(self.root)})
            result=self.finish()
        self.assertEqual(result['state'],'paused',result['message'])
        kept=self.splitter.media_file(run=result['id'],index='0');before=contract.identity(kept)
        self.splitter.close()
        self.splitter=Splitter(self.manager,self.root/'state');self.manager.splitter=self.splitter
        self.splitter.dispatch('resume',{'id':result['id']})
        result=self.finish();self.assertEqual(result['state'],'complete',result['message'])
        self.assertEqual(contract.identity(kept),before)
        expected=packets(self.source);actual={0:[],1:[],2:[]}
        for index,record in result['outputs'].items():
            self.assertEqual(record['audio_tracks'],2)
            self.assertEqual(record['source_stream_indices'],[0,3,6])
            for stream,rows in packets(self.splitter.media_file(run=result['id'],index=index)).items():actual[stream].extend(rows)
        self.assertEqual(actual,{0:expected[0],1:expected[3],2:expected[6]})

    def test_audio_selection_validation_and_draft(self):
        source=self.registered['source']
        for value in ({'mode':'other'}, {'mode':'selected','tracks':[]}, {'mode':'selected','tracks':[0]},
                      {'mode':'selected','tracks':[99]}, {'mode':'selected','tracks':[True]}, {'mode':'selected','tracks':[2,2]}):
            with self.subTest(value=value), self.assertRaises(ValueError):split_audio.selection(source,value)
        draft={'source_id':self.registered['source_id'],'points':[2], 'audio_selection':{'mode':'selected','tracks':[4]}}
        saved=self.splitter.dispatch('draft-save',{'revision':0,'draft':draft})
        self.assertEqual(saved['draft']['audio_selection'],{'mode':'selected','tracks':[4]})
        self.assertEqual(self.splitter.dispatch('draft-get',{})['draft']['audio_selection'],saved['draft']['audio_selection'])

    def test_preview_contains_only_requested_audio_without_reencoding(self):
        source_id=self.registered['source_id']
        result=self.splitter.dispatch('audio-preview',{'source_id':source_id,'track':5,'at':2})
        file=self.splitter.audio_preview.file(result['id'])
        probe=media.probe(file,threading.Event())
        self.assertEqual([s['codec_type'] for s in probe['streams']],['audio'])
        self.assertEqual(packets(file)[0],packets(self.source)[5])
        cached=self.splitter.dispatch('audio-preview',{'source_id':source_id,'track':5,'at':3})
        self.assertEqual(result,cached)
        for track,at in ((0,2),(True,2),(9,2),(1,-1),(1,float('nan')),(1,9)):
            with self.assertRaises(ValueError):self.splitter.dispatch('audio-preview',{'source_id':source_id,'track':track,'at':at})
        with self.assertRaises(ValueError):self.splitter.audio_preview.file('../original')
        self.splitter.audio_preview.close();self.assertFalse(file.exists())

    def test_preview_seek_uses_source_timeline(self):
        src=self.root/'긴 영상.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=160x90:rate=30:duration=72',
                        '-f','lavfi','-i','sine=frequency=770:duration=72:sample_rate=48000',
                        '-c:v','libx264','-g','30','-c:a','aac','-output_ts_offset','5',str(src)],check=True)
        registered=self.splitter.dispatch('register',{'path':str(src)})
        result=self.splitter.dispatch('audio-preview',{'source_id':registered['source_id'],'track':1,'at':65})
        self.assertEqual(result['start'],60)
        out=self.splitter.audio_preview.file(result['id']);probe=media.probe(out,threading.Event())
        self.assertLess(float(probe['streams'][0]['start_time']),.025)
        original=packets(src)[1];copied=packets(out)[0]
        self.assertTrue(copied);self.assertTrue(all(p in original for p in copied))

    def test_invalid_time_source_and_output(self):
        for values in ([0],[8],[float('nan')],[True],[1,1],[],list(range(1,203))):
            with self.assertRaises(ValueError):contract.points(values,8)
        with self.assertRaises((ValueError,FileNotFoundError)):media.inspect('https://example.com/file.mp4',threading.Event())
        link=self.root/'link.mp4';link.symlink_to(self.source)
        with self.assertRaises(ValueError):media.inspect(str(link),threading.Event())
        with self.assertRaises(ValueError):contract.inside(self.root,'../original.mp4')
        with self.assertRaises(ValueError):self.splitter.file('../source')
        result=self.plan()
        with self.assertRaises(KeyError):self.splitter.media_file(run=result['id'],index='0')
        with self.assertRaises((ValueError,FileNotFoundError)):self.splitter.dispatch('start',{'id':result['id'],'folder':str(self.root/'absent')})

    def test_colliding_keyframe_and_job_lock(self):
        source=self.registered['source']
        with self.assertRaises(ValueError):media.boundaries(source,[2.1,2.2],threading.Event(),lambda **v:None)
        result=self.plan()
        self.splitter.job.closed=False
        try:
            with self.assertRaises(Conflict):self.manager.speech_idle()
            with self.assertRaises(Conflict):self.manager.start(str(self.root),'1',None,'all')
            with self.assertRaises(Conflict):self.manager.deletion_preview(str(self.root),'1')
        finally:self.splitter.job.closed=True
        changed=dict(source);changed['identity']={**source['identity'],'mtime_ns':0}
        with self.assertRaises(ValueError):contract.unchanged(changed)

    def test_offset_and_video_only_inputs(self):
        for audio in (True, False):
            with self.subTest(audio=audio):
                src=self.root/f'offset-{audio}.mp4'
                subprocess.run(['ffmpeg','-v','error','-i',str(self.source),'-map','0' if audio else '0:v',
                                '-c','copy','-output_ts_offset','5',str(src)],check=True)
                registered=self.splitter.dispatch('register',{'path':str(src)})
                result=self.splitter.dispatch('plan',{'source_id':registered['source_id'],'points':[3,5.2]})
                result=self.finish();self.assertEqual(result['state'],'ready')
                self.splitter.dispatch('start',{'id':result['id'],'folder':str(self.root)})
                result=self.finish();self.assertEqual(result['state'],'complete',result['message'])
                expected=packets(src);actual={i:[] for i in expected}
                times=packet_times(src,-registered['source']['origin']);actual_times={i:[] for i in times}
                for i in range(3):
                    file=self.splitter.media_file(run=result['id'],index=str(i))
                    for stream,rows in packets(file).items():actual[stream].extend(rows)
                    for stream,rows in packet_times(file,result['plan']['parts'][i]['start']).items():actual_times[stream].extend(rows)
                self.assertEqual(actual,expected)
                self.assertEqual(actual_times,times)
                self.assertTrue(all(r['audio_tracks']==(6 if audio else 0) for r in result['outputs'].values()))

    def test_fat32_and_low_space_preserve_source(self):
        with patch('archive.split_storage.filesystem',return_value='ms-dos fat32'):
            with self.assertRaisesRegex(ValueError,'4GB'):check_volume(self.root,5*1024**3)
        with patch('archive.split_storage.filesystem',return_value='exfat'):
            self.assertEqual(check_volume(self.root,5*1024**3),'exfat')
        result=self.plan()
        from collections import namedtuple
        usage=namedtuple('usage','total used free')(1024,1024,0)
        with patch('archive.split_render.shutil.disk_usage',return_value=usage):
            self.splitter.dispatch('start',{'id':result['id'],'folder':str(self.root)})
            result=self.finish()
        self.assertEqual(result['state'],'error');self.assertFalse(result['outputs'])
        self.assertIn('공간',result['message'])


if __name__=='__main__':unittest.main()
