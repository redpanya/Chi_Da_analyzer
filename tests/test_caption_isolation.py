import base64
import copy
import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from archive import studio_decorations, clip_contract

class CaptionIsolation(unittest.TestCase):
    def test_preview_ignores_crop_for_every_ratio_and_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            options={'caption':True,'style':'basic','font_size':28}
            data={'text':'자막은 계속 보여야 합니다 123','size':[640,360],'options':options}
            expected=studio_decorations.preview(root,data)['png']
            for ratio in ['original','16:9','9:16','1:1','4:5']:
                for layout in ['single','split']:
                    # 범위 초과와 형식 오류도 자막 API에는 영향을 주지 않는다.
                    supplied=options|dict(ratio=ratio,layout=layout,game=[0,0,100,100],face=[80,50,30,50])
                    original=copy.deepcopy(supplied)
                    actual=studio_decorations.preview(root,data|{'options':supplied})['png']
                    self.assertEqual(actual,expected);self.assertEqual(supplied,original)
            image=Image.open(io.BytesIO(base64.b64decode(expected)))
            self.assertIsNotNone(image.getbbox())
            self.assertEqual(studio_decorations.preview(root,data|{'options':options|{'face':'bad'}})['png'],expected)
    def test_render_rejects_only_active_invalid_area_without_mutating(self):
        src=dict(origin=0,duration=10000,width=1920,height=1080)
        req={'clips':[dict(start_ms=0,end_ms=1000,title='검사')], 'options':{'layout':'single','face':[80,50,30,50]}}
        before=copy.deepcopy(req)
        self.assertEqual(clip_contract.validate(req,src)['options']['face'],[80,50,30,50]);self.assertEqual(before,req)
        req['options']['layout']='split'
        with self.assertRaisesRegex(ValueError,'얼굴 영역.*가로'):clip_contract.validate(req,src)
        req['options']['face']=[70,50,30,50]
        self.assertEqual(clip_contract.validate(req,src)['options']['layout'],'split')
    def test_caption_errors_are_still_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):studio_decorations.preview(Path(temp),{'size':[640,360],'text':'검사','options':{'font_size':999999}})

if __name__=='__main__':unittest.main()
