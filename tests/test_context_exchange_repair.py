"""미수신/오류 보완 ZIP의 원래 ID·스냅샷·기존 결과 보존 계약."""
import base64
import copy
import io
import json
import unittest
import zipfile
import test_context_exchange
from archive import context_exchange as exchange, context_exchange_batch as batch, context_exchange_zip as zipper


def files(packed):
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(packed['base64']))) as archive:
        return {name:archive.read(name) for name in archive.namelist()}


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_context_exchange.ExchangeTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.path=self.fixture.path;self.bundle=self.fixture.create();self.entries=self.fixture.responses(self.bundle)

    def snapshot(self):
        return {str(p.relative_to(self.path)):p.read_bytes() for p in self.path.rglob('*') if p.is_file()}

    def test_saved_missing_keeps_original_workorder_documents_and_every_file(self):
        self.fixture.receive(self.entries[:1])
        before=self.snapshot();full=files(zipper.pack(self.path,self.bundle['id']))
        packed=zipper.repair(self.path,'1',self.bundle['id']);repair=files(packed)
        self.assertEqual(packed['chunks'],[e['chunk_id'] for e in self.entries[1:]])
        self.assertEqual(repair['작업서.txt'],full['작업서.txt'])
        self.assertIn('이번 보완에서는',repair['먼저읽기-보완요청.txt'].decode())
        self.assertEqual(len([n for n in repair if n.endswith('.json')]),len(self.entries)-1)
        for name,content in repair.items():
            if name.endswith('.json'):self.assertEqual(content,full[name])
        self.assertEqual(before,self.snapshot())

    def test_preview_errors_keep_valid_inputs_excluded_and_recheck_token(self):
        broken=copy.deepcopy(self.entries[1]);broken['topics'][0]['evidence_ids']=['MISSING']
        payload={'text':json.dumps({'results':[self.entries[0],broken]})};preview=batch.preview(self.path,'1',payload)
        before=self.snapshot();packed=batch.repair(self.path,'1',payload|{'token':preview['token']})
        self.assertEqual(packed['chunks'],preview['missing']);self.assertNotIn(self.entries[0]['chunk_id'],packed['chunks'])
        self.assertEqual(before,self.snapshot())
        with self.assertRaisesRegex(ValueError,'다시 검사'):batch.repair(self.path,'1',payload|{'token':'changed'})
        self.fixture.receive(self.entries[:1])
        with self.assertRaisesRegex(ValueError,'다시 검사'):batch.repair(self.path,'1',payload|{'token':preview['token']})

    def test_repair_then_receive_keeps_prior_result_and_merges_new_version(self):
        first=self.fixture.receive(self.entries[:1]);old=self.path/'context/runs'/first['run']/'work.json';before=old.read_bytes()
        packed=zipper.repair(self.path,'1',self.bundle['id']);wanted=set(packed['chunks'])
        final=self.fixture.receive([e for e in self.entries if e['chunk_id'] in wanted])
        self.assertNotEqual(first['run'],final['run']);self.assertEqual(before,old.read_bytes())
        with self.assertRaisesRegex(ValueError,'미수신 묶음이 없습니다'):zipper.repair(self.path,'1',self.bundle['id'])

    def test_cancelled_changed_and_unknown_export_are_not_silently_rebuilt(self):
        exchange.cancel(self.path,self.bundle['id'])
        with self.assertRaisesRegex(ValueError,'취소'):zipper.repair(self.path,'1',self.bundle['id'])
        exchange.resume(self.path,'1',self.bundle['id']);self.fixture.source['rows'][0]['text']='변경된 전사'
        with self.assertRaisesRegex(ValueError,'입력이 바뀌'):zipper.repair(self.path,'1',self.bundle['id'])
        with self.assertRaises(ValueError):zipper.repair(self.path,'1','../wrong')

    def test_all_three_modes_keep_input_documents_including_clip_neighbors_and_chat(self):
        for mode in ('timestamps','detail','clips'):
            with self.subTest(mode=mode):
                bundle=self.fixture.create(mode,chat=mode!='timestamps');before=self.snapshot()
                full=files(zipper.pack(self.path,bundle['id']));repaired=files(zipper.repair(self.path,'1',bundle['id']))
                for name,content in full.items():self.assertEqual(content,repaired[name])
                self.assertEqual(before,self.snapshot())

    def test_unidentified_corrupt_json_requires_saved_export_selection(self):
        with self.assertRaisesRegex(ValueError,'외부 작업 목록'):batch.repair(self.path,'1',{'text':'{','token':None})

class RepairHttpTests(unittest.TestCase):
    def setUp(self):
        import test_context_exchange_http
        self.http=test_context_exchange_http.ExchangeHttpTests();self.http.setUp();self.addCleanup(self.http.doCleanups)

    def test_readonly_http_repair_large_input_and_origin_token_checks(self):
        reply=self.http.prepare();export_id=reply['export_id'];post=self.http.post
        before={str(p):p.read_bytes() for p in self.http.path.rglob('*') if p.is_file()}
        status,packed=post('context-exchange-repair-archive',{'export_id':export_id})
        self.assertEqual(status,200);self.assertEqual(packed['chunks'],['001'])
        reply['topics'][0]['evidence_ids']=['missing']
        payload={'text':json.dumps(reply)+' '*70000}
        status,preview=post('context-exchange-check-files',payload);self.assertEqual(status,200)
        status,packed=post('context-exchange-repair-files',payload|{'token':preview['token']})
        self.assertEqual(status,200);self.assertEqual(packed['chunks'],['001'])
        status,_=post('context-exchange-repair-files',payload|{'token':'stale'});self.assertEqual(status,409)
        status,_=post('context-exchange-repair-files',payload|{'token':preview['token']},origin='https://example.invalid');self.assertEqual(status,403)
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.http.path.rglob('*') if p.is_file()})
