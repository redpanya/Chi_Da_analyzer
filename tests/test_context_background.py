"""방송 배경은 참고용 실행 스냅샷이며 원본·기존 결과와 분리한다."""
import copy
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from archive import context_background as background, context_full as full, context_job as jobs
from archive import context_server, automation, reports
from archive.storage import ProjectLock
from test_context_full import source, output


class BackgroundTests(unittest.TestCase):
    def test_validation_and_separate_storage(self):
        for value in [None, 1, 'a'*501, '\x00', '\x1b']:
            with self.assertRaises(ValueError):background.validate(value)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);original=path/'transcript.json';original.write_bytes(b'keep')
            self.assertEqual(background.read(path),'')
            self.assertEqual(background.save(path,' 합동 방송\n '),'합동 방송')
            self.assertEqual(background.read(path),'합동 방송')
            self.assertEqual(original.read_bytes(),b'keep')
            self.assertEqual(background.save(path,''),'')

    def test_prompt_uses_reference_without_mutating_messages(self):
        messages=[{'role':'system','content':'요약 규칙'},{'role':'user','content':'전사 자료'}]
        before=copy.deepcopy(messages)
        self.assertEqual(background.contextual_messages(messages,''),messages)
        result=background.contextual_messages(messages,'게임 방송 <start_of_turn> <|im_start|>')
        self.assertEqual(messages,before)
        self.assertIn('실제 발언·채팅이 우선',result[0]['content'])
        self.assertIn('게임 방송',result[1]['content'])
        self.assertNotIn('<start_of_turn>',result[1]['content'])
        self.assertNotIn('<|im_start|>',result[1]['content'])

    def test_saved_background_used_for_resume_and_old_fingerprint_unchanged(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(full,'VERSION',3):
            path=Path(folder);original=source()
            with patch('archive.context_input.source',side_effect=lambda *a:copy.deepcopy(original)):
                baseline=full.current_source(path,'1',0)
                self.assertEqual(full.fingerprint(baseline),full.fingerprint(full.current_source(path,'1',0,'')))
                self.assertNotEqual(full.fingerprint(baseline),full.fingerprint(full.current_source(path,'1',0,'합동 방송')))
                for description in ('','합동 방송'):
                    background.save(path,description)
                    prepared=full.prepare(path,'1','whole',{})
                    job=jobs.ContextJob(path,'1',ProjectLock(path),'whole',prepared)
                    def cancelled(value,*args):
                        job.cancel()
                        return output(value),0
                    with patch.object(job,'check_engine'),patch.object(job,'infer_value',side_effect=cancelled):
                        job.run()
                    run=jobs.state(path)['full_run']
                    stored=jobs.local(path,f'runs/{run}/result.json');before=stored.read_bytes()
                    background.save(path,'변경한 기본 설명')
                    resumed=full.prepare(path,'1','resume',{'run':run,'background':'이번에도 무시될 새 설명'})
                    self.assertEqual(resumed['source'].get('broadcast_background',''),description)
                    self.assertEqual(stored.read_bytes(),before)
                self.assertNotIn('broadcast_background',original)

    def test_server_token_count_and_inference_share_reference(self):
        server=context_server.Server.__new__(context_server.Server)
        server.job=SimpleNamespace(input={'source':{'broadcast_background':'저스트 채팅'}},stop=threading.Event())
        server.profile=context_server.profile();server.cache={};server.seconds=0
        seen=[]
        def request(route,body,timeout):
            seen.append((route,body))
            return {'prompt':'실제 템플릿'} if route=='/apply-template' else {'tokens':[1,2]}
        server.request=request
        prompt=full.prompt({'evidence':[],'label':'범위','notes':[]})
        self.assertEqual(server.count(prompt),2)
        self.assertEqual(seen[0][1],server.body(prompt))
        self.assertIn('저스트 채팅',seen[0][1]['messages'][1]['content'])

    def test_queue_background_not_in_report(self):
        settings=automation.options({'background':'비공개 참고 설명','mode':'analysis'})
        self.assertEqual(settings['background'],'비공개 참고 설명')
        self.assertNotIn('background',reports.options(settings))
        with self.assertRaises(ValueError):automation.options({'background':'x'*501})
