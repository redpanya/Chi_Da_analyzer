"""전사 교정의 스냅샷, 클립 자막 시간 변환, OS 글꼴을 사용한 자막 이미지."""
import hashlib
import shutil
from .source import check_cancel
from . import analysis_inputs
from .storage import load_project
from .clip_contract import offsets
from . import caption_fonts, caption_styles, caption_design, studio_images


def snapshot(path, vod, selection, edits=None):
    if selection is None:return []
    selected=analysis_inputs.selected(path,load_project(path,vod),selection)
    origin=load_project(path,vod).get('input',{}).get('start_vod_ms',0)
    rows=selected['speech'];edits=edits or {};ids={r['id'] for r in rows}
    if set(edits)-ids:raise ValueError('선택한 전사에 없는 자막 교정입니다')
    return [dict(id=r['id'],start_ms=r['start_ms']+origin,end_ms=r['end_ms']+origin,
                 text=edits.get(r['id'],r['text']),speaker=r.get('speaker_name','')) for r in rows]


def cues(rows, clips, transition='cut'):
    starts,_,total=offsets(clips,transition);result=[]
    for c,at in zip(clips,starts):
        for r in rows:
            a=max(c['start_ms'],r['start_ms']);b=min(c['end_ms'],r['end_ms'])
            if a<b and r['text'].strip():result.append(dict(start_ms=round(at*1000+a-c['start_ms']),end_ms=round(at*1000+b-c['start_ms']),text=r['text']))
    return sorted(result,key=lambda r:(r['start_ms'],r['end_ms'])),total


def clock(ms, ass=False):
    ms=max(0,round(ms));sec=ms//1000
    return (f'{sec//3600}:{sec//60%60:02}:{sec%60:02}.{ms%1000//10:02}' if ass else f'{sec//3600:02}:{sec//60%60:02}:{sec%60:02},{ms%1000:03}')


def write(folder,name,rows,size,options):
    srt='\n\n'.join(f"{i+1}\n{clock(r['start_ms'])} --> {clock(r['end_ms'])}\n{r['text'].replace(chr(13),'')}" for i,r in enumerate(rows))+'\n'
    (folder/(name+'.srt')).write_text(srt,encoding='utf-8-sig')
    align={'bottom':2,'center':5,'top':8}[options['position']]
    color='&H0067E3FF' if options['style']=='accent' else '&H00FFFFFF'
    font,bold,italic=caption_fonts.ass_face(options.get("font","auto"),options.get("caption_language","ko"))
    font=font.replace(',',' ').replace('\n',' ')
    design=options.get('caption_design')
    preset=caption_styles.PRESETS.get(options['style']) if design is None else None
    def ass_color(hexcolor):
        c=hexcolor.lstrip('#');return '&H00'+c[4:6]+c[2:4]+c[:2]
    if preset:color=ass_color(preset['layers'][-1][0])
    header=f'[Script Info]\nScriptType: v4.00+\nPlayResX: {size[0]}\nPlayResY: {size[1]}\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{font},{round(options["font_size"]*size[0]/550)},{color},&H00000000,&H80000000,{bold},{italic},{3 if options["style"]=="box" and design is None else 1},2,0,{align},20,20,{round(size[1]*.08)},1\n\n[Events]\nFormat: Layer, Start, End, Style, Text\n'
    if design and design['box']:
        box=f'Style: Box,{font},{round(options["font_size"]*size[0]/550)},&HFFFFFFFF,&H00000000,&H00000000,{bold},{italic},3,0,0,{align},20,20,{round(size[1]*.08)},1'
        header=header.replace('\n\n[Events]', '\n'+box+'\n\n[Events]')
    # ASS 제어 문자열은 대사에서 제거하고 개행만 자막 개행으로 변환한다.
    def literal(text):return text.replace('\\','＼').replace('{','｛').replace('}','｝').replace('\r','').replace('\n','\\N')
    x=size[0]*(.5+options.get('caption_x',0)/100)
    y=size[1]*({'bottom':.9,'center':.5,'top':.08}[options['position']]+options.get('caption_y',0)/100)
    placement='{'+rf'\pos({x:.2f},{y:.2f})'+'}'
    events=[];scale=options['font_size']*size[0]/550/22
    for r in rows:
        if design is not None:
            for i,(style,tags) in enumerate(caption_design.ass_layers(design,scale,x,y)):
                events.append(f"Dialogue: {i},{clock(r['start_ms'],True)},{clock(r['end_ms'],True)},{style},{{{tags}}}{literal(r['text'])}")
        elif preset:
            for i,(fill,border,dx,dy,blur) in enumerate(preset['layers']):
                tags='{'+rf'\pos({x+dx*scale:.2f},{y+dy*scale:.2f})\1c{ass_color(fill)}&\3c{ass_color(fill)}&\bord{border*scale:.2f}\blur{blur*scale:.2f}'+'}'
                events.append(f"Dialogue: {i},{clock(r['start_ms'],True)},{clock(r['end_ms'],True)},Default,{tags}{literal(r['text'])}")
        else:events.append(f"Dialogue: 0,{clock(r['start_ms'],True)},{clock(r['end_ms'],True)},Default,{placement}{literal(r['text'])}")
    (folder/(name+'.ass')).write_text(header+'\n'.join(events),encoding='utf-8-sig')


def font_path():
    return caption_fonts.resolve()[0]


def preflight(rows, clips, size, options, stop=None):
    """선택 구간의 실제 문장을 영상 처리 전에 같은 렌더러로 검사한다."""
    if not options['caption']:return
    from PIL import Image
    checked=set()
    for row in rows:
        if stop is not None:check_cancel(stop)
        text=row['text']
        if text in checked or not any(row['start_ms']<c['end_ms'] and row['end_ms']>c['start_ms'] for c in clips):continue
        try:
            caption_styles.paint(Image.new('RGBA',size),text,size,options)
        except ValueError as error:
            raise ValueError(f"자막 호환성 검사 · {clock(row['start_ms'])}: {error}") from error
        checked.add(text)


def images(folder, rows, size, options, total, stop=None, overlay=None):
    from PIL import Image
    folder.mkdir(exist_ok=True)
    base=studio_images.layer(size,overlay,options.get('image'))
    events={0:[],round(total*1000):[]}
    for i,r in enumerate(rows):
        events.setdefault(r['start_ms'],[]).append((True,i));events.setdefault(r['end_ms'],[]).append((False,i))
    active=set();lines=[];cached={}
    for a,b in zip(sorted(events),sorted(events)[1:]):
        if stop is not None:check_cancel(stop)
        if shutil.disk_usage(folder).free<128*1024**2:raise ValueError('자막 이미지 저장 공간이 부족합니다')
        for enabled,i in events[a]:active.add(i) if enabled else active.discard(i)
        text='\n'.join(rows[i]['text'] for i in sorted(active))
        if text in cached:
            lines.extend([f"file '{cached[text]}'",'option framerate 1000',f'duration {(b-a)/1000:.3f}']);continue
        image=base.copy()
        if text:caption_styles.paint(image,text,size,options)
        name=hashlib.sha256(text.encode()).hexdigest()[:20]+'.png';image.save(folder/name);cached[text]=name;lines.extend([f"file '{name}'",'option framerate 1000',f'duration {(b-a)/1000:.3f}'])
    Image.new('RGBA',size).save(folder/'blank.png');lines.extend(["file 'blank.png'",'option framerate 1000'])
    target=folder/'captions.ffconcat';target.write_text('ffconcat version 1.0\n'+'\n'.join(lines)+'\n',encoding='utf-8');return target
