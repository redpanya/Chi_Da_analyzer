"""자막 6종의 외곽선·광택·발광을 미리보기와 저장에서 함께 그린다."""
from . import caption_fonts, caption_design

# 수치는 글자 크기 22px 기준이며 출력 크기에 비례한다. 바깥 레이어부터 그린다.
PRESETS = {
    'variety': dict(label='예능 · 굵은 흰 글자', sample='안녕하세요',
                    layers=[('#000000',2.4,0,1.2,0),('#000000',1.8,0,0,0),('#ffffff',0,0,0,0)], outline='#000000'),
    'point': dict(label='포인트 · 코랄 입체', sample='포인트 자막',
                  layers=[('#ffffff',2.4,0,0,0),('#cd515c',1.6,0,.6,0),('#fff3ed',.7,0,-.45,0),('#ffb0b5',0,0,0,0)], outline='#cd515c'),
    'soft': dict(label='핑크 빛 · 발광', sample='샤랄라한 자막',
                 layers=[('#ff6477',1.2,0,0,2.4),('#ff95a2',.5,0,0,1),('#ffffff',0,0,0,0)], outline='#ff95a2'),
    'game': dict(label='게임 설명 · 분홍 테두리', sample='게임 설명 자막',
                 layers=[('#ffffff',2.1,0,0,0),('#181318',1.5,0,.5,0),('#ffc0c7',0,0,0,0)], outline='#181318'),
    'gloom': dict(label='억울 · 회색 먹구름', sample='억울한 자막',
                  layers=[('#000000',1.8,0,.8,2),('#171717',2.1,0,.5,0),('#eeeeee',1.3,0,0,0),('#3b3b3b',.6,0,0,0),('#bcbcbc',0,0,0,0)], outline='#171717'),
    'rage': dict(label='분노 · 붉은 강조', sample='화나게 하지마라!!',
                 layers=[('#171010',2.3,0,.6,0),('#ffffff',1.4,0,0,0),('#610000',.55,0,0,0),('#d91e23',0,0,.3,0)], outline='#171010'),
}


def font(options, pixels):
    path, index, name = caption_fonts.resolve(options.get('font','auto'), options.get('caption_language','ko'))
    return caption_fonts.face(path, index, pixels, path.stat().st_mtime_ns), name


def paint(image, text, size, options):
    path,index,_=caption_fonts.resolve(options.get('font','auto'),options.get('caption_language','ko'))
    caption_fonts.check_text(path,index,text)
    try:
        _paint(image,text,size,options)
    except OSError as error:
        raise ValueError('선택한 글꼴로 이 자막을 그리지 못했습니다. 다른 글꼴을 선택하거나 글꼴 설치 상태를 확인하세요') from error


def _paint(image, text, size, options):
    from PIL import Image, ImageDraw, ImageFilter
    w,h = size
    face,_ = font(options, max(14,round(options['font_size']*w/550)))
    if options.get('caption_design') is not None:
        caption_design.paint(image,text,size,options,face)
        return
    draw = ImageDraw.Draw(image); wrapped=[]
    preset = PRESETS.get(options['style']); scale = options['font_size']*w/550/22
    spacing = 6 if not preset else max(2,round(6*scale))
    for line in text.splitlines():
        current=''
        for char in line:
            if current and draw.textlength(current+char,font=face)>w*.88: wrapped.append(current);current=''
            current+=char
        wrapped.append(current)
    if not wrapped:return
    content='\n'.join(wrapped)
    stroke=2 if not preset else round(max(layer[1] for layer in preset['layers'])*scale)
    bbox=draw.multiline_textbbox((0,0),content,font=face,spacing=spacing,stroke_width=stroke)
    tw,th=bbox[2]-bbox[0],bbox[3]-bbox[1];x=(w-tw)/2-bbox[0]
    y={'bottom':h*.9-th,'top':h*.08,'center':(h-th)/2}[options['position']]-bbox[1]
    x+=w*options.get('caption_x',0)/100;y+=h*options.get('caption_y',0)/100
    if not preset:
        if options['style']=='box': draw.rectangle((x-10,y+bbox[1]-6,x+tw+10,y+bbox[3]+6),fill=(16,16,16,220))
        draw.multiline_text((x,y),content,font=face,fill='#ffe367' if options['style']=='accent' else 'white',stroke_width=2,stroke_fill='black',align='center',spacing=spacing)
        return
    for color,border,dx,dy,blur in preset['layers']:
        layer=Image.new('RGBA',size);ink=ImageDraw.Draw(layer)
        ink.multiline_text((x+dx*scale,y+dy*scale),content,font=face,fill=color,
                           stroke_width=round(border*scale),stroke_fill=color,align='center',spacing=spacing)
        if blur:layer=layer.filter(ImageFilter.GaussianBlur(blur*scale))
        image.alpha_composite(layer)
