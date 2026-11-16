"""공통 프리셋의 원본 독립성·이전 설정 보존·변경 충돌을 임시 자료만으로 검사한다."""
import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from archive import studio_profiles as presets, studio_images as images
from archive.storage import Conflict, ProjectLock, read_json, save_json

class PresetAssets(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.source=self.base/'source';self.source.mkdir()
        self.target=self.base/'target';self.target.mkdir()
        self.support=patch.object(presets.runtime,'SUPPORT',self.base/'support');self.support.start()
        buffer=io.BytesIO();Image.new('RGBA',(8,6),(255,0,120,150)).save(buffer,format='PNG')
        asset=images.add(self.source,base64.b64encode(buffer.getvalue()).decode(),'원래 PNG.png')
        self.image={k:asset[k] for k in ('asset','name')}|dict(x=40,y=80,width=35,opacity=92)
    def tearDown(self):self.support.stop();self.temp.cleanup()
    def save(self):
        result=presets.dispatch('save',dict(name='PNG 프리셋',options={'image':self.image,'ratio':'9:16'}),self.source)
        return result['presets'][0]
    def test_source_removed_still_applies_and_preserves_copied_values(self):
        item=self.save();stored=images.location(presets.folder(),self.image['asset']).read_bytes()
        images.location(self.source,self.image['asset']).unlink()
        applied=presets.dispatch('apply',dict(id=item['id'],revision=1),self.target)['options']
        self.assertEqual(applied['image'],self.image)
        self.assertEqual(images.location(self.target,self.image['asset']).read_bytes(),stored)
        self.assertEqual(images.load(self.target,applied['image']).size,(8,6))
        # 프리셋 제거도 적용 대상의 PNG·설정을 바꾸지 않는다.
        presets.dispatch('delete',{'id':item['id']})
        self.assertEqual(images.location(self.target,self.image['asset']).read_bytes(),stored)
        self.assertEqual(applied['image']['y'],80)
    def test_shared_preset_during_other_draft_write_and_image_collision(self):
        item=self.save()
        args=dict(id=item['id'],revision=1)
        with ProjectLock(self.target,write=['studio-draft']):
            with ProjectLock(self.target,read=['studio-images']):
                with self.assertRaises(Conflict):
                    presets.dispatch('apply',args,self.target)
                self.assertFalse(images.location(self.target,self.image['asset']).exists())
            self.assertEqual(presets.dispatch('apply',args,self.target)['options']['image'],self.image)

    def test_overwrite_archives_old_revision_and_rejects_stale_writers(self):
        old=self.save();file=presets.folder()/(old['id']+'.json');before=file.read_bytes()
        payload=dict(id=old['id'],revision=1,name=old['name'],options={'image':self.image,'ratio':'1:1'})
        result=presets.dispatch('save',payload,self.source);new=result['presets'][0]
        self.assertEqual(new['id'],old['id']);self.assertEqual(new['revision'],2)
        backups=list((presets.folder()/'history').glob('*.json'));self.assertEqual(len(backups),1)
        self.assertEqual(read_json(backups[0]),old)
        saved=file.read_bytes();self.assertNotEqual(saved,before)
        with self.assertRaises(Conflict):presets.dispatch('save',payload,self.source)
        with self.assertRaises(Conflict):presets.dispatch('apply',dict(id=old['id'],revision=1),self.target)
        self.assertEqual(file.read_bytes(),saved)
    def test_missing_or_changed_png_does_not_replace_preset(self):
        item=self.save();file=presets.folder()/(item['id']+'.json');before=file.read_bytes()
        source=images.location(self.source,self.image['asset']);source.write_bytes(b'changed')
        with self.assertRaises(ValueError):presets.dispatch('save',dict(id=item['id'],revision=1,name=item['name'],options={'image':self.image}),self.source)
        self.assertEqual(file.read_bytes(),before)
        images.location(presets.folder(),self.image['asset']).unlink()
        with self.assertRaises(ValueError):presets.dispatch('apply',dict(id=item['id'],revision=1),self.target)
        self.assertFalse(images.location(self.target,self.image['asset']).exists())
    def test_symlinks_and_traversal_rejected(self):
        with self.assertRaises(ValueError):presets.preset_options({'image':self.image|{'asset':'../../secret'}})
        item=self.save();(self.target/'studio').symlink_to(self.source/'studio',target_is_directory=True)
        original=images.location(self.source,self.image['asset']).read_bytes()
        with self.assertRaises(ValueError):presets.dispatch('apply',dict(id=item['id'],revision=1),self.target)
        self.assertEqual(images.location(self.source,self.image['asset']).read_bytes(),original)
    def test_failed_copy_cleans_temporary_and_keeps_source(self):
        original=images.location(self.source,self.image['asset']).read_bytes()
        with patch.object(Path,'replace',side_effect=OSError('디스크 부족')):
            with self.assertRaises(OSError):images.copy_asset(self.source,self.target,self.image)
        self.assertFalse(images.location(self.target,self.image['asset']).exists())
        self.assertFalse(list(self.target.rglob('*.part')))
        self.assertEqual(images.location(self.source,self.image['asset']).read_bytes(),original)
    def test_legacy_presets_keep_existing_image_on_apply(self):
        key='a'*32;old=dict(schema=1,id=key,name='기존',created_at='2026',options={'ratio':'original'})
        file=presets.folder()/(key+'.json');save_json(file,old);before=file.read_bytes()
        applied=presets.dispatch('apply',dict(id=key,revision=1),self.target)
        self.assertNotIn('image',applied['options']);self.assertEqual(file.read_bytes(),before)

if __name__=='__main__':unittest.main()
