"""VOD별 로컬 요약 작업·버전·취소. 전사와 채팅에는 쓰지 않는다."""
import json
import re
import shutil
import subprocess
from . import processes
import threading
import time
import uuid
from . import context_input as inputs, context_model as model
from .source import Cancelled, check_cancel, safe_error
from .storage import read_json, save_json, stamp
from . import task_timing


class EngineError(ValueError):
    """새 처리 경로가 요청 단위로 복구할 수 있는 추론 오류."""

class FatalEngineError(EngineError):
    """같은 서버에 재요청해서 복구할 수 없는 종료·접속 오류."""

class OutputLimitError(EngineError):
    """엔진이 출력 토큰 상한에 도달해 응답을 끝내지 못했다."""


def local(path, relative):
    target=path/'context'/relative
    if not target.resolve().is_relative_to((path/'context').resolve()):raise ValueError('문맥 자료 경로가 올바르지 않습니다')
    for p in (target,*target.parents):
        if p==path:break
        if p.is_symlink():raise ValueError('문맥 자료의 연결 파일은 지원하지 않습니다')
    return target

def state(path):
    file=local(path,'state.json')
    return read_json(file) if file.exists() else {'state':'idle','message':'전체 영상의 전사와 채팅을 시간순 문맥으로 정리하세요','runs':[],'run':None}

def view(path, locked=False, owned=False):
    saved=state(path)
    if saved['state'] in ('running','stopping') and not locked:
        saved=task_timing.interrupted(saved)|{'state':'paused','message':'이전 요약 작업이 중단됐습니다. 완료 요약은 유지됩니다. 전체 문맥은 이어서 정리할 수 있습니다'}
    from .context_catalog import MODELS
    return saved|{'owned':owned,'model':model.status(),'models':[model.status(name) for name in dict.fromkeys([model.DEFAULT_NAME,model.NAME,*MODELS])]}

def result(path, vod, id=None):
    saved=state(path);id=id or saved.get('run')
    if not id:return None
    if not isinstance(id,str) or not re.fullmatch(r'[a-f0-9]{32}',id) or id not in [r['id'] for r in saved['runs']]:raise ValueError('저장된 요약 버전이 아닙니다')
    if next(r for r in saved['runs'] if r['id']==id).get('scope')=='full':
        from . import context_full
        return context_full.result(path,vod,id)
    value=read_json(local(path,f'runs/{id}/result.json'))
    try:stale=inputs.build(path,vod,value['input']['range'])['fingerprint']!=value['input']['fingerprint']
    except (ValueError,OSError,KeyError,TypeError):stale=True
    return value|{'stale':stale}


class ContextJob:
    def __init__(self,path,vod,lock,action,value=None):
        self.path,self.vod,self.lock,self.action,self.input=path,vod,lock,action,value
        self.model_info=model.spec((value or {}).get('model_name') or (model.NAME if action=='summarize' else None))
        self.model_path=model.model_path(self.model_info['name'])
        self.inference=(value or {}).get('inference');self.server=None
        from . import context_tokens
        self.output_tokens=self.inference['output'] if self.inference else context_tokens.OUTPUT
        self.stop=threading.Event();self.closed=False
        previous=state(path)
        resume=action=='resume' and previous.get('action') in ('whole','resume') and previous.get('full_run')==value['saved']['id']
        self.value=previous|{'state':'running','action':action,'message':'요약 작업 준비 중','progress':{},
                             'timing':task_timing.start(previous,resume=resume)}
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.update()
    def cancel(self):self.stop.set()
    def update(self,**values):
        self.value=task_timing.update(self.value,values)|{'updated_at':stamp()};save_json(local(self.path,'state.json'),self.value)
    def check_engine(self):
        started=time.monotonic()
        model.model_paths.available()
        if not model.status(self.model_info['name'])['ready']:raise ValueError('요약 모델 준비·검사를 먼저 실행하세요')
        hash_started=time.monotonic()
        if model.digest(self.model_path)!=self.model_info['sha256']:raise ValueError('요약 모델이 변경됐습니다. 모델 준비를 다시 실행하세요')
        self.model_hash_seconds=time.monotonic()-hash_started
        binary=shutil.which('llama-server' if self.inference else 'llama-completion')
        if not binary:raise ValueError('로컬 요약 엔진이 없습니다. 앱을 다시 설치하세요')
        version=subprocess.run([binary,'--version'],capture_output=True,text=True,timeout=15,check=True)
        self.engine_version=(version.stdout+version.stderr).strip()
        if shutil.disk_usage(self.path).free<128*1024**2:raise OSError('요약 결과 저장 공간이 부족합니다')
        self.preflight_seconds=time.monotonic()-started
        if self.inference:
            from .context_server import Server,supported
            if not supported(self.inference):raise ValueError('저장된 사고 설정과 현재 엔진 설정이 다릅니다. 새 정리를 시작하세요')
            self.server=Server(self,local(self.path,'engines/'+uuid.uuid4().hex))
        return binary
    def make_tokenizer(self):
        from .context_tokens import Tokenizer
        return self.server or Tokenizer(self.model_path,self.stop)
    def contract(self):
        from . import context_tokens,context_dialogue_model
        value={'engine':getattr(self,'engine_version','검증 모형'),'context':context_tokens.CONTEXT,
               'target':context_tokens.TARGET,'output':self.output_tokens,'margin':context_tokens.MARGIN,
               'tokenizer':'llama-server/native-template' if self.inference else 'llama-tokenize',
               'prompt_revision':context_dialogue_model.REVISION,'input_revision':1}
        if self.input.get('speaker_policy'):
            value.update(speaker_policy=self.input['speaker_policy'],input_revision=3)
        if self.input.get('version')==8:
            from .context_boundary import REVISION
            value.update(prompt_revision=REVISION,input_revision=2,pipeline_version=8,
                         input_policy={'lookahead_rows':4,'lookahead_tokens':256,'reference_tokens':768,'references':6,'fit':'bounded-v1'})
        if self.input.get('version')==9:
            from .context_grounded import REVISION
            value.update(prompt_revision=REVISION,input_revision=4,pipeline_version=9)
        if self.input.get('version')==10:
            from .context_adaptive import REVISION
            value.update(prompt_revision=REVISION,input_revision=5,pipeline_version=10,interpretation_policy=1)
        return value|{'inference':self.inference} if self.inference else value
    def infer_value(self,value,folder,prompt=None,schema=None):
        if self.server:return self.server.infer(value,folder,prompt,schema)
        binary=shutil.which('llama-completion')
        folder.mkdir(parents=True,exist_ok=False)
        save_json(folder/'input.json',value)
        (folder/'prompt.txt').write_text(prompt or inputs.prompt(value),encoding='utf-8')
        save_json(folder/'schema.json',schema or inputs.schema(value['evidence']))
        args=[binary,'-m',str(self.model_path),'-f',str(folder/'prompt.txt'),'-jf',str(folder/'schema.json'),
              '--offline','--no-conversation','--no-display-prompt','--color','off','--no-context-shift',
              '-c','16384','-n','3600','-t','6','-ngl','99','--temp','0.2','--seed','42']
        started=time.monotonic()
        with (folder/'raw.txt').open('wb') as output,(folder/'engine.log').open('wb') as log:
            child=processes.popen(args,stdout=output,stderr=log,stdin=subprocess.DEVNULL,lock_fd=self.lock.fd)
            try:
                while child.poll() is None:
                    if self.stop.wait(1):raise Cancelled()
                    elapsed=round(time.monotonic()-started)
                    if elapsed>900:raise EngineError('요약 처리 제한 시간 15분을 넘었습니다. 구간을 줄여 다시 시도하세요')
                    self.update(progress=self.value.get('progress',{})|{'seconds':elapsed})
                check_cancel(self.stop)
                if child.returncode:raise EngineError(f'로컬 요약 엔진 오류({child.returncode}). 메모리와 해당 요약의 engine.log를 확인하세요')
            finally:
                processes.stop(child, timeout=5)
        raw=(folder/'raw.txt').read_text(encoding='utf-8').strip()
        # completion 실행기가 EOS 뒤에 붙이는 표시만 제외하며 다른 출력은 검사에서 거부한다.
        raw=raw.removesuffix('[end of text]').strip()
        return json.loads(raw),round(time.monotonic()-started,1)
    def infer(self):
        self.check_engine()
        id=uuid.uuid4().hex;folder=local(self.path,f'runs/{id}')
        raw,seconds=self.infer_value(self.input,folder)
        summary=inputs.validate(raw,self.input['evidence'])
        check_cancel(self.stop)
        if inputs.build(self.path,self.vod,self.input['range'])['fingerprint']!=self.input['fingerprint']:
            raise ValueError('요약 중 입력 자료가 바뀌었습니다. 현재 자료로 다시 생성하세요')
        value={'id':id,'created_at':stamp(),'input':self.input,'model':model.NAME,'model_sha256':model.SHA256,
               'seconds':seconds,'summary':summary}
        save_json(folder/'result.json',value)
        check_cancel(self.stop)
        self.update(run=id,runs=self.value['runs']+[{'id':id,'label':self.input['label'],'title':summary['title']}])
    def run(self):
        try:
            problems=0
            if self.action=='model':model.prepare(self.stop,self.update,self.model_info['name'])
            elif self.action in ('whole','resume'):
                from . import context_full
                problems=context_full.run(self) or 0
            else:self.infer()
            self.update(state='review' if problems else 'complete',message=f'문맥 처리 종료 · 확인 필요 {problems}개. 완료 요약은 사용 가능하며 이어하기로 재검토하세요' if problems else '요약 모델 준비 완료' if self.action=='model' else '문맥 정리 완료 · 원문과 근거를 확인하세요')
            if problems and (self.input or {}).get('version') in (8,9,10):
                self.update(message=f'문맥 처리 종료 · 확인 필요 {problems}개. 근거 확인 표시는 원문에서 검토하세요. 실패 범위만 이어하기로 재검토합니다.')
        except Exception as error:
            try:self.update(state='paused' if self.stop.is_set() or isinstance(error,Cancelled) else 'error',message='요약 작업 중단 · 완료 결과는 유지합니다' if self.stop.is_set() or isinstance(error,Cancelled) else safe_error(error))
            except OSError:pass
        finally:
            try:
                if self.server:self.server.close()
            finally:self.lock.close();self.closed=True
