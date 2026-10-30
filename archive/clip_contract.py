"""클립 편집의 시간·화면 계약. 모든 시각은 원본 VOD 기준이다."""
import math
import re
from .caption_styles import PRESETS
from . import caption_design
from .storage import load_project
from .speech_media import source, identity
from .video import probe


def number(v, lo, hi, label):
    if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError(label + ' 값을 확인하세요')
    return v


def media(path, vod):
    data = load_project(path, vod)
    file = source(path, data)
    info = probe(file)
    stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
    return dict(file=file, identity=identity(file, path), origin=int(data.get('input', {}).get('start_vod_ms', 0)),
                duration=round(float(info['format']['duration'])*1000), width=int(stream['width']), height=int(stream['height']),
                audio=any(s['codec_type']=='audio' for s in info['streams']), data=data)


def validate(value, src, *, draft=False):
    if not isinstance(value, dict): raise ValueError('편집 설정을 확인하세요')
    clips=value.get('clips')
    if not isinstance(clips,list) or not (0 if draft else 1)<=len(clips)<=100: raise ValueError('구간은 1~100개 선택하세요')
    result=[]
    for c in clips:
        if not isinstance(c,dict) or not isinstance(c.get('title'),str) or len(c['title'])>200: raise ValueError('클립 제목을 확인하세요')
        a=number(c.get('start_ms'),src['origin'],src['origin']+src['duration'],'시작 시각')
        b=number(c.get('end_ms'),a+100,src['origin']+src['duration'],'끝 시각')
        if c.get('id') is not None and (not isinstance(c['id'],str) or len(c['id'])>256):raise ValueError('클립 선택 정보를 확인하세요')
        result.append(dict(title=c['title'],start_ms=round(a),end_ms=round(b),id=c.get('id')))
    result.sort(key=lambda c:(c['start_ms'],c['end_ms']))
    options=dict(ratio='original',fit='contain',x=50,y=50,layout='single',split=60,game=[0,0,100,100],face=[70,50,30,50],
                 size='source',mode='separate',transition='cut',volume=100,brightness=0,contrast=1,saturation=1,fade=0,
                 caption=False,style='basic',caption_design=None,font='auto',caption_language='ko',font_size=22,position='bottom',caption_x=0,caption_y=0,image=None,sidecar=True,speed='exact')
    supplied=value.get('options',{})
    if not isinstance(supplied,dict) or set(supplied)-set(options):raise ValueError('지원하지 않는 편집 옵션입니다')
    options.update(supplied)
    options['caption_design']=caption_design.validate(options['caption_design'])
    enums={'ratio':['original','16:9','9:16','1:1','4:5'],'fit':['contain','cover'],'layout':['single','split'],
           'size':['source','720','1080'],'mode':['separate','joined'],'transition':['cut','fade'],
           'caption_language':['ko','en','ja','zh-CN','zh-TW'],'style':['basic','box','accent',*PRESETS],'position':['bottom','center','top'],'speed':['exact','fast']}
    for k,allowed in enums.items():
        if options[k] not in allowed:raise ValueError(k+' 설정을 확인하세요')
    for k,a,b in [('x',0,100),('y',0,100),('split',20,80),('volume',0,200),('brightness',-.5,.5),('contrast',.5,2),('saturation',0,2),('fade',0,2),('font_size',14,40),('caption_x',-40,40),('caption_y',-40,40)]:
        number(options[k],a,b,k)
    for k in ['caption','sidecar']:
        if type(options[k]) is not bool:raise ValueError(k+' 선택을 확인하세요')
    if not isinstance(options['font'],str) or not re.fullmatch(r'auto|[0-9a-f]{24}',options['font']):
        raise ValueError('글꼴 목록에서 선택하세요')
    image=options['image']
    if image is not None:
        if not isinstance(image,dict) or set(image)!=set(('asset','name','x','y','width','opacity')):
            raise ValueError('PNG 이미지 설정을 확인하세요')
        if not isinstance(image['asset'],str) or not re.fullmatch('[0-9a-f]{64}',image['asset']):raise ValueError('PNG 이미지 선택 정보를 확인하세요')
        if not isinstance(image['name'],str) or len(image['name'])>180:raise ValueError('PNG 이름을 확인하세요')
        for k,a,b in [('x',0,100),('y',0,100),('width',1,100),('opacity',0,100)]:number(image[k],a,b,'PNG '+k)
    for k in ['game','face']:
        r=options[k]
        if not isinstance(r,list) or len(r)!=4:raise ValueError('게임·얼굴 영역을 확인하세요')
        for i,v in enumerate(r):number(v,0 if i<2 else 1,100,k)
        if options['layout']=='split':
            label='게임 영역' if k=='game' else '얼굴 영역'
            if r[0]+r[2]>100.001:raise ValueError(label+'의 가로 위치 + 너비가 100%를 넘습니다. 화면 설정에서 조절하세요')
            if r[1]+r[3]>100.001:raise ValueError(label+'의 세로 위치 + 높이가 100%를 넘습니다. 화면 설정에서 조절하세요')
            if r[2]*src['width']/100<2 or r[3]*src['height']/100<2:raise ValueError(label+'의 너비·높이는 원본 기준 최소 2픽셀이어야 합니다')
    if options['layout']=='split':options['ratio']='9:16'
    if not draft and options['speed']=='fast' and (options['mode']!='separate' or options['ratio']!='original' or options['caption'] or options['image'] or
        options['layout']!='single' or options['size']!='source' or options['volume']!=100 or options['brightness']!=0 or
        options['contrast']!=1 or options['saturation']!=1 or options['fade'] or (options['sidecar'] and value.get('selection'))):
        raise ValueError('빠른 저장은 개별·원본 비율·효과/자막/PNG 없음에서만 사용할 수 있습니다. 편집용 자막 파일도 해제하세요')
    edits=value.get('caption_edits',{})
    if not isinstance(edits,dict) or len(edits)>20000 or any(not isinstance(k,str) or not isinstance(v,str) or len(v)>5000 for k,v in edits.items()):raise ValueError('자막 교정을 확인하세요')
    versions=value.get('caption_versions',{})
    if not isinstance(versions,dict) or len(versions)>100:raise ValueError('자막 버전별 교정 목록을 확인하세요')
    for version, changes in versions.items():
        if not isinstance(version,str) or len(version)>256 or not isinstance(changes,dict) or len(changes)>20000 or any(not isinstance(k,str) or not isinstance(v,str) or len(v)>5000 for k,v in changes.items()):raise ValueError('자막 버전별 교정을 확인하세요')
    range_drafts=value.get('range_drafts',{})
    if not isinstance(range_drafts,dict) or len(range_drafts)>1000:raise ValueError('작성 중인 구간을 확인하세요')
    for key,row in range_drafts.items():
        if not isinstance(key,str) or len(key)>256 or not isinstance(row,dict) or set(row)!=set(('title','start','end')) or any(not isinstance(v,str) or len(v)>500 for v in row.values()):raise ValueError('작성 중인 구간 값을 확인하세요')
    return dict(clips=result,options=options,selection=value.get('selection'),caption_edits=edits,caption_versions=versions,range_drafts=range_drafts)


def dimensions(src, options):
    ratio=src['width']/src['height'] if options['ratio']=='original' else float(options['ratio'].split(':')[0])/float(options['ratio'].split(':')[1])
    edge=min(src['width'],src['height']) if options['size']=='source' else int(options['size'])
    edge=min(edge,1080)
    w,h=(edge*ratio,edge) if ratio>=1 else (edge,edge/ratio)
    return max(2,round(w/2)*2),max(2,round(h/2)*2)


def offsets(clips, transition):
    starts=[0];overlaps=[]
    for i in range(1,len(clips)):
        length=(clips[i-1]['end_ms']-clips[i-1]['start_ms'])/1000
        next_length=(clips[i]['end_ms']-clips[i]['start_ms'])/1000
        overlap=min(.35,length/3,next_length/3) if transition=='fade' else 0
        overlaps.append(overlap);starts.append(starts[-1]+length-overlap)
    return starts,overlaps,starts[-1]+(clips[-1]['end_ms']-clips[-1]['start_ms'])/1000
