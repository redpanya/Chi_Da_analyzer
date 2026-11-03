import copy
import tempfile
import threading
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from archive import studio_profiles as p, clip_contract as c, clip_render, studio_maintenance
from archive.storage import ProjectLock, save_json, Conflict

class Profiles(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name).resolve()
        self.src={'origin':5000,'duration':5000,'width':320,'height':180,'audio':True}
        self.raw={'clips':[{'id':'a','title':'가로','start_ms':5000,'end_ms':6000},
                           {'id':'b','title':'세로','start_ms':7000,'end_ms':8000,'options':{'ratio':'9:16','caption':True,'style':'box','font_size':30}}],
                  'options':{'caption':False}}
    def tearDown(self):self.temp.cleanup()
    def test_contract_and_detached_values(self):
        original=copy.deepcopy(self.raw);request=c.validate(self.raw,self.src)
        self.assertEqual(self.raw,original)
        self.assertNotIn('options',request['clips'][0])
        self.assertEqual(p.effective(request,request['clips'][1])['ratio'],'9:16')
        opts=p.effective(request,request['clips'][0]);opts['game'][0]=42
        self.assertEqual(request['options']['game'][0],0)
        for bad in [{'mode':'joined'},{'ratio':'2:3'},{'font':'/tmp/font.ttf'},{'layout':'split','face':[99,0,30,50]}]:
            data=copy.deepcopy(self.raw);data['clips'][1]['options']=bad
            with self.assertRaises(ValueError):c.validate(data,self.src)
        legacy=c.validate({'clips':self.raw['clips'][:1]},self.src)
        self.assertNotIn('options',legacy['clips'][0])
        # 사용하지 않는 공통 자막 설정은 원본 비율 개별 빠른 저장을 막지 않는다.
        fast={'clips':[self.raw['clips'][0]|{'options':{'ratio':'original','caption':False}}],
              'options':{'caption':True,'ratio':'9:16','speed':'fast','sidecar':False}}
        self.assertFalse(p.profiles(c.validate(fast,self.src))[0]['caption'])
    def test_presets_reject_assets_and_preserve_applied(self):
        opts=p.preset_options({'ratio':'9:16','caption':True,'font_size':24})
        with patch.object(p.runtime,'SUPPORT',self.path):
            saved=p.dispatch('save',{'name':'세로 자막','options':opts});id=saved['id']
            applied=copy.deepcopy(saved['presets'][0]['options'])
            with self.assertRaises(ValueError):p.preset_options({'image':None})
            with self.assertRaises(ValueError):p.preset_options({'font_size':float('nan')})
            with self.assertRaises(Exception):p.dispatch('save',{'name':'세로 자막','options':opts})
            p.dispatch('delete',{'id':id})
            self.assertEqual(p.entries(),[]);self.assertEqual(applied,opts)
            self.assertEqual(len(list((self.path/'studio-presets/deleted').glob('*.json'))),1)
    def test_mixed_ratio_caption_and_resume(self):
        source=self.path/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=5','-f','lavfi','-i','sine=frequency=440:duration=5','-c:v','libx264','-c:a','aac',str(source)],check=True)
        src=self.src|{'file':source};before=source.read_bytes()
        rows=[{'start_ms':5000,'end_ms':6000,'text':'첫 자막'},{'start_ms':7000,'end_ms':8000,'text':'둘째 자막'}]
        for mode,transition in [('separate','cut'),('joined','cut'),('joined','fade')]:
            folder=self.path/(mode+transition);folder.mkdir();raw=copy.deepcopy(self.raw);raw['options'].update(mode=mode,transition=transition)
            request=c.validate(raw,src);stop=threading.Event();completed={};progress=[];first_output=[]
            def update(**values):
                if 'progress' in values:progress.append(values['progress'])
                if 'outputs' in values and len(values['outputs'])==1:first_output.append(values.get('progress',progress[-1]))
            with ProjectLock(self.path) as lock:
                clip_render.render(folder,src,request,rows,stop,lock,update,completed)
                names=[o['assets']['video'] for o in completed.values()]
                snapshots={n:((folder/n).read_bytes(),(folder/n).stat().st_mtime_ns) for n in names}
                clip_render.render(folder,src,request,rows,stop,lock,lambda **v:None,completed)
                for n,(data,mtime) in snapshots.items():
                    self.assertEqual((folder/n).read_bytes(),data);self.assertEqual((folder/n).stat().st_mtime_ns,mtime)
            self.assertEqual(progress,sorted(progress))
            if mode=='separate':self.assertLess(first_output[0],.6)
            # 새 구간별 중간 파일도 기존 정리 화면에서 식별되며 완성 파일은 제외된다.
            manifest=folder/'manifest.json';save_json(manifest,{'id':folder.name,'kind':'start','state':'complete','outputs':completed})
            cleanup=studio_maintenance.preview(self.path,manifest,'intermediate')
            self.assertNotIn(names[0],cleanup['names'])
            self.assertTrue(cleanup['names'])
            unrelated=folder/'사용자가-놓은-자료.txt';unrelated.write_text('보존')
            with self.assertRaises(Conflict):studio_maintenance.preview(self.path,manifest,'intermediate')
            unrelated.unlink()
            expected=[(320,180),(180,320)] if mode=='separate' else [(320,180)]
            actual=[]
            for name in names:
                stream=next(v for v in clip_render.probe(folder/name)['streams'] if v['codec_type']=='video');actual.append((stream['width'],stream['height']))
            self.assertEqual(actual,expected)
            if mode=='joined':
                ass=(folder/'joined.ass').read_text(encoding='utf-8-sig')
                self.assertIn('Style: C0_Default',ass);self.assertIn('Style: C1_Default',ass)
                self.assertIn('둘째 자막',(folder/'joined.srt').read_text(encoding='utf-8-sig'))
            # 출력 프레임은 한 구간만 자막이 켜져 있어 서로 달라야 한다.
            def pixels(name,at):return subprocess.check_output(['ffmpeg','-v','error','-ss',str(at),'-i',str(folder/name),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
            if mode=='separate':
                plain=pixels('clip-001.mp4',.5);captioned=pixels('clip-002.mp4',.5)
                self.assertGreater(sum(v>150 for v in captioned[0::3]),sum(v>150 for v in plain[0::3]))
        self.assertEqual(source.read_bytes(),before)

if __name__=='__main__':unittest.main()
