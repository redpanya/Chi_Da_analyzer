"""편집 초안·출력 이력·범위 작업. 원본 결과와 별도의 저장소와 프로젝트 잠금."""
from . import error_log
from contextlib import ExitStack
import copy
import re
import threading
import time
import uuid
from . import clip_contract, clip_captions, clip_render, analysis_inputs, studio_space, studio_maintenance
from .storage import project_path, load_project, ProjectLock, Conflict, read_json, save_json, stamp, asset_path
from .source import Cancelled, safe_error
from . import caption_fonts, caption_design, caption_styles, caption_templates, studio_decorations, studio_images


def local(path,relative):
    target=path/'studio'/relative
    if not target.resolve().is_relative_to((path/'studio').resolve()):raise ValueError('편집 경로를 확인하세요')
    for item in (target,*target.parents):
        if item==path:break
        if item.is_symlink():raise Conflict('편집 자료에 연결 파일은 사용할 수 없습니다')
    return target


def run_file(path,id):
    if not isinstance(id,str) or not re.fullmatch('[0-9a-f]{32}',id):raise ValueError('작업 목록에서 선택하세요')
    return local(path,f'runs/{id}/manifest.json')


class Studio:
    def __init__(self,manager):
        self.manager=manager;self.job=None

    def idle(self):
        if self.job and not self.job.closed:raise Conflict('클립 또는 범위 처리 중입니다. 완료·중단 후 진행하세요')

    def close(self):
        if self.job and not self.job.closed:self.job.stop.set();self.job.thread.join()

    def list(self,path):
        result=[]
        for file in local(path,'runs').glob('*/manifest.json'):
            try:
                item=read_json(run_file(path,file.parent.name))
                if self.job and not self.job.closed and self.job.file==file:item=item|{'elapsed_seconds':round(self.job.elapsed+time.monotonic()-self.job.started,1)}
                if item['state']=='running' and not (self.job and not self.job.closed and self.job.file==file):item=item|{'state':'paused','message':'이전 실행이 종료됐습니다. 이어하기를 누르세요'}
                view={k:v for k,v in item.items() if k not in ('request','captions')}
                view['folder']=str(file.parent)
                view['output_bytes']=sum(o.get('verification',{}).get('bytes',0) for o in item.get('outputs',{}).values())
                if item.get('kind')!='start':view['range_ms']=[item['request']['start_ms'],item['request']['end_ms']]
                result.append(view)
            except (ValueError,OSError,KeyError):continue
        return sorted(result,key=lambda r:r['created_at'],reverse=True)

    def dispatch(self,action,data):
        if action in ('template-list','template-save','template-delete'):
            return caption_templates.dispatch(action.removeprefix('template-'), data)
        path=project_path(data['root'],data['vod_id']);load_project(path,data['vod_id'])
        if action=='info':
            draft=local(path,'draft.json')
            return {'inputs':analysis_inputs.catalog(path),'draft':read_json(draft) if draft.exists() else None,'runs':self.list(path),
                    'caption_designs':caption_design.catalog(caption_styles.PRESETS)}
        if action=='status':return {'runs':self.list(path)}
        if action=='fonts':return studio_decorations.catalog(data.get('refresh') is True)
        if action=='decoration-preview':return studio_decorations.preview(path,data)
        if action=='image-preview':return studio_images.preview(path,data.get('asset'))
        if action=='space':
            src=clip_contract.media(path,data['vod_id']);request=clip_contract.validate(data['request'],src)
            studio_decorations.prepare(path,request['options'],request.get('selection'))
            rows=clip_captions.snapshot(path,data['vod_id'],request['selection']) if request['options']['caption'] else []
            count=sum(any(r['start_ms']<c['end_ms'] and r['end_ms']>c['start_ms'] for c in request['clips']) for r in rows)
            return studio_space.preflight(path,src,request,count)
        if action=='captions':return {'rows':clip_captions.snapshot(path,data['vod_id'],data.get('selection'))}
        if action=='stop':
            if self.job and not self.job.closed and self.job.path==path:self.job.stop.set()
            return {'runs':self.list(path)}
        with self.manager.guard:
            self.manager.speech_idle()
            if action=='image-add':
                with ProjectLock(path):return studio_images.add(path,data.get('png'),data.get('name'))
            if action in ('clean-preview','clean'):
                with ExitStack() as locks:
                    locks.enter_context(ProjectLock(path))
                    file=run_file(path,data['run'])
                    from .studio_range_cleanup import child_path
                    child=child_path(file)
                    child_lock=locks.enter_context(ProjectLock(child)) if child is not None and child.exists() else None
                    if action=='clean-preview':return studio_maintenance.preview(path,file,data['mode'])
                    if child_lock is not None and data['mode']=='delete':locks.enter_context(child_lock.moving())
                    return studio_maintenance.clean(path,file,data['mode'],data.get('token'))
            if action=='draft':
                with ProjectLock(path):
                    target=local(path,'draft.json');old=read_json(target) if target.exists() else {'revision':0}
                    if data.get('revision',0)!=old['revision']:raise Conflict('다른 창에서 초안이 변경됐습니다. 다시 불러온 뒤 저장하세요')
                    request=clip_contract.validate(data['request'],clip_contract.media(path,data['vod_id']),draft=True)
                    value={'revision':old['revision']+1,'request':request,'updated_at':stamp()}
                    if target.exists():save_json(local(path,f'drafts/{uuid.uuid4().hex}.json'),old)
                    save_json(target,value);return value
            if action not in ('start','scope','resume','remote'):raise ValueError('알 수 없는 편집 작업입니다')
            lock=ProjectLock(path)
            try:
                if action=='resume':
                    file=run_file(path,data['run']);saved=read_json(file)
                    if saved['state']=='complete':lock.close();return saved
                else:
                    src=clip_contract.media(path,data['vod_id']) if action!='remote' else None
                    request=data['request']
                    if action=='start':
                        request=clip_contract.validate(request,src)
                        if request['options']['caption'] or (request['options']['sidecar'] and request.get('selection')):
                            request['options']=caption_fonts.frozen_options(request['options'])
                        rows=clip_captions.snapshot(path,data['vod_id'],request['selection'],request['caption_edits'])
                        studio_decorations.prepare(path,request['options'],request.get('selection'))
                        if request['options']['caption'] and not rows:raise ValueError('영상에 입힐 완료된 전사를 선택하세요')
                        count=sum(any(r['start_ms']<c['end_ms'] and r['end_ms']>c['start_ms'] for c in request['clips']) for r in rows)
                        space=studio_space.preflight(path,src,request,count);studio_space.available(path,space['required_min'])
                    else:
                        from .range_jobs import validate
                        from .context_background import read as background
                        request=validate(request,src,load_project(path,data['vod_id']),remote=action=='remote');rows=[]
                        request['settings'].setdefault('background',background(path))
                    id=uuid.uuid4().hex;file=run_file(path,id)
                    saved={'id':id,'kind':action,'created_at':stamp(),'state':'paused','request':request,'source':src['identity'] if src else None,'outputs':{},'completed_stages':[], 'elapsed_seconds':0}
                    if action=='start':
                        saved['space_estimate']=space
                        save_json(file.parent/'captions.json',rows)
                    save_json(file,saved)
                self.job=Work(path,data['vod_id'],file,saved,lock)
                self.job.update(state='running',message='작업 준비',progress=0)
                self.job.thread.start()
            except Exception:lock.close();raise
            return {k:v for k,v in self.job.value.items() if k!='request'}

    def file(self,path,id,key):
        value=read_json(run_file(path,id));parts=key.split(':')
        if len(parts)!=2 or parts[0] not in value['outputs'] or parts[1] not in ('video','srt','ass'):raise ValueError('완성된 출력 파일이 아닙니다')
        name=value['outputs'][parts[0]]['assets'][parts[1]]
        file=local(path,f'runs/{id}/{name}')
        return asset_path(path,str(file.relative_to(path)))


class Work:
    def __init__(self,path,vod,file,value,lock):
        self.path,self.vod,self.file,self.value,self.lock=path,vod,file,value,lock
        self.stop=threading.Event();self.closed=False;self.thread=threading.Thread(target=self.run,daemon=True)
        self.started=time.monotonic();self.elapsed=value.get('elapsed_seconds',0);self.last_save=0

    def update(self,**values):
        self.value.update(values,updated_at=stamp(),elapsed_seconds=round(self.elapsed+time.monotonic()-self.started,1))
        if set(values)=={'progress'} and time.monotonic()-self.last_save<1:return
        save_json(self.file,self.value);self.last_save=time.monotonic()

    def run(self):
        try:
            self.update(state='running',message='작업 준비',progress=0)
            if self.value['kind']=='start':
                src=clip_contract.media(self.path,self.vod)
                # 과거 작업도 기본값을 보충하고, 재개 시 이미지·글꼴 존재 여부를 다시 확인한다.
                request=self.value['request'];options=request.get('options',{})
                if options.get('caption') or (options.get('sidecar',True) and request.get('selection')):
                    request=dict(request,options=caption_fonts.frozen_options(options))
                self.value['request']=clip_contract.validate(request,src)
                src['overlay']=studio_decorations.prepare(self.path,self.value['request']['options'],self.value['request'].get('selection'))
                if src['identity']!=self.value['source']:raise ValueError('원본 영상이 변경됐습니다. 새 작업으로 시작하세요')
                clip_render.render(self.file.parent,src,self.value['request'],read_json(self.file.parent/'captions.json'),self.stop,self.lock,self.update,self.value['outputs'])
                if clip_contract.media(self.path,self.vod)['identity']!=self.value['source']:raise ValueError('작업 중 원본 영상이 변경됐습니다. 결과를 확인하세요')
            else:
                from .range_jobs import execute
                execute(self)
            self.update(state='complete',message='처리와 출력 검사 완료',progress=1)
        except Exception as error:
            if not self.stop.is_set() and not isinstance(error,Cancelled): error_log.record('studio-'+self.value['kind'],error,path=self.path)
            try:self.update(state='paused' if self.stop.is_set() or isinstance(error,Cancelled) else 'error',message='중단했습니다. 완료 자료를 보존했습니다' if self.stop.is_set() else safe_error(error))
            except OSError:pass
        finally:self.lock.close();self.closed=True
