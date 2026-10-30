"""범위 작업의 자식 VOD 소유권과 다른 프로젝트의 경로 참조를 확인한다."""
import hashlib
import json
import re
from pathlib import Path
from .storage import Conflict,read_json

def child_path(file):
    value=read_json(file)
    if not value.get('project'):return None
    project=value['project'];vod=str(project.get('vod_id',''))
    if not re.fullmatch(r'[0-9]+',vod):raise Conflict('범위 프로젝트 식별 정보가 잘못됐습니다')
    child=file.parent/'analysis'/('vod-'+vod)
    if any(p.is_symlink() for p in (child,*child.parents)):raise Conflict('연결 경로는 정리할 수 없습니다')
    if str(child)!=project.get('path') or str(child.parent)!=project.get('root'):raise Conflict('범위 프로젝트 위치가 기록과 다릅니다')
    return child

def preview(path,file,mode):
    from .studio_maintenance import inventory
    value=read_json(file);folder=file.parent;child=child_path(file)
    if mode!='delete':raise Conflict('범위 작업은 전체 작업 삭제만 지원합니다')
    if value['state']=='running':raise Conflict('범위 작업을 중단한 뒤 삭제하세요')
    if child is None:raise Conflict('범위 프로젝트 준비가 끝나지 않았습니다. 원본 참조 확인 후 정리해야 합니다')
    project=value['project']
    if str(child)!=project.get('path') or str(child.parent)!=project.get('root'):raise Conflict('범위 프로젝트 위치가 기록과 다릅니다')
    if child.exists():
        data=read_json(child/'project.json');source=data.get('input',{})
        if source.get('kind')!='range' or str(source.get('parent_vod'))!=path.name.removeprefix('vod-'):raise Conflict('이 작업이 만든 범위 VOD가 아닙니다')
    allowed={'manifest.json','analysis'}
    if any(p.name not in allowed for p in folder.iterdir()):raise Conflict('범위 작업 밖의 파일이 있습니다')
    if child.parent.exists() and any(p!=child for p in child.parent.iterdir()):raise Conflict('다른 범위 프로젝트가 함께 있습니다')
    for record in [path/'project.json',*path.parent.glob('vod-*/project.json'),*path.glob('studio/runs/*/manifest.json')]:
        if record==file:continue
        data=read_json(record);refs=list(data.get('tasks',{}).get('video',{}).get('assets',{}).values())
        if data.get('source'):refs.append(data['source'].get('file',''))
        base=record.parent if record.name=='project.json' else path
        for ref in refs:
            if isinstance(ref,str) and ref and (base/ref).resolve().is_relative_to(folder.resolve()):raise Conflict('다른 작업에서 사용하는 원본 경로가 이 범위 안에 있습니다')
    rows=[r for r in inventory(folder) if not r[0].endswith('.write.lock')]
    for row in rows:
        if (folder/row[0]).is_dir():row[3:]=[0,0]
    token=hashlib.sha256(json.dumps([value,rows,mode],sort_keys=True).encode()).hexdigest()
    return dict(id=value['id'],mode=mode,token=token,bytes=sum(r[3] for r in rows if (folder/r[0]).is_file()),names=[],folder=str(folder),output_count=0,scope='범위 작업 기록과 자식 VOD의 영상·전사·분석 결과 전체')
