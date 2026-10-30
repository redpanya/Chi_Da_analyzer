"""템플릿/글꼴 분리와 언어 필터의 회귀 검사."""
import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from fontTools.ttLib import TTFont
from archive import caption_fonts, caption_styles, clip_captions, clip_contract, studio_decorations, font_languages


class FontTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.roots=patch.object(caption_fonts,'roots',return_value=[caption_fonts.BUNDLED]);self.roots.start()
        self.fonts=caption_fonts.catalog(True)
        self.jua=next(r for r in self.fonts if r['family']=='Jua')['id']
        self.gaegu=next(r for r in self.fonts if r['family']=='Gaegu')['id']
    def tearDown(self):
        self.roots.stop();caption_fonts._installed.cache_clear();self.temp.cleanup()
    def options(self,**value):
        return clip_contract.validate({'clips':[],'options':value},dict(width=640,height=360,origin=0,duration=1000),draft=True)['options']
    def test_templates_never_choose_a_font(self):
        names=set()
        for style in ['basic','box','accent',*caption_styles.PRESETS]:
            self.assertNotIn('font',caption_styles.PRESETS.get(style,{}))
            for key,name in [(self.jua,'Jua'),(self.gaegu,'Gaegu')]:
                self.assertEqual(caption_styles.font(self.options(style=style,font=key),28)[1],name)
            names.add(caption_styles.font(self.options(style=style),28)[1])
        self.assertEqual(len(names),1)
    def test_selected_face_changes_preview_and_saved_image(self):
        text='같은 템플릿 다른 글꼴'
        rows=[dict(start_ms=0,end_ms=1000,text=text)]
        renders=[]
        for key in [self.jua,self.gaegu]:
            options=self.options(style='soft',font=key,caption=True)
            result=studio_decorations.preview(self.path,dict(options=options,text=text,size=[640,360]))
            preview=Image.open(io.BytesIO(base64.b64decode(result['png']))).tobytes();renders.append(preview)
            folder=self.path/key;clip_captions.images(folder,rows,(640,360),options,1)
            png=next(p for p in folder.glob('*.png') if p.name!='blank.png')
            self.assertEqual(preview,Image.open(png).tobytes())
            clip_captions.write(folder,'captions',rows,(640,360),options)
            family=caption_fonts.resolve(key)[2]
            self.assertIn('Style: Default,'+family+',',(folder/'captions.ass').read_text(encoding='utf-8-sig'))
        self.assertNotEqual(*renders)
    def test_language_coverage_is_more_than_one_sample_character(self):
        with TTFont(caption_fonts.BUNDLED/'jua/Jua-Regular.ttf') as font:
            for table in font['cmap'].tables:
                if table.isUnicode():table.cmap={code:glyph for code,glyph in table.cmap.items() if code<128 or code==ord('한')}
            file=self.path/'latin-and-one-hangul.ttf';font.save(file)
        support=font_languages.inspect(file,0)
        self.assertIn('en',support['languages']);self.assertNotIn('ko',support['languages'])
        with patch.object(caption_fonts,'roots',return_value=[self.path]):
            rows=caption_fonts.catalog(True)
            self.assertEqual(len(rows),1);self.assertFalse(rows[0]['korean'])
            with self.assertRaisesRegex(ValueError,'지원하는 글꼴이 없습니다'):caption_fonts.resolve(language='ko')
        for language in font_languages.LANGUAGES:
            self.assertIn(language,font_languages.required())
        self.assertEqual(len(font_languages.required()['ko']),2350+51)
    def test_last_resort_placeholder_font_is_excluded(self):
        with TTFont(caption_fonts.BUNDLED/'jua/Jua-Regular.ttf') as font:
            font['head'].flags |= 0x4000
            file=self.path/'placeholder.ttf';font.save(file)
        self.assertEqual(font_languages.inspect(file,0)['languages'],[])

    def test_existing_choices_missing_fonts_and_language_validation(self):
        self.assertEqual(caption_fonts.frozen_options({'style':'soft','font':'auto'})['font'],self.gaegu)
        self.assertEqual(caption_fonts.frozen_options({'style':'soft','font':self.jua})['font'],self.jua)
        self.assertNotEqual(caption_fonts.frozen_options(self.options(style='soft'))['font'],self.gaegu)
        for value in ['../ko',None,[],True]:
            with self.assertRaises(ValueError):self.options(caption_language=value)
        with self.assertRaises(ValueError):caption_fonts.resolve('f'*24)
        # 경로는 목록 응답에 포함하지 않는다.
        self.assertTrue(all('path' not in r and 'index' not in r for r in self.fonts))

if __name__=='__main__':unittest.main()
