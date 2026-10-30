"""사용자가 조절한 자막 색상과 효과. 길이 수치는 글자 크기 22 기준이다."""
import math
import re

DEFAULT = dict(text_color='#ffffff',outline=True,outline_color='#000000',outline_width=2,
               shadow=False,shadow_color='#000000',shadow_opacity=70,shadow_blur=2,shadow_x=1,shadow_y=2,
               box=False,box_color='#101010',box_opacity=86,box_padding=6)
LIMITS = dict(outline_width=(0,8),shadow_opacity=(0,100),shadow_blur=(0,8),shadow_x=(-10,10),shadow_y=(-10,10),
              box_opacity=(0,100),box_padding=(0,24))


def validate(value):
    if value is None:return None
    if not isinstance(value,dict) or set(value)!=set(DEFAULT):raise ValueError('자막 색상·효과 설정을 확인하세요')
    for key,item in value.items():
        if key.endswith('_color'):
            if not isinstance(item,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',item):raise ValueError('자막 색상은 #RRGGBB 형식이어야 합니다')
        elif key in ('outline','shadow','box'):
            if type(item) is not bool:raise ValueError('자막 효과 선택을 확인하세요')
        else:
            lo,hi=LIMITS[key]
            if type(item) not in (int,float) or not math.isfinite(item) or not lo<=item<=hi:raise ValueError('자막 효과 수치 범위를 확인하세요')
    return dict(value)


def catalog(legacy):
    result={'basic':dict(DEFAULT),'box':dict(DEFAULT,box=True)}
    result['accent']=dict(DEFAULT,text_color='#ffe367')
    for key,preset in legacy.items():
        # 예전 다중 레이어는 그대로 렌더링한다. 이 값은 사용자가 직접 수정할 때의 출발값이다.
        border=next((v for v in preset['layers'] if v[0]==preset['outline']),preset['layers'][0])
        shadow=next((v for v in preset['layers'] if v[4]),None)
        result[key]=dict(DEFAULT,text_color=preset['layers'][-1][0],outline_color=preset['outline'],outline_width=border[1])
        if shadow:result[key].update(shadow=True,shadow_color=shadow[0],shadow_opacity=100,shadow_blur=shadow[4],shadow_x=shadow[2],shadow_y=shadow[3])
    return result


def rgba(color,opacity=100):
    return (*[int(color[i:i+2],16) for i in (1,3,5)],round(opacity*255/100))


def paint(image,text,size,options,face):
    from PIL import Image, ImageDraw, ImageFilter
    d=options['caption_design'];w,h=size;scale=options['font_size']*w/550/22
    stroke=round(d['outline_width']*scale) if d['outline'] else 0
    spacing=max(2,round(6*scale));draw=ImageDraw.Draw(image);lines=[]
    for line in text.splitlines():
        current=''
        for char in line:
            if current and draw.textlength(current+char,font=face)>w*.88:lines.append(current);current=''
            current+=char
        lines.append(current)
    if not lines or not text.strip():return
    content='\n'.join(lines)
    bbox=draw.multiline_textbbox((0,0),content,font=face,spacing=spacing,stroke_width=stroke,align='center')
    tw,th=bbox[2]-bbox[0],bbox[3]-bbox[1]
    left=(w-tw)/2+w*options.get('caption_x',0)/100
    top={'bottom':h*.9-th,'top':h*.08,'center':(h-th)/2}[options['position']]+h*options.get('caption_y',0)/100
    x,y=left-bbox[0],top-bbox[1]
    if d['box']:
        layer=Image.new('RGBA',size);pad=d['box_padding']*scale
        ImageDraw.Draw(layer).rectangle((left-pad,top-pad,left+tw+pad,top+th+pad),fill=rgba(d['box_color'],d['box_opacity']))
        image.alpha_composite(layer)
    if d['shadow'] and d['shadow_opacity']:
        layer=Image.new('RGBA',size);color=rgba(d['shadow_color'],d['shadow_opacity'])
        ImageDraw.Draw(layer).multiline_text((x+d['shadow_x']*scale,y+d['shadow_y']*scale),content,font=face,fill=color,
                                           stroke_width=stroke,stroke_fill=color,align='center',spacing=spacing)
        if d['shadow_blur']:layer=layer.filter(ImageFilter.GaussianBlur(d['shadow_blur']*scale))
        image.alpha_composite(layer)
    layer=Image.new('RGBA',size)
    ImageDraw.Draw(layer).multiline_text((x,y),content,font=face,fill=d['text_color'],stroke_width=stroke,
                                       stroke_fill=d['outline_color'],align='center',spacing=spacing)
    image.alpha_composite(layer)


def ass_layers(design,scale,x,y):
    """ASS는 편집기 글꼴·줄바꿈에 따라 PNG 합성과 표현이 달라질 수 있다."""
    def color(v):return '&H'+v[5:7]+v[3:5]+v[1:3]+'&'
    def alpha(opacity):return f'&H{round(255*(100-opacity)/100):02X}&'
    def pos(dx=0,dy=0):return rf'\pos({x+dx*scale:.2f},{y+dy*scale:.2f})'
    d=design;layers=[];border=d['outline_width']*scale if d['outline'] else 0
    if d['box']:
        tags=pos()+rf'\1a&HFF&\3c{color(d["box_color"])}\3a{alpha(d["box_opacity"])}\bord{d["box_padding"]*scale:.2f}\shad0'
        layers.append(('Box',tags))
    if d['shadow'] and d['shadow_opacity']:
        tags=pos(d['shadow_x'],d['shadow_y'])+rf'\1c{color(d["shadow_color"])}\3c{color(d["shadow_color"])}\alpha{alpha(d["shadow_opacity"])}\bord{border:.2f}\blur{d["shadow_blur"]*scale:.2f}\shad0'
        layers.append(('Default',tags))
    layers.append(('Default',pos()+rf'\1c{color(d["text_color"])}\3c{color(d["outline_color"])}\alpha&H00&\bord{border:.2f}\shad0'))
    return layers
