"""범위별 독립 프로젝트와 기존 분석 단계 연결. 부모 자료에는 쓰지 않는다."""
import copy
import json
import os
import shutil
import uuid
from types import SimpleNamespace
from . import clip_contract, clip_render, analysis_inputs, speech_media, speech_store, voice_store
from . import automation, automation_plan, automation_steps, analysis_store, context_background
from .storage import load_project, create_or_load, ProjectLock, save_json, read_json, stamp, asset_path
from .source import check_cancel


def validate(value,src,data,remote=False):
    if not isinstance(value,dict):raise ValueError('범위 설정을 확인하세요')
    origin=0 if remote else src['origin'];duration=round(data['metadata']['duration']*1000) if remote else src['duration']
    a=round(clip_contract.number(value.get('start_ms'),origin,origin+duration,'시작'))
    b=round(clip_contract.number(value.get('end_ms'),a+1000,origin+duration,'끝'))
    if b-a>20*3600000:raise ValueError('한 번에 최대 20시간까지 처리할 수 있습니다')
    raw=value.get('settings',{})
    only_download=remote and isinstance(raw,dict) and raw.get('steps')==[]
    settings=automation.options(raw|{'steps':['audio']} if only_download else raw)
    if only_download:settings['steps']=[]
    if 'download' in settings['steps']:raise ValueError('범위 처리의 다운로드는 별도로 선택하세요')
    selection=value.get('selection')
    if selection is not None:
        if not isinstance(selection,dict):raise ValueError('전사 버전을 선택하세요')
        analysis_inputs.run_id(selection.get('transcript_run'))
        if selection.get('speaker_run') is not None:analysis_inputs.run_id(selection['speaker_run'])
    if 'transcribe' not in settings['steps'] and any(k in settings['steps'] for k in ('diarize','context')) and selection is None:raise ValueError('새 전사를 선택하거나 재사용할 완료 전사를 선택하세요')
    if remote and selection is not None:raise ValueError('서버에서 새로 받을 구간에는 새 전사를 선택하세요')
    return {'start_ms':a,'end_ms':b,'settings':settings,'selection':selection}


def filtered_chat(parent,path,data,a,b,stop):
    old=data['tasks']['chat'];file=old.get('assets',{}).get('jsonl')
    state=old.get('state') if old.get('state') in ('complete','empty','unavailable') else 'review'
    if not file:return {'state':'unavailable','message':'이 범위에 복사할 저장 채팅이 없습니다','assets':{},'progress':{}}
    folder=path/'exports';folder.mkdir(exist_ok=True);target=folder/'chat.jsonl';count=0
    with target.with_suffix('.part').open('w',encoding='utf-8') as out:
        for row in analysis_store.rows(parent,data):
            check_cancel(stop);at=row.get('vod_offset_ms',row['offset_ms'])
            if a<=at<b:
                out.write(json.dumps(row|{'offset_ms':at},ensure_ascii=False)+'\n');count+=1
    target.with_suffix('.part').replace(target)
    labels={'complete':'제공 범위 순회·경계 대조 완료','empty':'현재 제공된 채팅 없음','unavailable':'채팅 미제공','review':'일부 제공 채팅 · 원본 검증 상태 유지'}
    save_json(folder/'summary.json',{'messages':count,'status':labels[state],'source_range_ms':[a,b]})
    return {'state':state,'message':f'저장된 채팅에서 범위 내 {count}건 복사','assets':{'jsonl':'exports/chat.jsonl','summary':'exports/summary.json'},'progress':{'messages':count}}


def copy_transcript(parent,path,vod,selection,a,b,audio):
    source=load_project(parent,vod);origin=source.get('input',{}).get('start_vod_ms',0)
    selected=analysis_inputs.selected(parent,source,selection);raw=speech_store.manifest(parent,{'run':selection['transcript_run']})
    duration=audio['duration_ms'];rows=[]
    for r in selected['speech']:
        start=max(a,r['start_ms']+origin);end=min(b,a+duration,r['end_ms']+origin)
        if start<end:rows.append(r|{'start_ms':start-a,'end_ms':end-a})
    id=uuid.uuid4().hex;folder=speech_media.local(path,'runs/'+id);folder.mkdir(parents=True)
    save_json(folder/'00000.json',{'start_ms':0,'end_ms':duration,'segments':rows})
    run=copy.deepcopy(raw);run.update(id=id,created_at=stamp(),duration_ms=duration,processed_ms=duration,complete=True,segment_count=len(rows),
        audio_sha256=audio['sha256'],source_audio_sha256=audio['sha256'],input_audio=audio,source_audio=audio,
        chunks=[{'start_ms':0,'end_ms':duration,'file':'00000.json','status':'recognized' if rows else 'no_speech'}],origin_selection=selection,origin_range_ms=[a,b])
    save_json(folder/'manifest.json',run)
    speech_store.update(path,state='complete',message='선택 전사·수동 교정의 범위 복사 완료',run=id,audio=audio,raw_audio=audio,exports={},progress={'processed_ms':duration,'duration_ms':duration})
    if selection.get('speaker_run'):
        voice=voice_store.result(parent,selection['speaker_run']);edits=voice_store.edits(parent,voice['id']);names=voice['speakers']|edits['speakers']|edits['names'];vid=uuid.uuid4().hex
        assignments={r['id']:{k:r[k] for k in ('speaker','status','reason','confidence') if k in r} for r in rows}
        turns=[t|{'start_ms':max(a,t['start_ms']+origin)-a,'end_ms':min(b,a+duration,t['end_ms']+origin)-a} for t in voice.get('turns',[]) if t['start_ms']+origin<min(b,a+duration) and t['end_ms']+origin>a]
        result=copy.deepcopy(voice)|{'id':vid,'created_at':stamp(),'transcript_run':id,'audio_sha256':audio['sha256'],'duration_ms':duration,'speakers':names,'assignments':assignments,'turns':turns,'origin_selection':selection}
        save_json(voice_store.local(path,f'runs/{vid}/result.json'),result)
        voice_store.update(path,state='complete',message='선택 화자 배정의 범위 복사 완료',run=vid,runs=[vid],exports={})


def remote_media(work,target):
    from .remote_media import receive
    request=work.value['request']
    return receive(work.vod,request['start_ms'],request['end_ms'],target,work.stop,work.lock,work.update,height=request['settings']['height'])


def execute(work):
    # 내부 범위 프로젝트도 표준 API·잠금을 사용한다. 부모의 현재 선택/결과는 바꾸지 않는다.
    from .jobs import Manager
    from .studio_jobs import local
    req=work.value['request'];a,b=req['start_ms'],req['end_ms'];settings=req['settings'];parent=load_project(work.path,work.vod)
    root=local(work.path,f'runs/{work.value["id"]}/analysis');path=root/f'vod-{work.vod}';path.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():raise ValueError('범위 프로젝트에 연결 폴더를 사용할 수 없습니다')
    with ProjectLock(path) as child_lock:
        def clock(ms):
            s=ms//1000;return f'{s//3600:02}:{s//60%60:02}:{s%60:02}'
        metadata=parent['metadata']|{'title':parent['metadata']['title']+f' · 구간 {clock(a)}–{clock(b)}'}
        source=None if (path/'project.json').exists() else {'kind':'range','start_vod_ms':a,'end_vod_ms':b,'parent_vod':work.vod}
        data=create_or_load(path,metadata,parent['format_id'],source)
        if not (path/'context/background.json').exists():context_background.save(path,settings.get('background',''))
        if data['tasks']['video']['state']!='complete':
            work.update(message='부분 영상 준비',progress=0);folder=path/'media';folder.mkdir(exist_ok=True);target=folder/'range-working.mp4'
            if work.value['kind']=='remote':remote_media(work,target)
            else:
                src=clip_contract.media(work.path,work.vod)
                if src['identity']!=work.value['source']:raise ValueError('원본 영상이 바뀌었습니다. 새 범위 작업으로 시작하세요')
                if a==src['origin'] and b-a==src['duration']:
                    # 같은 디스크에서는 복제 공간을 쓰지 않는 하드링크. 원본에는 쓰지 않는다.
                    if target.exists():target.unlink()
                    try:os.link(src['file'],target)
                    except OSError:clip_render.copy_media(src['file'],target,work.stop)
                else:
                    options=clip_contract.validate({'clips':[{'title':'분석 범위','start_ms':a,'end_ms':b}]},src)['options']
                    clip_render.encode(src,{'start_ms':a,'end_ms':b},options,target,work.stop,child_lock,work.update)
            target.replace(folder/'range.mp4')
            duration=float(clip_render.probe(folder/'range.mp4')['format']['duration'])
            data['tasks']['video'].update(state='complete',message='독립 범위 영상 준비 완료',verification={'duration':duration},assets={'playback':'media/range.mp4','original':'media/range.mp4'})
            data['tasks']['chat']=filtered_chat(work.path,path,parent,a,b,work.stop)
            save_json(path/'project.json',data)
        if req['selection'] and not speech_store.manifest(path):
            work.update(message='선택 전사와 수동 교정 복사',progress=0)
            tracks=speech_media.info(path,data)['tracks']
            if not tracks:raise ValueError('원음이 없는 영상입니다')
            audio=speech_media.extract(path,data,tracks[0]['index'],work.stop,child_lock,lambda **v:None)
            # 원본 전사 복사는 요청한 원본 시각을 기준으로 한다.
            copy_transcript(work.path,path,work.vod,req['selection'],a,b,audio)
        work.update(project={'root':str(root),'vod_id':work.vod,'path':str(path)})
    manager=Manager(root);queue=SimpleNamespace(manager=manager,root=str(root),stop=work.stop)
    try:
        chosen=copy.deepcopy(settings)
        if req['selection']:
            chosen['steps']=[k for k in chosen['steps'] if k!='transcribe']
            chosen['speakers_enabled']=bool(req['selection'].get('speaker_run')) or 'diarize' in chosen['steps']
        # 새 범위는 대응 원음이 필요하다. 전사 실행을 선택하면 범위 원음도 준비한다.
        if 'transcribe' in chosen['steps'] and 'audio' not in chosen['steps']:chosen['steps'].insert(0,'audio')
        entry={'vod':work.vod,'format':parent['format_id'],'options':chosen}
        stages=automation_plan.sequence(chosen) if chosen['steps'] else []
        for stage in stages:
            check_cancel(work.stop)
            if stage in work.value['completed_stages']:continue
            work.update(message={'audio':'범위 원음 추출','transcribe':'범위 전사','diarize':'범위 화자 구분','reactions':'범위 채팅 반응','summary':'범위 상세 문맥','timestamps':'범위 타임스탬프','clips':'범위 클립 후보'}[stage],progress=0)
            outcome=automation_steps.execute(queue,entry,stage)
            work.value['completed_stages'].append(stage);work.update(stage_result=outcome)
    finally:manager.close()
