"""계열 묶음이 개별 글꼴 선택·출력 계약을 바꾸지 않는지 검사한다."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fontTools.ttLib import TTFont
from archive import caption_fonts, font_families


class FontFamilyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):
        caption_fonts._installed.cache_clear();self.temp.cleanup()
    def make(self,name,weight=400,vendor='검증 제작사',preferred=None,style='Regular',width=5):
        target=self.root/(name+str(len(list(self.root.iterdir())))+'.ttf')
        with TTFont(caption_fonts.BUNDLED/'jua/Jua-Regular.ttf') as font:
            names=font['name'];names.names=[r for r in names.names if r.nameID not in (1,2,8,16,17)]
            for key,value in [(1,name),(2,style),(8,vendor)]:names.setName(value,key,3,1,0x409)
            if preferred:
                names.setName(preferred,16,3,1,0x409);names.setName(style,17,3,1,0x409)
            font['OS/2'].usWeightClass=weight;font['OS/2'].usWidthClass=width;font.save(target)
        return dict(id=target.stem,family=name,label=name+' · '+style,**font_families.inspect(target,0,name,style))
    def test_legacy_suffixes_need_siblings_and_keep_ids(self):
        light=self.make('SampleLight');bold=self.make('SampleBold');short=self.make('SamLight')
        ids=[r['id'] for r in [light,bold,short]]
        result=font_families.group([light,bold,short])
        self.assertEqual(light['family_id'],bold['family_id']);self.assertEqual(light['family_name'],'Sample')
        self.assertEqual([light['weight'],bold['weight']],[300,700]);self.assertEqual(short['family_name'],'SamLight')
        self.assertEqual([r['id'] for r in result],ids)
    def test_typographic_family_vendor_width_and_duplicate_faces(self):
        regular=self.make('Body',preferred='Sample',weight=400)
        bold=self.make('Body Bold',preferred='Sample',style='Bold',weight=700)
        copy=self.make('Body Bold',preferred='Sample',style='Bold',weight=700)
        other=self.make('Body',preferred='Sample',vendor='다른 제작사')
        narrow=self.make('Body',preferred='Sample',width=3)
        rows=font_families.group([regular,bold,copy,other,narrow])
        self.assertEqual(regular['family_id'],bold['family_id']);self.assertEqual(copy['family_id'],bold['family_id'])
        self.assertNotEqual(copy['id'],bold['id']);self.assertEqual(len(rows),5)
        self.assertNotEqual(other['family_id'],regular['family_id']);self.assertNotEqual(narrow['family_id'],regular['family_id'])
    def test_metadata_and_ass_weight_preserve_exact_face(self):
        self.make('ExampleLight');self.make('ExampleBold')
        with patch.object(caption_fonts,'roots',return_value=[self.root]):
            rows=caption_fonts.catalog(True)
            for row in rows:
                self.assertNotIn('path',row);self.assertNotIn('index',row)
                selected=caption_fonts.frozen_options({'font':row['id']})
                self.assertEqual(selected['font'],row['id'])
                family,bold,italic=caption_fonts.ass_face(row['id'])
                self.assertEqual(family,row['family']);self.assertEqual(bold,-1 if row['style']=='Bold' else 0);self.assertEqual(italic,0)

if __name__=='__main__':unittest.main()
