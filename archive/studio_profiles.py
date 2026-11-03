"""구간별 편집값과 이식 가능한 화면·자막 프리셋. 적용 시 참조 대신 값을 복사한다."""
import copy
import uuid
from . import runtime, caption_fonts, studio_decorations
from .caption_templates import template_id, template_name
from .storage import Conflict, ProjectLock, read_json, save_json, stamp

CLIP_KEYS = frozenset(('ratio','fit','x','y','layout','split','game','face','volume','brightness',
    'contrast','saturation','fade','caption','style','caption_design','font','caption_language',
    'font_size','position','caption_x','caption_y','image'))
# PNG는 VOD 내부 자산이다. 다른 VOD에 없는 이미지나 전사 버전을 프리셋으로 옮기지 않는다.
PRESET_KEYS = CLIP_KEYS - {'image'}

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
    return {k:clean[k] for k in sorted(PRESET_KEYS)}

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
        if not isinstance(item,dict) or item.get('schema')!=1 or item.get('id')!=file.stem:raise ValueError('저장한 편집 프리셋을 확인하세요')
        template_id(item['id']);template_name(item.get('name'))
        item['options']=preset_options(item.get('options'));result.append(item)
    return sorted(result,key=lambda v:(v['name'].casefold(),v['id']))

def dispatch(action,data):
    if action=='list':return {'presets':entries()}
    path=folder()
    with ProjectLock(path):
        items=entries()
        if action=='save':
            if len(items)>=100:raise ValueError('편집 프리셋은 최대 100개입니다')
            name=template_name(data.get('name'))
            if any(v['name'].casefold()==name.casefold() for v in items):raise Conflict('같은 이름의 프리셋이 있습니다. 다른 이름을 입력하세요')
            item=dict(schema=1,id=uuid.uuid4().hex,name=name,options=preset_options(data.get('options')),created_at=stamp())
            save_json(path/(item['id']+'.json'),item)
            return {'presets':entries(),'id':item['id']}
        if action=='delete':
            id=template_id(data.get('id'))
            if not any(v['id']==id for v in items):raise Conflict('이미 제거된 프리셋입니다. 목록을 다시 불러오세요')
            removed=path/'deleted'
            if removed.is_symlink():raise ValueError('프리셋 삭제 보관 경로를 확인하세요')
            removed.mkdir(exist_ok=True)
            (path/(id+'.json')).rename(removed/(id+'-'+uuid.uuid4().hex+'.json'))
            return {'presets':entries()}
        raise ValueError('알 수 없는 편집 프리셋 작업입니다')
