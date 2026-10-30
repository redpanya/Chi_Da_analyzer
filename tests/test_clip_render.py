import tempfile
import unittest
import subprocess
import threading
from pathlib import Path
from archive import clip_contract as c, clip_captions, clip_render
from archive.storage import ProjectLock

class ClipRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name).resolve()
        cls.source=cls.path/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=4','-f','lavfi','-i','sine=frequency=440:duration=4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(cls.source)],check=True)
        cls.src={'file':cls.source,'origin':10000,'duration':4000,'width':320,'height':180,'audio':True}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_validate(self):
        for req in [{'clips':[]},{'clips':[{'title':'x','start_ms':-1,'end_ms':12}]},{'clips':[{'title':'x','start_ms':10000,'end_ms':12000}],'options':{'face':[99,0,5,5]}},{'clips':[{'title':'x','start_ms':10000,'end_ms':12000}],'options':{'caption':True,'speed':'fast'}}]:
            with self.assertRaises(ValueError):c.validate(req,self.src)
    def test_caption_offsets(self):
        clips=[{'start_ms':10000,'end_ms':12000},{'start_ms':12500,'end_ms':14000}]
        rows=[{'start_ms':9000,'end_ms':10500,'text':'시작'},{'start_ms':13000,'end_ms':15000,'text':'끝'}]
        cues,total=clip_captions.cues(rows,clips,'fade')
        self.assertEqual(cues[0]['start_ms'],0);self.assertAlmostEqual(total,3.15);self.assertEqual(cues[-1]['end_ms'],3150)
    def test_render_split_captions_join(self):
        folder=self.path/'render';folder.mkdir();stop=threading.Event()
        req=c.validate({'clips':[{'title':'첫 구간','start_ms':10000,'end_ms':11500},{'title':'둘째','start_ms':12500,'end_ms':14000}],
                        'options':{'layout':'split','caption':True,'caption_x':5,'caption_y':-10,'mode':'joined','transition':'fade','size':'source'}},self.src)
        with ProjectLock(folder) as lock:
            result=clip_render.render(folder,self.src,req,[{'start_ms':10000,'end_ms':11000,'text':'한글 자막 확인'},{'start_ms':13000,'end_ms':14000,'text':'마지막 자막'}],stop,lock,lambda **v:None,{})
        self.assertIn('joined',result);self.assertAlmostEqual(result['joined']['verification']['duration'],2.65,delta=.15)
        info=clip_render.probe(folder/'joined.mp4');v=next(s for s in info['streams'] if s['codec_type']=='video')
        self.assertEqual((v['width'],v['height']),(180,320));self.assertIn('한글 자막 확인',(folder/'joined.srt').read_text(encoding='utf-8-sig'))
    def test_caption_position_and_validation(self):
        from PIL import Image
        from hashlib import sha256
        rows=[{'start_ms':0,'end_ms':1000,'text':'위치 확인'}]
        req={'clips':[{'title':'위치','start_ms':10000,'end_ms':11000}]}
        default=c.validate(req,self.src)['options']
        self.assertEqual((default['caption_x'],default['caption_y']),(0,0))
        for bad in [float('nan'),float('inf'),41,'10',True]:
            with self.assertRaises(ValueError):c.validate(dict(req,options={'caption_x':bad}),self.src)
        for position in ['top','center','bottom']:
            original=dict(default,position=position)
            moved=dict(original,caption_x=10,caption_y=5)
            a=self.path/('caption-'+position);b=self.path/('moved-'+position)
            clip_captions.images(a,rows,(550,800),original,1)
            clip_captions.images(b,rows,(550,800),moved,1)
            name=sha256(rows[0]['text'].encode()).hexdigest()[:20]+'.png'
            with Image.open(a/name) as ia,Image.open(b/name) as ib:
                before=ia.getbbox();after=ib.getbbox()
            self.assertEqual(tuple(y-x for x,y in zip(before,after)),(55,40,55,40))
            clip_captions.write(a,'caption',rows,(550,800),original)
            clip_captions.write(b,'caption',rows,(550,800),moved)
            self.assertEqual((a/'caption.srt').read_bytes(),(b/'caption.srt').read_bytes())
            expected_y=800*({'top':.08,'center':.5,'bottom':.9}[position]+.05)
            self.assertIn(rf'\pos(330.00,{expected_y:.2f})',(b/'caption.ass').read_text(encoding='utf-8-sig'))

    def test_progress_cleanup_and_caption_501(self):
        from archive import studio_maintenance as maintenance
        from archive.storage import save_json
        folder=self.path/'studio/runs'/('e'*32);folder.mkdir(parents=True)
        req=c.validate({'clips':[{'title':'검증','start_ms':10000,'end_ms':11000}], 'options':{'caption':True}},self.src)
        updates=[]
        with ProjectLock(self.path) as lock:
            out=clip_render.render(folder,self.src,req,[{'start_ms':10000,'end_ms':11000,'text':'501번째 자막 교정'}],threading.Event(),lock,lambda **v:updates.append(v),{})
        save_json(folder/'manifest.json',{'id':folder.name,'kind':'start','state':'complete','outputs':out})
        report=maintenance.preview(self.path,folder/'manifest.json','intermediate')
        self.assertNotIn('clip-001.mp4',report['names']);self.assertIn('clip-001-source.mp4',report['names'])
        progress=[v['progress'] for v in updates if 'progress' in v]
        self.assertEqual(progress,sorted(progress));self.assertTrue(any('phase_progress' in v for v in updates))
        self.assertIn('501번째 자막 교정',(folder/'clip-001.srt').read_text(encoding='utf-8-sig'))

    def test_cancel(self):
        folder=self.path/'cancel';folder.mkdir();stop=threading.Event();stop.set()
        from archive.source import Cancelled
        with ProjectLock(folder) as lock,self.assertRaises(Cancelled):
            clip_render.encode(self.src,{'start_ms':10000,'end_ms':12000},c.validate({'clips':[{'title':'a','start_ms':10000,'end_ms':12000}]},self.src)['options'],folder/'out.mp4',stop,lock,lambda **v:None)
        self.assertFalse((folder/'out.mp4').exists())

    def test_resume_preserves_completed_clip(self):
        from archive.source import Cancelled
        folder=self.path/'resume';folder.mkdir();stop=threading.Event();completed={}
        req=c.validate({'clips':[{'title':'첫째','start_ms':10000,'end_ms':11000},{'title':'둘째','start_ms':12000,'end_ms':13000}]},self.src)
        def progress(**values):
            if len(values.get('outputs',{}))==1:stop.set()
        with ProjectLock(folder) as lock:
            with self.assertRaises(Cancelled):clip_render.render(folder,self.src,req,[],stop,lock,progress,completed)
            first=(folder/'clip-001.mp4').read_bytes();modified=(folder/'clip-001.mp4').stat().st_mtime_ns
            stop.clear();clip_render.render(folder,self.src,req,[],stop,lock,lambda **v:None,completed)
        self.assertEqual(len(completed),2);self.assertEqual((folder/'clip-001.mp4').read_bytes(),first)
        self.assertEqual((folder/'clip-001.mp4').stat().st_mtime_ns,modified)

    def test_join_many_fractional_ranges_and_fast(self):
        folder=self.path/'many';folder.mkdir();stop=threading.Event()
        req=c.validate({'clips':[{'title':str(i),'start_ms':10000,'end_ms':11033} for i in range(7)],'options':{'mode':'joined'}},self.src)
        with ProjectLock(folder) as lock:
            result=clip_render.render(folder,self.src,req,[],stop,lock,lambda **v:None,{})
            self.assertAlmostEqual(result['joined']['verification']['duration'],7.231,delta=.15)
            fast=c.validate({'clips':[{'title':'빠른 저장','start_ms':11000,'end_ms':12000}],'options':{'speed':'fast'}},self.src)
            check=clip_render.encode(self.src,fast['clips'][0],fast['options'],folder/'fast.mp4',stop,lock,lambda **v:None)
            self.assertTrue(check['approximate'])

if __name__=='__main__':unittest.main()
