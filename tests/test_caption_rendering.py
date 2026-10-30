"""글꼴 이름에 의존하지 않는 빈 글리프·문장 호환성 회귀 검사."""
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from PIL import Image
from archive import caption_fonts, caption_styles, clip_captions, clip_contract, clip_render


class CaptionRenderingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.root=self.path/'fonts';self.root.mkdir()
        self.point=self.root/'point-space.ttf';self.empty=self.root/'empty-space.ttf'
        for file,point in [(self.point,True),(self.empty,False)]:
            with TTFont(caption_fonts.BUNDLED/'jua/Jua-Regular.ttf') as font:
                pen=TTGlyphPen(None)
                if point:pen.moveTo((0,58));pen.closePath()
                font['glyf'][font.getBestCmap()[32]]=pen.glyph()
                font.save(file)
        self.before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [self.point,self.empty]}
        self.mock=patch.object(caption_fonts,'roots',return_value=[self.root]);self.mock.start()
        caption_fonts.catalog(True)
        rows=caption_fonts._installed().values()
        self.keys={r['path'].name:r['id'] for r in rows}
        self.src=dict(origin=0,duration=10000,width=640,height=360,audio=False)

    def tearDown(self):
        self.mock.stop();caption_fonts._installed.cache_clear();caption_fonts.face.cache_clear();self.temp.cleanup()

    def options(self,**value):
        return clip_contract.validate(dict(clips=[],options=dict(caption=True,font=self.keys['point-space.ttf'],**value)),self.src,draft=True)['options']

    def test_degenerate_space_keeps_metrics_and_pixels_in_all_styles(self):
        for pixels in [22,30,44,86]:
            face=caption_fonts.face(self.point,0,pixels,self.point.stat().st_mtime_ns)
            self.assertAlmostEqual(face.getlength('가   나')-face.getlength('가 나'),2*face.getlength(' '),places=4)
            face.getmask(' ')
        for style in ['basic','box','accent',*caption_styles.PRESETS]:
            options=self.options(style=style)
            for text in ['안녕 하세요','  안녕   하세요  \n\n ABC 123 ', '', '   ', '\n\n']:
                point=Image.new('RGBA',(640,360));empty=point.copy()
                caption_styles.paint(point,text,point.size,options)
                caption_styles.paint(empty,text,empty.size,dict(options,font=self.keys['empty-space.ttf']))
                self.assertEqual(point.tobytes(),empty.tobytes(),(style,text))
        self.assertEqual(self.before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.before})

    def test_real_sentence_catches_missing_glyph_and_render_failure(self):
        options=self.options();image=Image.new('RGBA',(640,360))
        with self.assertRaisesRegex(ValueError,'U\\+10FFFF'):
            caption_styles.paint(image,'정상 한글 '+chr(0x10ffff),image.size,options)
        with patch.object(caption_styles,'_paint',side_effect=OSError('Bitmap missing for glyph')):
            with self.assertRaisesRegex(ValueError,'이 자막을 그리지 못했습니다'):
                caption_styles.paint(image,'안녕 하세요',image.size,options)

    def test_selected_sentences_only_and_deduplicated(self):
        rows=[dict(start_ms=0,end_ms=1000,text='안녕 하세요'),dict(start_ms=1000,end_ms=2000,text='안녕 하세요'),
              dict(start_ms=3000,end_ms=4000,text=chr(0x10ffff))]
        clips=[dict(start_ms=0,end_ms=2000)]
        with patch.object(caption_styles,'paint',wraps=caption_styles.paint) as paint:
            clip_captions.preflight(rows,clips,(640,360),self.options())
            self.assertEqual(paint.call_count,1)
        with self.assertRaisesRegex(ValueError,'00:00:03,000'):
            clip_captions.preflight(rows,[dict(start_ms=0,end_ms=5000)],(640,360),self.options())
        clip_captions.preflight(rows,clips,(640,360),dict(self.options(),caption=False))

    def test_render_checks_actual_captions_before_encoding(self):
        request=clip_contract.validate({'clips':[dict(start_ms=0,end_ms=1000,title='검사')], 'options':self.options()},self.src)
        with patch.object(clip_render,'encode') as encode:
            with self.assertRaisesRegex(ValueError,'자막 호환성 검사'):
                clip_render.render(self.path,self.src,request,[dict(start_ms=0,end_ms=1000,text=chr(0x10ffff))],threading.Event(),None,lambda **v:None,{})
            encode.assert_not_called()


if __name__=='__main__':unittest.main()
