"""클립 작업 소유권·원본 참조·완성 파일을 확인한 뒤 휴지통으로 정리한다."""
import hashlib
import json
import re
from pathlib import Path
from .storage import Conflict,read_json,save_json,stamp
from .deletion import trash_path
from .file_metadata import owned_metadata

def owned(relative,outputs):
    return relative in ('manifest.json','captions.json','join.ffconcat') or relative in outputs or re.fullmatch(r'(?:clip-\d{3}|joined|join|join-\d{3})[\w-]*\.(?:mp4|log|progress)',relative) or re.fullmatch(r'(?:clip-\d{3}|joined)-final-working-captions(?:/(?:[0-9a-f]{20}\.png|blank\.png|captions\.ffconcat))?',relative)

def identity(file):
    s=file.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns]

def inventory(folder):
    rows=[]
    for file in sorted(folder.rglob('*')):
        if file.is_symlink() or not (file.is_file() or file.is_dir()):raise Conflict('작업에 연결 파일 또는 특수 파일이 있습니다')
        rows.append([str(file.relative_to(folder)),*identity(file)])
    return rows

def preview(path,file,mode):
    value=read_json(file);folder=file.parent
    if value['id']!=folder.name:raise Conflict('작업 식별 정보가 다릅니다')
    if value['kind']!='start':
        from .studio_range_cleanup import preview as range_preview
        return range_preview(path,file,mode)
    if mode not in ('intermediate','delete'):raise ValueError('정리 범위를 확인하세요')
    if mode=='intermediate' and value['state']!='complete':raise Conflict('중간 파일 정리는 완료한 영상에서만 가능합니다')
    if any(p.is_symlink() for p in (folder,*folder.parents)):raise Conflict('연결 경로는 정리할 수 없습니다')
    outputs={name for out in value['outputs'].values() for name in out['assets'].values()}
    for out in value['outputs'].values():
        for kind,name in out['assets'].items():
            if Path(name).name!=name:raise Conflict('출력 경로를 확인하세요')
            target=folder/name
            if not target.is_file() or target.is_symlink():raise Conflict('완성 파일을 찾을 수 없습니다. 저장 디스크를 확인하세요')
            if out.get('asset_identities',{}).get(kind) and identity(target)!=out['asset_identities'][kind]:raise Conflict('완성 파일이 변경됐습니다. 정리하지 않았습니다')
            if kind=='video':
                if target.stat().st_size!=out['verification']['bytes'] or (out.get('file_identity') and identity(target)!=out['file_identity']):raise Conflict('완성 파일이 변경됐습니다. 정리하지 않았습니다')
    rows=inventory(folder);protected=set()
    # 프로젝트의 영상과 다른 작업에서 원본으로 사용하는 파일을 보호한다.
    for record in [path/'project.json',*path.parent.glob('vod-*/project.json'),*path.glob('studio/runs/*/manifest.json')]:
        if not record.is_file() or record==file:continue
        data=read_json(record)
        refs=list(data.get('tasks',{}).get('video',{}).get('assets',{}).values())
        if data.get('source',{}):refs.append(data['source'].get('file',''))
        base=record.parent if record.name=='project.json' else path
        for ref in refs:
            if not isinstance(ref,str) or not ref:continue
            target=base/ref
            if target.exists():protected.add(tuple(identity(target)[:2]))
    names=[];size=0;allowed={r[0] for r in rows if owned(r[0],outputs)}
    for relative,dev,ino,bytes_,mtime in rows:
        top=relative.split('/')[0]
        if relative not in allowed and not owned_metadata(folder/relative,folder,allowed):raise Conflict('작업 외 파일이 있어 정리하지 않았습니다: '+relative)
        if (dev,ino) in protected:raise Conflict('다른 작업의 원본으로 참조되는 파일이 있습니다')
        keep=top in outputs or top in ('manifest.json','captions.json','.DS_Store') or (top.startswith('._') and top[2:] in outputs|{'manifest.json','captions.json'})
        if mode=='delete' or not keep:
            if '/' not in relative:names.append(top)
            if (folder/relative).is_file():size+=bytes_
    token=hashlib.sha256(json.dumps([value,rows,mode],sort_keys=True).encode()).hexdigest()
    return dict(id=value['id'],mode=mode,token=token,bytes=size,names=names,folder=str(folder),output_count=len(outputs))

def clean(path,file,mode,token):
    checked=preview(path,file,mode)
    if checked['token']!=token:raise Conflict('확인 이후 파일이 바뀌었습니다. 정리 창을 다시 열어주세요')
    if mode=='delete':trash_path(file.parent)
    else:
        # 각 경로는 검증한 작업 소유 항목이다. 실패 시 남은 항목만 재확인해 재시도한다.
        for name in checked['names']:trash_path(file.parent/name)
        value=read_json(file);value['intermediates_cleaned_at']=stamp();save_json(file,value)
    return {'ok':True,'bytes':checked['bytes']}
