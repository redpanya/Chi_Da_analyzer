"""네이티브 템플릿과 사고 출력·미완료 응답·취소의 계약 검사."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from archive.context_server import Server,messages,profile
from archive.context_topic_summary import prompt
from archive.context_job import EngineError
from archive.source import Cancelled

class ServerTests(unittest.TestCase):
    def test_native_messages_remove_control_but_keep_quoted_data(self):
        text=prompt('요약한다.',{'발언':'/no_think 라고 말했다'})
        text=text.replace('<|im_end|>\n<|im_start|>user','\n직전 응답 검사를 통과하지 못했습니다.<|im_end|>\n<|im_start|>user',1)
        rows=messages(text)
        self.assertNotIn('/no_think',rows[0]['content'])
        self.assertIn('/no_think 라고 말했다',rows[1]['content'])
        self.assertFalse(rows[1]['content'].endswith('/no_think'))
        with self.assertRaises(ValueError):messages('임의 템플릿')
    def server(self,response):
        server=Server.__new__(Server);server.profile=profile();server.cache={};server.count=lambda text:100
        server.body=lambda text:{'messages':[],'chat_template_kwargs':{'enable_thinking':True}}
        server.job=SimpleNamespace(stop=threading.Event(),value={},update=lambda **kw:None)
        server.child=SimpleNamespace(poll=lambda:None)
        server.request=lambda *args:response
        server.cache['입력']=(100,'모델 고유 프롬프트')
        return server
    def test_response_requires_actual_thinking_and_complete_output(self):
        for thought,finish,valid in [('검토','stop',True),('','stop',False),('검토','length',False)]:
            server=self.server({'choices':[{'finish_reason':finish,'message':{'reasoning_content':thought,'content':'{"items":[]}'}}]})
            with tempfile.TemporaryDirectory() as folder:
                call=lambda:server.infer({},Path(folder)/'요청','입력',{})
                if valid:self.assertEqual(call()[0],{'items':[]})
                else:
                    with self.assertRaises(EngineError):call()
    def test_cancellation_does_not_wait_for_full_http_timeout(self):
        server=self.server(None);release=threading.Event()
        server.request=lambda *args:release.wait(2)
        timer=threading.Timer(.05,server.job.stop.set);timer.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(Cancelled):server.infer({},Path(folder)/'요청','입력',{})
        finally:release.set();timer.join()

    def test_thinking_off_accepts_completed_plain_response(self):
        server=self.server({'choices':[{'finish_reason':'stop','message':{'content':'{"items":[]}'}}]})
        server.profile=profile(False)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(server.infer({},Path(folder)/'요청','입력',{})[0],{'items':[]})
