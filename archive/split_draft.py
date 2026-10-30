"""경계 검사 전의 분할점도 실행 이력과 별도로 보존한다."""
from .storage import Conflict, read_json, save_json, stamp
from . import split_contract as contract
from .split_audio import selection

def read(root):
    file=root/'draft.json'
    if root.is_symlink() or file.is_symlink():raise Conflict('초안 경로가 연결 파일입니다')
    return read_json(file) if file.exists() else {'revision':0,'draft':None}

def save(root,data,sources):
    old=read(root)
    if data.get('revision')!=old['revision']:raise Conflict('다른 창에서 분할 초안이 변경됐습니다. 현재 내용을 보관하고 저장된 초안을 다시 불러오세요')
    value=data.get('draft')
    if value is not None:
        if not isinstance(value,dict):raise ValueError('분할 초안을 확인하세요')
        source=sources[contract.run_id(value.get('source_id'))]
        contract.unchanged(source)
        points=contract.points(value.get('points'),source['duration']) if value.get('points') else []
        folder=value.get('folder','')
        if not isinstance(folder,str) or len(folder)>4096:raise ValueError('출력 폴더를 확인하세요')
        drafts=value.get('point_drafts',{});pending=value.get('pending_point','')
        if not isinstance(drafts,dict) or len(drafts)>200 or any(not isinstance(k,str) or len(k)>64 or not isinstance(v,str) or len(v)>64 for k,v in drafts.items()) or not isinstance(pending,str) or len(pending)>64:raise ValueError('작성 중인 분할 시각을 확인하세요')
        value={'source':source,'points':points,'folder':folder,'point_drafts':drafts,'pending_point':pending,
               'audio_selection':selection(source,value.get('audio_selection'))}
    result={'revision':old['revision']+1,'draft':value,'updated_at':stamp()}
    save_json(root/'draft.json',result)
    return result
