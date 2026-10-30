"""외부 요청 미리보기와 저장 작업서가 모든 모드에서 같은 계약을 유지한다."""
import base64
import io
import unittest
import zipfile
from unittest.mock import patch
import test_context_exchange
from archive import context_exchange as exchange, context_exchange_zip as zipper
from archive.storage import read_json, save_json


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_context_exchange.ExchangeTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.path=self.fixture.path

    def test_all_modes_custom_snapshot_full_list_zip_and_txt(self):
        custom='노래 제목이 확인되는 경우 제목에 넣어 주세요.\n불확실한 제목은 추측하지 마세요.'
        for mode in ('timestamps','detail','clips'):
            with self.subTest(mode=mode),patch.object(exchange,'PACKET_BYTES',700):
                value=exchange.create(self.path,'1',{'mode':mode,'custom_request':custom})
                target=exchange.folder(self.path,value['id']);saved=read_json(target/'manifest.json')
                self.assertEqual(saved['custom_request'],custom)
                self.assertGreater(len(saved['chunks']),1)
                self.assertIn('전체 목록이 완료되면',value['prompt'])
                self.assertIn('하나의 ZIP으로 압축',value['prompt'])
                self.assertIn('노래 제목이 확인되는 경우',value['prompt'])
                self.assertIn('review_needed',value['prompt'])
                for chunk in saved['chunks']:
                    self.assertIn(f'자료/chida-{value["id"][:8]}-{chunk["id"]}.json → chida-result-',value['prompt'])
                for file in value['files']:
                    self.assertIn('노래 제목이 확인되는 경우',file['text'])
                before={p.name:p.read_bytes() for p in target.iterdir()}
                with patch.object(exchange,'prompt',side_effect=AssertionError('저장한 요청은 다시 만들지 않음')):
                    self.assertEqual(exchange.bundle(self.path,value['id'])['prompt'],value['prompt'])
                    packed=zipper.pack(self.path,value['id'])
                with zipfile.ZipFile(io.BytesIO(base64.b64decode(packed['base64']))) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(archive.read('작업서.txt').decode(),value['prompt'])
                    self.assertEqual(len(archive.namelist()),len(saved['chunks'])+1)
                self.assertEqual(before,{p.name:p.read_bytes() for p in target.iterdir()})
        self.assertEqual(self.fixture.before,self.fixture.old.read_bytes())

    def test_legacy_manifest_without_custom_fields_stays_readable_and_unchanged(self):
        value=self.fixture.create();target=exchange.folder(self.path,value['id'])/'manifest.json'
        saved=read_json(target)
        for field in ('custom_request','request_prompt','work_order'):saved.pop(field)
        save_json(target,saved);before=target.read_bytes()
        restored=exchange.bundle(self.path,value['id'])
        self.assertEqual(restored['custom_request'],'')
        self.assertIn('전체 목록',restored['prompt'])
        zipper.pack(self.path,value['id'])
        self.assertEqual(before,target.read_bytes())

    def test_invalid_custom_request_rejected_before_source_read(self):
        for custom in (None,[],{},4,'가'*4001,'안녕\x00'):
            with self.subTest(custom=type(custom)),patch.object(exchange.data,'snapshot') as source:
                with self.assertRaises(ValueError):exchange.create(self.path,'1',{'custom_request':custom})
                source.assert_not_called()
        self.assertEqual(exchange.custom_request('  노래 제목  '),'노래 제목')
        self.assertEqual(len(exchange.custom_request('가'*4000)),4000)
        with self.assertRaises(ValueError):exchange.prompt('missing')


if __name__=='__main__':unittest.main()
