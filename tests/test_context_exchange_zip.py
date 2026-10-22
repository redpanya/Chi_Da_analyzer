import base64
import copy
import io
import json
import stat
import unittest
import zipfile
from unittest.mock import patch
import test_context_exchange
from archive import context_exchange as exchange, context_exchange_batch as batch, context_exchange_zip as zipper
from archive.storage import read_json


def zipped(files):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,text in files:archive.writestr(name,text)
    return base64.b64encode(buffer.getvalue()).decode('ascii')


class ZipTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_context_exchange.ExchangeTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.path=self.fixture.path;self.bundle=self.fixture.create();self.entries=self.fixture.responses(self.bundle)

    def payload(self,entries=None):
        return {'archive':zipped([(f'결과/chida-result-{e["chunk_id"]}.json',json.dumps(e,ensure_ascii=False)) for e in (self.entries if entries is None else entries)])}

    def test_export_work_order_json_and_preserve_existing_source(self):
        source=exchange.folder(self.path,self.bundle['id'])/'source.json';before=source.read_bytes()
        packed=zipper.pack(self.path,self.bundle['id'])
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(packed['base64']))) as archive:
            self.assertIn('작업서.txt',archive.namelist())
            order=archive.read('작업서.txt').decode('utf-8');self.assertIn('한 파일씩',order);self.assertIn('다음 번호',order)
            names=[n for n in archive.namelist() if n.endswith('.json')];self.assertEqual(len(names),len(self.entries))
            for name,entry in zip(names,self.entries):
                value=json.loads(archive.read(name));self.assertEqual(value['output_example']['coverage'],entry['coverage'])
                self.assertNotIn('로컬 실명',archive.read(name).decode('utf-8'));self.assertNotIn(str(self.path),order)
        self.assertEqual(source.read_bytes(),before)
        self.assertIn('0~20개',exchange.prompt('detail'))

    def test_zip_partial_then_remaining_duplicate_and_preservation(self):
        first=self.payload(self.entries[:1]);p=batch.preview(self.path,'1',first)
        self.assertEqual(p['accepted'],1);self.assertFalse(p['complete']);self.assertTrue(p['missing'])
        old=batch.receive(self.path,'1',first|{'token':p['token']})
        old_file=exchange.local(self.path,f'runs/{old["run"]}/work.json');before=old_file.read_bytes()
        remaining=self.payload(self.entries[1:]);p=batch.preview(self.path,'1',remaining)
        self.assertTrue(p['complete']);new=batch.receive(self.path,'1',remaining|{'token':p['token']})
        self.assertNotEqual(new['run'],old['run']);self.assertEqual(old_file.read_bytes(),before)
        p=batch.preview(self.path,'1',remaining)
        self.assertTrue(batch.receive(self.path,'1',remaining|{'token':p['token']})['duplicate'])
        self.assertEqual(self.fixture.old.read_bytes(),self.fixture.before)

    def test_malformed_file_does_not_hide_good_and_requires_partial_consent(self):
        data={'archive':zipped([('good.json',json.dumps(self.entries[0])),('broken.json','{'),('__MACOSX/._good.json','metadata'),('.DS_Store','metadata')])}
        p=batch.preview(self.path,'1',data);self.assertEqual(p['accepted'],1);self.assertEqual(p['errors'][0]['file'],'broken.json')
        with self.assertRaisesRegex(ValueError,'부분 저장'):batch.receive(self.path,'1',data|{'token':p['token']})
        result=batch.receive(self.path,'1',data|{'token':p['token'],'allow_partial':True});self.assertTrue(result['run'])
        data={'archive':zipped([('bad.json',b'\xff')])};p=batch.preview(self.path,'1',data)
        self.assertEqual(p['accepted'],0);self.assertIn('UTF-8',p['errors'][0]['message'])

    def test_duplicate_chunk_all_conflicts_rejected_mixed_exports_rejected(self):
        e=self.entries[0];data={'archive':zipped([('a.json',json.dumps(e)),('b.json',json.dumps(e))])}
        p=batch.preview(self.path,'1',data);self.assertEqual(p['accepted'],0);self.assertEqual(len(p['errors']),2)
        with self.assertRaisesRegex(ValueError,'저장 가능한'):batch.receive(self.path,'1',data|{'token':p['token'],'allow_partial':True})
        data={'archive':zipped([('a.json',json.dumps(e)),('b.json',json.dumps(e|{'export_id':'f'*32}))])}
        with self.assertRaisesRegex(ValueError,'섞여'):batch.preview(self.path,'1',data)

    def test_schema_errors_and_token_changes_and_resume(self):
        bad=copy.deepcopy(self.entries[1]);bad['topics'][0]['evidence_ids']=['not-real']
        data=self.payload([self.entries[0],bad]);p=batch.preview(self.path,'1',data)
        self.assertEqual(p['accepted'],1);self.assertEqual(p['errors'][0]['chunk'],bad['chunk_id'])
        changed=self.payload(self.entries[:1])
        with self.assertRaisesRegex(ValueError,'다시 검사'):batch.receive(self.path,'1',changed|{'token':p['token']})
        exchange.cancel(self.path,self.bundle['id'])
        with self.assertRaisesRegex(ValueError,'작업 재개'):batch.preview(self.path,'1',data)
        exchange.resume(self.path,'1',self.bundle['id']);self.assertEqual(batch.preview(self.path,'1',data)['accepted'],1)
        exchange.cancel(self.path,self.bundle['id']);self.fixture.source['rows'][0]['text']='입력 수정'
        with self.assertRaisesRegex(ValueError,'재개할 수'):exchange.resume(self.path,'1',self.bundle['id'])
        self.assertTrue(read_json(exchange.folder(self.path,self.bundle['id'])/'manifest.json')['cancelled'])

    def test_unsafe_zip_paths_duplicates_symlinks_sizes_and_corruption(self):
        for name in ['../escape.json','/root.json','C:/root.json','folder\\file.json','a/../b.json']:
            with self.subTest(name=name),self.assertRaises(ValueError):zipper.unpack(zipped([(name,'{}')]))
        with self.assertRaisesRegex(ValueError,'중복'):zipper.unpack(zipped([('a.json','{}'),('A.JSON','{}')]))
        link=zipfile.ZipInfo('link.json');link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16
        with self.assertRaisesRegex(ValueError,'링크'):zipper.unpack(zipped([(link,'/tmp/target')]))
        with self.assertRaisesRegex(ValueError,'결과 JSON'):zipper.unpack(zipped([('작업서.txt','not a result')]))
        with self.assertRaises(ValueError):zipper.unpack('not base64')
        with self.assertRaises(ValueError):zipper.unpack(base64.b64encode(b'not zip').decode())
        compressed=zipped([('large.json',' '*20000)])
        with patch.object(zipper,'MAX_BYTES',1000),self.assertRaisesRegex(ValueError,'압축을 푼'):zipper.unpack(compressed)
        with patch.object(zipper,'MAX_MEMBERS',1),self.assertRaises(ValueError):zipper.unpack(zipped([('a.json','{}'),('b.json','{}')]))

    def test_legacy_json_and_utf8_bom_still_accepted(self):
        data={'text':'\ufeff'+json.dumps({'results':self.entries})};p=batch.preview(self.path,'1',data)
        self.assertEqual(p['accepted'],len(self.entries));self.assertEqual(p['errors'],[])
        with self.assertRaises(ValueError):batch.preview(self.path,'1',data|{'archive':'abc'})


if __name__=='__main__':unittest.main()
