import base64
import hashlib
import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from archive import caption_fonts, caption_styles, clip_contract, clip_captions, studio_images, studio_decorations, clip_render
from archive.storage import ProjectLock


class Decorations(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=Path(self.temp.name).resolve()
        self.src=dict(origin=0,duration=2000,width=640,height=360,audio=False)
        self.req={'clips':[dict(title='검증',start_ms=0,end_ms=1000)]}
        out=io.BytesIO(); Image.new('RGBA',(80,40),(240,40,70,128)).save(out,format='PNG')
        self.png=out.getvalue()
    def tearDown(self):self.temp.cleanup()
    def options(self,**kwargs):return clip_contract.validate(dict(self.req,options=kwargs),self.src)['options']
    def upload(self):
        asset=studio_images.add(self.path,base64.b64encode(self.png).decode(),'검증.png')
        return {k:asset[k] for k in ('asset','name')}|dict(x=50,y=50,width=40,opacity=50)
    def test_all_templates_match_preview_output(self):
        rows=[dict(start_ms=0,end_ms=1000,text='오늘의 방송! 한글 123')]
        hashes=set()
        for key in caption_styles.PRESETS:
            o=self.options(style=key,caption=True);folder=self.path/key
            clip_captions.images(folder,rows,(640,360),o,1)
            name=hashlib.sha256(rows[0]['text'].encode()).hexdigest()[:20]+'.png'
            expected=Image.open(folder/name).tobytes();hashes.add(hashlib.sha256(expected).hexdigest())
            result=studio_decorations.preview(self.path,dict(options=o,text=rows[0]['text'],size=[640,360]))
            self.assertEqual(expected,Image.open(io.BytesIO(base64.b64decode(result['png']))).tobytes())
            clip_captions.write(folder,'caption',rows,(640,360),o)
            self.assertIn('오늘의 방송!',(folder/'caption.srt').read_text(encoding='utf-8-sig'))
            self.assertIn(r'\1c&H00',(folder/'caption.ass').read_text(encoding='utf-8-sig'))
        self.assertEqual(len(hashes),6)
    def test_png_alpha_position_and_missing_asset(self):
        o=self.upload();layer=studio_images.layer((500,300),studio_images.load(self.path,o),o)
        self.assertEqual(layer.getbbox(),(150,100,350,200));self.assertEqual(layer.getpixel((250,150))[3],64)
        outside=dict(o,x=0,y=0);self.assertEqual(studio_images.layer((500,300),studio_images.load(self.path,o),outside).getbbox(),(0,0,100,50))
        with self.assertRaises(ValueError):studio_images.load(self.path,dict(o,asset='f'*64))
        studio_images.location(self.path,o['asset']).write_bytes(b'changed')
        with self.assertRaises(ValueError):studio_images.load(self.path,o)
    def test_invalid_uploads_and_paths(self):
        for raw in [b'not png',b'GIF89a']:
            with self.assertRaises(ValueError):studio_images.add(self.path,base64.b64encode(raw).decode(),'a.png')
        with self.assertRaises(ValueError):studio_images.add(self.path,'%%%','a.png')
        with self.assertRaises(ValueError):studio_images.location(self.path,'../source')
        for options in [dict(font='/Library/Fonts/a.ttf'),dict(image={'asset':'a'*64}),dict(image=self.upload()|{'x':float('nan')}),dict(speed='fast',image=self.upload())]:
            with self.assertRaises(ValueError):self.options(**options)
        data=io.BytesIO();Image.new('RGBA',(4,4)).save(data,format='PNG',save_all=True,append_images=[Image.new('RGBA',(4,4),'red')],duration=100)
        with self.assertRaises(ValueError):studio_images.decode(data.getvalue())
        target=self.path/'outside';target.mkdir();(self.path/'other').mkdir();(self.path/'other/studio').symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError):studio_images.add(self.path/'other',base64.b64encode(self.png).decode(),'a.png')
    def test_drag_preview_preserves_alpha_and_original_dimensions(self):
        raw=io.BytesIO();Image.new('RGBA',(4096,512),(200,50,60,128)).save(raw,format='PNG')
        asset=studio_images.add(self.path,base64.b64encode(raw.getvalue()).decode(),'드래그.png')
        path=studio_images.location(self.path,asset['asset']);before=path.read_bytes()
        result=studio_images.preview(self.path,asset['asset'])
        with Image.open(io.BytesIO(base64.b64decode(result['png']))) as image:
            self.assertEqual(image.size,(2048,256));self.assertEqual(image.getpixel((400,100))[3],128)
        self.assertEqual((result['width_px'],result['height_px']),(4096,512))
        self.assertEqual(before,path.read_bytes())
        for invalid in [None,'../source','f'*64]:
            with self.assertRaises(ValueError):studio_images.preview(self.path,invalid)
    def test_installed_font_scan_override_and_missing(self):
        with patch.object(caption_fonts,'roots',return_value=[caption_fonts.BUNDLED/'jua']):
            try:
                rows=caption_fonts.catalog(True);self.assertEqual(len(rows),1)
                self.assertTrue(rows[0]['korean']);self.assertNotIn('path',rows[0])
                face,name=caption_styles.font(self.options(style='soft',font=rows[0]['id']),22)
                self.assertEqual(name,rows[0]['family'])
                with self.assertRaises(ValueError):caption_fonts.resolve('f'*24)
            finally:caption_fonts._installed.cache_clear()
    def test_png_only_and_template_mp4(self):
        import subprocess
        source=self.path/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=navy:s=640x360:r=30:d=2','-c:v','libx264',str(source)],check=True)
        before=hashlib.sha256(source.read_bytes()).hexdigest();image=self.upload()
        src=self.src|{'file':source,'overlay':studio_images.load(self.path,image)}
        for key in ['png-only',*caption_styles.PRESETS]:
            folder=self.path/key;folder.mkdir()
            req=clip_contract.validate(dict(self.req,options=dict(image=image,caption=key!='png-only',style='basic' if key=='png-only' else key)),src)
            rows=[dict(start_ms=100,end_ms=900,text='한글 자막과 투명 이미지')]
            with ProjectLock(folder) as lock:
                result=clip_render.render(folder,src,req,rows,threading.Event(),lock,lambda **v:None,{})
            self.assertAlmostEqual(result['clip-001']['verification']['duration'],1,delta=.15)
            frame=folder/'frame.png';subprocess.run(['ffmpeg','-v','error','-ss','0.5','-i',str(folder/'clip-001.mp4'),'-frames:v','1',str(frame)],check=True)
            pixel=Image.open(frame).convert('RGB').getpixel((320,180))
            if pixel[0]<=35:
                # 실패 시 가상 자료의 입력/출력 픽셀과 합성 로그로 OS 차이를 확인한다.
                layer=folder/'clip-001-final-working-captions'
                details={p.name:Image.open(p).convert('RGBA').getpixel((320,180)) for p in layer.glob('*.png')}
                print('PNG 합성 진단:',key,'출력 크기',Image.open(frame).size,'픽셀',pixel,'입력',details,flush=True)
                print((layer/'captions.ffconcat').read_text(),flush=True)
                print((folder/'clip-001-final-working.log').read_text(errors='replace')[-6000:],flush=True)
            self.assertGreater(pixel[0],35) # 반투명 빨강 PNG가 실제 영상에 합성됨
            self.assertLess(pixel[1],40)
            self.assertGreater(pixel[2],70)
        self.assertEqual(before,hashlib.sha256(source.read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
