"""구간별 편집값과 이식 가능한 화면·자막 프리셋. 적용 시 참조 대신 값을 복사한다."""
import copy
import uuid
from . import runtime, caption_fonts, studio_decorations, studio_images
from .caption_templates import template_id, template_name
from .storage import Conflict, ProjectLock, read_json, save_json, stamp

CLIP_KEYS = frozenset(('ratio','fit','x','y','layout','split','game','face','volume','brightness',
    'contrast','saturation','fade','caption','style','caption_design','font','caption_language',
    'font_size','position','caption_x','caption_y','image'))
PRESET_KEYS = CLIP_KEYS

def effective(request, clip):
    return copy.deepcopy(request['options'] | clip.get('options', {}))

def profiles(request):
    return [effective(request,c) for c in request['clips']]

def prepare(path, request):
    """각 구간의 사용 글꼴을 확정하고 이미지 존재를 확인한다. 미사용 기본값은 건드리지 않는다."""
    for clip in request['clips']:
        options=effective(request,clip)
        if options['caption'] or (options['sidecar'] and request.get('selection')):
            frozen=caption_fonts.frozen_options(options)
            if 'options' in clip:clip['options']['font']=frozen['font']
            else:request['options']['font']=frozen['font']
        studio_decorations.prepare(path,effective(request,clip),request.get('selection'))
    return request

def preset_options(value):
    from .clip_contract import validate
    if not isinstance(value,dict) or set(value)-PRESET_KEYS:raise ValueError('화면·자막 프리셋 설정을 확인하세요')
    clean=validate({'clips':[],'options':value},{'origin':0,'duration':1000,'width':1920,'height':1080},draft=True)['options']
    # 구형 프리셋은 PNG 설정 자체가 없었다. 적용 대상의 PNG를 지우지 않도록 유지한다.
    return {k:clean[k] for k in sorted(PRESET_KEYS) if k!='image' or k in value}

def folder():
    path=runtime.SUPPORT/'studio-presets'
    if path.is_symlink():raise ValueError('편집 프리셋 폴더에 연결 경로를 사용할 수 없습니다')
    return path

def entries():
    result=[]
    for file in folder().glob('*.json'):
        if file.is_symlink():raise ValueError('편집 프리셋에 연결 파일을 사용할 수 없습니다')
        try:item=read_json(file)
        except FileNotFoundError:continue
        if not isinstance(item,dict) or item.get('schema') not in (1,2) or item.get('id')!=file.stem:raise ValueError('저장한 편집 프리셋을 확인하세요')
        template_id(item['id']);template_name(item.get('name'))
        item.setdefault('revision',1)
        item['options']=preset_options(item.get('options'));result.append(item)
    return sorted(result,key=lambda v:(v['name'].casefold(),v['id']))

def dispatch(action,data,project=None):
    if action=='list':return {'presets':entries()}
    path=folder()
    with ProjectLock(path):
        items=entries()
        if action=='save':
            name=template_name(data.get('name'))
            old=None
            if data.get('id') is not None:
                id=template_id(data['id']);old=next((v for v in items if v['id']==id),None)
                if old is None or data.get('revision')!=old['revision']:
                    raise Conflict('다른 창에서 프리셋이 변경되거나 제거됐습니다. 다시 불러온 뒤 저장하세요')
            if old is None and len(items)>=100:raise ValueError('편집 프리셋은 최대 100개입니다')
            if any(v['name'].casefold()==name.casefold() and v is not old for v in items):raise Conflict('같은 이름의 프리셋이 있습니다. 다른 이름을 입력하세요')
            options=preset_options(data.get('options'))
            if options.get('image'):
                if project is None:raise ValueError('PNG를 저장할 VOD를 선택하세요')
                studio_images.copy_asset(project,path,options['image'])
            item=dict(schema=2,id=old['id'] if old else uuid.uuid4().hex,name=name,options=options,
                      revision=old['revision']+1 if old else 1,created_at=old['created_at'] if old else stamp(),updated_at=stamp())
            if old:
                history=path/'history'
                if history.is_symlink():raise ValueError('프리셋 이전 설정 보관 경로를 확인하세요')
                save_json(history/(old['id']+'-'+uuid.uuid4().hex+'.json'),old)
            save_json(path/(item['id']+'.json'),item)
            return {'presets':entries(),'id':item['id']}
        if action=='apply':
            id=template_id(data.get('id'));item=next((v for v in items if v['id']==id),None)
            if item is None or data.get('revision')!=item['revision']:
                raise Conflict('프리셋이 변경되거나 제거됐습니다. 목록을 다시 불러오세요')
            if item['options'].get('image'):
                if project is None:raise ValueError('프리셋을 적용할 VOD를 선택하세요')
                studio_images.copy_asset(path,project,item['options']['image'])
            return {'options':copy.deepcopy(item['options'])}
        if action=='delete':
            id=template_id(data.get('id'))
            if not any(v['id']==id for v in items):raise Conflict('이미 제거된 프리셋입니다. 목록을 다시 불러오세요')
            removed=path/'deleted'
            if removed.is_symlink():raise ValueError('프리셋 삭제 보관 경로를 확인하세요')
            removed.mkdir(exist_ok=True)
            (path/(id+'.json')).rename(removed/(id+'-'+uuid.uuid4().hex+'.json'))
            return {'presets':entries()}
        raise ValueError('알 수 없는 편집 프리셋 작업입니다')
