import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from archive import caption_design, caption_templates
from archive.storage import Conflict, ProjectLock, read_json, save_json
from archive.studio_jobs import Studio


class CaptionTemplates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.support = patch('archive.runtime.SUPPORT', self.root)
        self.support.start()
        self.addCleanup(self.support.stop);self.addCleanup(self.temp.cleanup)
        self.design = dict(caption_design.DEFAULT, text_color='#fe5069', shadow=True, box=True)

    def save(self, name='코랄 자막'):
        return Studio(None).dispatch('template-save', dict(name=name, design=self.design))

    def test_persistent_snapshot_and_remove(self):
        self.assertEqual(caption_templates.dispatch('list', {})['templates'], [])
        result = self.save();id = result['id'];file = self.root/'caption-templates'/f'{id}.json'
        original = file.read_bytes()
        applied = copy.deepcopy(result['templates'][0]['design'])
        self.design['text_color'] = '#123456'
        listed = Studio(None).dispatch('template-list', {})['templates']
        self.assertEqual(listed[0]['style'], 'box')
        self.assertEqual(listed[0]['design'], applied)
        self.assertFalse({'font', 'font_size', 'position'} & set(listed[0]['design']))
        draft = self.root/'draft.json';save_json(draft, {'options':{'caption_design':applied}})
        before = draft.read_bytes()
        result = Studio(None).dispatch('template-delete', {'id':id})
        self.assertEqual(result['templates'], []);self.assertFalse(file.exists())
        self.assertEqual(draft.read_bytes(), before)
        self.assertEqual(next((file.parent/'deleted').glob('*.json')).read_bytes(), original)

    def test_duplicate_and_invalid_name_preserve_existing(self):
        self.save();before = caption_templates.entries()
        for name in ['', ' ', '줄\n바꿈', 'a'*61, None]:
            with self.subTest(name=name), self.assertRaises(ValueError):self.save(name)
        with self.assertRaises(Conflict):self.save(' 코랄 자막 ')
        self.assertEqual(caption_templates.entries(), before)

    def test_invalid_design_and_delete_id(self):
        for design in [None, {}, dict(self.design, font='auto'), dict(self.design, box_opacity=101)]:
            with self.subTest(design=design), self.assertRaises(ValueError):
                caption_templates.dispatch('save', {'name':'검사', 'design':design})
        for id in ['basic', '../draft', None, 'a'*32]:
            with self.subTest(id=id), self.assertRaises(ValueError):caption_templates.dispatch('delete', {'id':id})
        self.assertEqual(caption_templates.entries(), [])

    def test_other_template_survives_and_removed_cannot_delete_twice(self):
        a=self.save('하나');b=self.save('둘')
        caption_templates.dispatch('delete', {'id':a['id']})
        self.assertEqual([t['id'] for t in caption_templates.entries()], [b['id']])
        with self.assertRaises(Conflict):caption_templates.dispatch('delete', {'id':a['id']})

    def test_corrupt_file_is_not_overwritten(self):
        result=self.save();file=self.root/'caption-templates'/f"{result['id']}.json"
        file.write_text('{잘못된 파일');before=file.read_bytes()
        with self.assertRaises(ValueError):self.save('다른 이름')
        self.assertEqual(file.read_bytes(), before)

    def test_concurrent_write_and_link_rejected(self):
        with ProjectLock(caption_templates.folder()), self.assertRaises(Conflict):self.save()
        result=self.save();folder=caption_templates.folder();outside=self.root/'outside';outside.mkdir()
        (folder/'deleted').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):caption_templates.dispatch('delete', {'id':result['id']})
        self.assertEqual(len(caption_templates.entries()), 1)


if __name__ == '__main__':unittest.main()
