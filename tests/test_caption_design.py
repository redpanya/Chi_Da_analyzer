"""맞춤 자막의 입력 경계·보존·미리보기/출력 연결 검사."""
import base64
import hashlib
import io
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from PIL import Image
from archive import caption_design, caption_styles, clip_contract, clip_captions, clip_render, studio_decorations
from archive.storage import ProjectLock


class CaptionDesignTests(unittest.TestCase):
    src=dict(origin=0,duration=2000,width=640,height=360,audio=False)
    def options(self,design=None,style='basic'):
        return clip_contract.validate(dict(clips=[],options=dict(caption=True,style=style,caption_design=design,position='center')),self.src,draft=True)['options']

    def test_contract_roundtrip_and_rejection(self):
        d=dict(caption_design.DEFAULT,text_color='#FE5069',shadow=True,box=True,outline_width=2.5)
        self.assertEqual(self.options(d)['caption_design'],d)
        self.assertIsNone(self.options()['caption_design'])
        invalid=[{},[],dict(d,unknown=True),dict(d,text_color='red'),dict(d,box='yes'),dict(d,outline_width=True),
                 dict(d,shadow_x=float('nan')),dict(d,box_opacity=101),dict(d,box_padding=-1),dict(d,shadow_blur=9)]
        for value in invalid:
            with self.subTest(value=value),self.assertRaises(ValueError):self.options(value)
        self.assertEqual(d['outline_width'],2.5)

    def test_legacy_design_pixels_unchanged_without_customization(self):
        for key in ['basic','box','accent',*caption_styles.PRESETS]:
            options=self.options(style=key);before=Image.new('RGBA',(640,360));after=before.copy()
            old={k:v for k,v in options.items() if k!='caption_design'}
            caption_styles.paint(before,'원래 자막 123',before.size,old)
            caption_styles.paint(after,'원래 자막 123',after.size,options)
            self.assertEqual(before.tobytes(),after.tobytes(),key)

    def test_preview_and_export_images_match_and_effects_are_independent(self):
        variants=[dict(caption_design.DEFAULT),dict(caption_design.DEFAULT,text_color='#FE5069'),
                  dict(caption_design.DEFAULT,outline=False),dict(caption_design.DEFAULT,outline_color='#7947DE',outline_width=4),
                  dict(caption_design.DEFAULT,shadow=True,shadow_color='#7947DE',shadow_opacity=50,shadow_blur=3),
                  dict(caption_design.DEFAULT,box=True,box_color='#7947DE',box_opacity=50)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);hashes=set();rows=[dict(start_ms=0,end_ms=1000,text='한글 자막 ABC 123')]
            for i,d in enumerate(variants):
                options=self.options(d);folder=root/str(i)
                clip_captions.images(folder,rows,(640,360),options,1)
                name=hashlib.sha256(rows[0]['text'].encode()).hexdigest()[:20]+'.png'
                output=Image.open(folder/name).tobytes();hashes.add(hashlib.sha256(output).hexdigest())
                preview=studio_decorations.preview(root,dict(options=options,text=rows[0]['text'],size=[640,360]))
                self.assertEqual(output,Image.open(io.BytesIO(base64.b64decode(preview['png']))).tobytes())
            self.assertEqual(len(hashes),len(variants))

    def test_ass_carries_colors_layers_and_escapes_dialogue(self):
        options=self.options(dict(caption_design.DEFAULT,text_color='#FE5069',outline_color='#7947DE',shadow=True,shadow_x=-3,box=True))
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);clip_captions.write(folder,'test',[dict(start_ms=0,end_ms=1000,text=r'문장 {\pos(0,0)}')],(640,360),options)
            ass=(folder/'test.ass').read_text(encoding='utf-8-sig')
            self.assertIn('Style: Box,',ass);self.assertIn(r'\1c&H6950FE&',ass);self.assertIn(r'\3c&HDE4779&',ass)
            self.assertEqual(ass.count('Dialogue:'),3);self.assertIn('｛＼pos(0,0)｝',ass)

    def test_custom_caption_short_video_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source=folder/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=640x360:r=30:d=2','-c:v','libx264',str(source)],check=True)
            before=hashlib.sha256(source.read_bytes()).hexdigest();src=self.src|{'file':source}
            options=self.options(dict(caption_design.DEFAULT,text_color='#FE5069',shadow=True,box=True,box_color='#7947DE',box_opacity=70))
            request=clip_contract.validate(dict(clips=[dict(title='검증',start_ms=0,end_ms=1000)],options=options),src)
            rows=[dict(start_ms=0,end_ms=1000,text='맞춤 자막 확인')]
            with ProjectLock(folder) as lock:result=clip_render.render(folder,src,request,rows,threading.Event(),lock,lambda **v:None,{})
            self.assertAlmostEqual(result['clip-001']['verification']['duration'],1,delta=.15)
            frame=folder/'frame.png';subprocess.run(['ffmpeg','-v','error','-ss','0.5','-i',str(folder/'clip-001.mp4'),'-frames:v','1',str(frame)],check=True)
            image=Image.open(frame).convert('RGB');self.assertGreater(max(p[0] for p in image.getdata()),100)
            self.assertEqual(before,hashlib.sha256(source.read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
