"""Gemma 고유 템플릿·사고 모드를 쓰는 작업당 한 개의 로컬 추론 서버."""
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
from . import processes, compute
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from .source import check_cancel
from .storage import save_json

PROFILE={'backend':'llama-server','revision':1,'thinking':True,'thinking_budget':4096,
         'output':8192,'context':16384,'temperature':.6,'top_p':.95,'top_k':20,'seed':42}

def profile(thinking=True):
    if type(thinking) is not bool:raise ValueError('사고 모드는 켜기 또는 끄기여야 합니다')
    return dict(PROFILE) if thinking else PROFILE|{'revision':2,'thinking':False,'thinking_budget':0}

def boundary_profile(thinking=True, *, cache_prompt=False, thinking_budget=4096):
    if type(cache_prompt) is not bool or thinking_budget not in (4096,3072):raise ValueError('추론 비교 설정이 올바르지 않습니다')
    return profile(thinking)|{'revision':3,'thinking_budget':thinking_budget if thinking else 0,
                              'token_cache_entries':16,'cache_prompt':cache_prompt}

def supported(value):
    return value in [profile(True),profile(False)]+[boundary_profile(t,cache_prompt=c,thinking_budget=b)
        for t in (True,False) for c in (True,False) for b in (4096,3072)]

def messages(text):
    match=re.fullmatch(r'<\|im_start\|>system\n(.*?)<\|im_end\|>\n<\|im_start\|>user\n(.*?)<\|im_end\|>\n<\|im_start\|>assistant\n<think>\n\n</think>\n\n',text,re.S)
    if not match:raise ValueError('문맥 프롬프트 형식이 올바르지 않습니다')
    system,user=match.groups()
    system=re.sub(r' /no_think(?=$|\n직전 응답)', '', system)
    return [{'role':'system','content':system.rstrip()},
            {'role':'user','content':user.removesuffix('\n/no_think').rstrip()}]

class Server:
    output=PROFILE['output']
    def __init__(self,job,folder):
        self.profile=job.inference;self.output=self.profile['output'];self.job=job;self.folder=folder;self.cache={};self.seconds=0.;self.child=None;self.log=None
        self.tokenizer_requests=0;self.tokenizer_hits=0
        folder.mkdir(parents=True,exist_ok=False)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.url=f'http://127.0.0.1:{port}';self.key=secrets.token_urlsafe(32)
        self.http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.compute=getattr(job,'compute',None) or compute.select('llama-server')
        args=[self.compute['binary'],'-m',str(job.model_path),'--host','127.0.0.1','--port',str(port),
              '--offline','--no-webui','--api-key',self.key,'-c','16384','-np','1','-t','6',*self.compute['args'],
              '--jinja','--reasoning','on' if self.profile['thinking'] else 'off','--reasoning-format','deepseek','--reasoning-budget',str(self.profile['thinking_budget']),
              '--no-context-shift','--cache-ram','0']
        save_json(folder/'options.json',[x if x!=self.key else '[임시 인증키 생략]' for x in args])
        if compute.windows(): save_json(folder/'compute.json',self.compute)
        command=[sys.executable]
        if not getattr(sys,'frozen',False):command.append(str(Path(__file__).resolve().parents[1]/'app.py'))
        command.append('--context-worker')
        self.log=(folder/'engine.log').open('wb');begin=time.monotonic()
        try:
            self.child=processes.popen(command,stdin=subprocess.PIPE,stdout=self.log,stderr=self.log,lock_fd=job.lock.fd)
            self.child.stdin.write(json.dumps({'parent':os.getpid(),'lock_fd':processes.inherited_lock(job.lock.fd),'args':args}).encode())
            self.child.stdin.close()
            while True:
                check_cancel(job.stop)
                if self.child.poll() is not None:raise ValueError('Gemma 추론 서버 시작 실패: engine.log를 확인하세요'+compute.failure_hint(self.compute))
                try:
                    if self.request('/health',timeout=1).get('status')=='ok':break
                except (OSError,ValueError):pass
                if time.monotonic()-begin>120:raise ValueError('Gemma 모델 준비 제한 시간 2분을 넘었습니다')
                job.update(message='Gemma 4 E4B · 사고 '+('켜기' if self.profile['thinking'] else '끄기')+' · 모델 로딩 중',progress={'seconds':int(time.monotonic()-begin)})
                job.stop.wait(.25)
            save_json(folder/'ready.json',{'port':port,'load_seconds':round(time.monotonic()-begin,3),'inference':self.profile})
        except BaseException:
            self.close();raise

    def request(self,endpoint,body=None,timeout=900):
        request=urllib.request.Request(self.url+endpoint,data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+self.key})
        try:
            with self.http.open(request,timeout=timeout) as response:return json.load(response)
        except urllib.error.HTTPError as error:
            raise ValueError(f'로컬 추론 응답 오류 {error.code}: '+error.read().decode('utf-8','replace')[-400:]) from error

    def body(self,text):
        from .context_background import contextual_messages
        background=getattr(self.job,'input',{}).get('source',{}).get('broadcast_background','')
        return {'messages':contextual_messages(messages(text),background),'chat_template_kwargs':{'enable_thinking':self.profile['thinking']},'reasoning_format':'deepseek'}

    def count(self,text):
        check_cancel(self.job.stop)
        if text not in self.cache:
            begin=time.monotonic()
            try:
                formatted=self.request('/apply-template',self.body(text),30)['prompt']
                ids=self.request('/tokenize',{'content':formatted,'add_special':True,'parse_special':True},30)['tokens']
                self.cache[text]=(len(ids),formatted)
                self.tokenizer_requests=getattr(self,'tokenizer_requests',0)+1
                limit=self.profile.get('token_cache_entries')
                if limit and len(self.cache)>limit:del self.cache[next(iter(self.cache))]
            except (OSError,KeyError,TypeError) as error:raise ValueError('Gemma 토큰 계산에 실패했습니다') from error
            finally:self.seconds+=time.monotonic()-begin
        else:
            self.tokenizer_hits=getattr(self,'tokenizer_hits',0)+1
            if self.profile.get('token_cache_entries'):self.cache[text]=self.cache.pop(text)
        return self.cache[text][0]

    def infer(self,value,folder,prompt,schema):
        from .context_job import EngineError, FatalEngineError
        check_cancel(self.job.stop);count=self.count(prompt)
        if count+self.output+512>16384:raise EngineError('사고 출력 예약을 포함한 문맥 한도를 넘었습니다')
        folder.mkdir(parents=True,exist_ok=False)
        body=self.body(prompt)|{'model':'local','response_format':{'type':'json_schema','json_schema':{'name':'summary','strict':True,'schema':schema}},
            'max_tokens':self.output,'temperature':.6,'top_p':.95,'top_k':20,'min_p':0,'presence_penalty':0,
            'repeat_penalty':1,'seed':42,'cache_prompt':self.profile.get('cache_prompt',False),'stream':False}
        save_json(folder/'input.json',value);save_json(folder/'request.json',body)
        (folder/'prompt.txt').write_text(self.cache[prompt][1],encoding='utf-8')
        done=threading.Event();result={};begin=time.monotonic()
        def request():
            try:result['response']=self.request('/v1/chat/completions',body)
            except Exception as error:result['error']=error
            finally:done.set()
        threading.Thread(target=request,daemon=True).start();previous=-1
        while not done.wait(.25):
            check_cancel(self.job.stop)
            elapsed=int(time.monotonic()-begin)
            if elapsed>900 or self.child.poll() is not None:
                self.close();raise FatalEngineError('Gemma 응답 제한 시간을 넘었거나 추론 서버가 종료됐습니다. 완료 결과는 유지됩니다'+compute.failure_hint(getattr(self,'compute',{})))
            if elapsed!=previous:self.job.update(progress=self.job.value.get('progress',{})|{'seconds':elapsed});previous=elapsed
        check_cancel(self.job.stop)
        if 'error' in result:
            kind=FatalEngineError if isinstance(result['error'],OSError) or self.child.poll() is not None else EngineError
            raise kind('Gemma 로컬 추론 요청 실패: '+str(result['error'])) from result['error']
        response=result['response'];save_json(folder/'response.json',response)
        try:
            choice=response['choices'][0];message=choice['message']
            thought=message.get('reasoning_content') or '';answer=message.get('content') or ''
            (folder/'reasoning.txt').write_text(thought,encoding='utf-8');(folder/'answer.json').write_text(answer,encoding='utf-8')
            elapsed=round(time.monotonic()-begin,3)
            save_json(folder/'metrics.json',{'seconds':elapsed,'finish_reason':choice['finish_reason'],'prompt_tokens':count,
                'usage':response.get('usage'),'timings':response.get('timings'),'reasoning_chars':len(thought),'inference':self.profile})
            if choice['finish_reason']=='length':
                from .context_job import OutputLimitError
                raise OutputLimitError('Gemma 출력 상한에 도달했습니다. 입력 묶음을 나누어 확인합니다')
            if choice['finish_reason']!='stop':raise EngineError('Gemma 출력이 끝나지 않았습니다. 완료 결과는 유지됩니다')
            if self.profile['thinking'] and not thought.strip():raise EngineError('Gemma 사고 출력이 확인되지 않았습니다')
            return json.loads(answer),elapsed
        except (KeyError,IndexError,TypeError) as error:raise EngineError('Gemma 응답 형식이 올바르지 않습니다') from error

    def close(self):
        if self.child and self.child.poll() is None:
            processes.stop(self.child, timeout=8)
        if self.log:self.log.close()
