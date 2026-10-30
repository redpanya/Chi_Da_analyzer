import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from archive import speech_media,speech_store,voice_store,analysis_store,context_background
from archive.jobs import Manager
from archive.storage import create_or_load,ProjectLock,save_json,load_project,Conflict,stamp
from archive.studio_jobs import local,run_file

class StudioJobs(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.path=self.root/'vod-1';self.path.mkdir()
        meta={'id':'1','title':'독립 검사','channel':'검사','duration':4,'formats':[{'id':'test'}]}
        with ProjectLock(self.path):data=create_or_load(self.path,meta,'test')
        (self.path/'media').mkdir();self.file=self.path/'media/original.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=4','-f','lavfi','-i','sine=duration=4','-c:v','libx264','-c:a','aac',str(self.file)],check=True)
        data['tasks']['video'].update(state='complete',verification={'duration':4},assets={'original':'media/original.mp4','playback':'media/original.mp4'})
        (self.path/'exports').mkdir();chats=[{'vod_id':'1','offset_ms':v,'text':str(v),'nickname':'시청자'} for v in (0,1000,2000,3000)]
        (self.path/'exports/chat.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in chats))
        save_json(self.path/'exports/summary.json',{'status':'제공 범위 순회·경계 대조 완료','messages':4})
        data['tasks']['chat'].update(state='complete',assets={'jsonl':'exports/chat.jsonl'})
        save_json(self.path/'project.json',data)
        self.manager=Manager(self.root);self.args={'root':str(self.root),'vod_id':'1'}
    def tearDown(self):self.manager.close();self.temp.cleanup()
    def finish(self):
        self.manager.studio.job.thread.join(45)
        self.assertTrue(self.manager.studio.job.closed)
        value=self.manager.studio.job.value
        self.assertEqual(value['state'],'complete',value.get('message'))
        return value
    def test_range_audio_chat_and_parent_preserved(self):
        context_background.save(self.path,'게임 합동 방송')
        before={str(p.relative_to(self.path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.path.rglob('*') if p.is_file()}
        self.manager.studio.dispatch('scope',self.args|{'request':{'start_ms':1000,'end_ms':3000,'settings':{'steps':['audio']}}})
        with self.assertRaises(Conflict):self.manager.speech_idle()
        value=self.finish();path=Path(value['project']['path']);data=load_project(path,'1')
        self.assertEqual(data['input']['start_vod_ms'],1000)
        self.assertEqual(context_background.read(path),'게임 합동 방송')
        self.assertEqual([r['offset_ms'] for r in analysis_store.rows(path,data)],[0,1000])
        audio=speech_store.state(path)['raw_audio'];speech_media.validate_wav(speech_media.local(path,audio['file']),2000)
        for file,digest in before.items():self.assertEqual(hashlib.sha256((self.path/file).read_bytes()).hexdigest(),digest)
        self.assertEqual(self.manager.view(str(path.parent),'1')['speech']['state'],'complete')
        checked=self.manager.studio.dispatch('clean-preview',self.args|{'run':value['id'],'mode':'delete'})
        with ProjectLock(path),self.assertRaises(Conflict):
            self.manager.studio.dispatch('clean',self.args|{'run':value['id'],'mode':'delete','token':checked['token']})
        from archive.deletion import trash_path
        # Windows의 실제 휴지통 API로 열린 잠금 핸들과의 호환성을 확인한다.
        trash = trash_path if os.name == 'nt' else lambda f:f.rename(self.root/'trashed-range')
        with patch('archive.studio_maintenance.trash_path',side_effect=trash):
            self.manager.studio.dispatch('clean',self.args|{'run':value['id'],'mode':'delete','token':checked['token']})
        self.assertTrue(self.file.exists());self.assertFalse(path.exists())
    def test_copy_transcript_and_manual_speaker(self):
        data=load_project(self.path,'1')
        with ProjectLock(self.path) as lock:audio=speech_media.extract(self.path,data,1,threading.Event(),lock,lambda **v:None)
        id='a'*32;voice='b'*32;folder=speech_media.local(self.path,'runs/'+id);folder.mkdir(parents=True)
        rows=[{'id':'r1','start_ms':500,'end_ms':1500,'text':'교정 전'},{'id':'r2','start_ms':2000,'end_ms':3500,'text':'둘째 발화'}]
        save_json(folder/'00000.json',{'start_ms':0,'end_ms':4000,'segments':rows})
        save_json(folder/'corrections.json',{'r1':'수동 교정 보존'})
        save_json(folder/'manifest.json',{'id':id,'created_at':stamp(),'duration_ms':4000,'processed_ms':4000,'complete':True,'segment_count':2,'language':'ko','model':'테스트 전사','audio_sha256':audio['sha256'],'source_audio':audio,'chunks':[{'file':'00000.json','start_ms':0,'end_ms':4000}]})
        speech_store.update(self.path,state='complete',audio=audio,raw_audio=audio,run=id)
        save_json(voice_store.local(self.path,f'runs/{voice}/result.json'),{'id':voice,'created_at':stamp(),'transcript_run':id,'audio_sha256':audio['sha256'],'duration_ms':4000,'speakers':{'speaker1':'A화자'},'assignments':{'r1':{'speaker':'speaker1','status':'assigned','reason':None}},'turns':[]})
        save_json(voice_store.local(self.path,f'runs/{voice}/edits.json'),{'revision':1,'names':{'speaker1':'수동 이름'},'speakers':{},'assignments':{},'history':[]})
        voice_store.update(self.path,state='complete',run=voice,runs=[voice])
        self.manager.studio.dispatch('scope',self.args|{'request':{'start_ms':1000,'end_ms':3000,'settings':{'steps':['audio','transcribe']},'selection':{'transcript_run':id,'speaker_run':voice}}})
        value=self.finish();path=Path(value['project']['path']);run=speech_store.manifest(path)
        copied=speech_store.segments(path,run);self.assertEqual([(r['start_ms'],r['end_ms']) for r in copied],[(0,500),(1000,2000)])
        self.assertEqual(copied[0]['text'],'수동 교정 보존');self.assertEqual(voice_store.rows(path)[0]['speaker_name'],'수동 이름')
        self.assertEqual(speech_store.state(self.path)['run'],id)
    def test_draft_conflict_and_paths(self):
        req={'clips':[{'title':'테스트','start_ms':0,'end_ms':1000}],'options':{'caption_x':5.5,'caption_y':-10}}
        self.manager.studio.dispatch('draft',self.args|{'request':req,'revision':0})
        saved=self.manager.studio.dispatch('info',self.args)['draft']['request']['options']
        self.assertEqual((saved['caption_x'],saved['caption_y']),(5.5,-10))
        with self.assertRaises(Conflict):self.manager.studio.dispatch('draft',self.args|{'request':req,'revision':0})
        with self.assertRaises(ValueError):run_file(self.path,'../../project')
        with self.assertRaises(ValueError):local(self.path,'../../outside')
        link=self.path/'studio/runs';link.symlink_to(self.root)
        with self.assertRaises((Conflict,ValueError)):run_file(self.path,'c'*32)
    def test_resume_outputs_and_immutable_request(self):
        request={'clips':[{'title':'x','start_ms':0,'end_ms':1000}]}
        self.manager.studio.dispatch('start',self.args|{'request':request})
        value=self.finish();out=self.manager.studio.file(self.path,value['id'],'clip-001:video');before=out.stat().st_mtime_ns
        self.manager.studio.dispatch('resume',self.args|{'run':value['id']});self.assertEqual(out.stat().st_mtime_ns,before)
        with self.assertRaises(ValueError):self.manager.studio.file(self.path,value['id'],'clip-001:../../project.json')
    def test_remote_range_uses_checked_vod_url(self):
        from archive.range_jobs import validate
        request=validate({'start_ms':0,'end_ms':1000,'settings':{'steps':[]}},None,load_project(self.path,'1'),remote=True)
        self.assertEqual(request['settings']['steps'],[])
        with self.assertRaises(ValueError):validate({'start_ms':0,'end_ms':1000,'settings':{'steps':['context']}},None,load_project(self.path,'1'),remote=True)

    def test_image_font_draft_restore_and_original_preserved(self):
        import base64,io
        from PIL import Image
        raw=io.BytesIO();Image.new('RGBA',(24,16),(240,40,70,180)).save(raw,format='PNG')
        before=self.file.read_bytes()
        asset=self.manager.studio.dispatch('image-add',self.args|{'png':base64.b64encode(raw.getvalue()).decode(),'name':'테스트.png'})
        preview=self.manager.studio.dispatch('image-preview',self.args|{'asset':asset['asset']})
        self.assertEqual((preview['width_px'],preview['height_px']),(24,16))
        self.assertTrue(preview['png'])
        image={k:asset[k] for k in ('asset','name')}|dict(x=20,y=30,width=40,opacity=60)
        req={'clips':[{'title':'테스트','start_ms':0,'end_ms':1000}],'options':{'style':'point','font':'auto','image':image}}
        self.manager.studio.dispatch('draft',self.args|{'request':req,'revision':0})
        o=self.manager.studio.dispatch('info',self.args)['draft']['request']['options']
        self.assertEqual(o['image'],image);self.assertEqual(o['style'],'point');self.assertEqual(o['font'],'auto')
        self.manager.studio.dispatch('draft',self.args|{'request':dict(req,options=dict(req['options'],image=None)),'revision':1})
        self.assertEqual(len(list((self.path/'studio/drafts').glob('*.json'))),1)
        self.assertTrue((self.path/'studio/images'/(image['asset']+'.png')).exists())
        self.assertEqual(before,self.file.read_bytes())

if __name__=='__main__':unittest.main()
