"""편집용 PNG 사본과 합성. 원본 파일·외부 경로는 수정하거나 공개하지 않는다."""
import base64
import binascii
import hashlib
import io
import re
import warnings
from PIL import Image

MAX_BYTES = 10 * 1024**2


def location(project, key):
    if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key):
        raise ValueError('PNG 이미지 선택 정보를 확인하세요')
    path = project/'studio/images'/(key+'.png')
    for part in (path, *path.parents):
        if part == project: break
        if part.is_symlink(): raise ValueError('연결 파일은 편집 이미지로 사용할 수 없습니다')
    return path


def decode(raw):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('움직이지 않는 PNG 이미지 한 장을 선택하세요')
                if max(image.size) > 8192 or image.width*image.height > 25_000_000:
                    raise ValueError('PNG는 한 변 8192px, 전체 2500만 픽셀 이하로 줄여 주세요')
                image.load()
                return image.convert('RGBA')
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError('PNG 이미지를 읽을 수 없습니다. 파일 형식과 크기를 확인하세요') from error


def add(project, encoded, name):
    if not isinstance(encoded, str) or len(encoded) > (MAX_BYTES+2)//3*4:
        raise ValueError('PNG는 10MB 이하로 선택하세요')
    try: raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error: raise ValueError('PNG 데이터를 다시 선택하세요') from error
    if len(raw) > MAX_BYTES: raise ValueError('PNG는 10MB 이하로 선택하세요')
    image = decode(raw)
    out = io.BytesIO(); image.save(out, format='PNG'); clean = out.getvalue()
    key = hashlib.sha256(clean).hexdigest(); path = location(project, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temp = path.with_suffix('.part'); temp.write_bytes(clean); temp.replace(path)
    label = name if isinstance(name, str) else 'PNG 이미지'
    label = label.replace('\\', '/').split('/')[-1][:180]
    return dict(asset=key, name=label, width_px=image.width, height_px=image.height)


def load(project, options):
    if not options: return None
    path = location(project, options['asset'])
    if not path.is_file(): raise ValueError('초안의 PNG 이미지가 없습니다. 이미지를 다시 선택하거나 제거하세요')
    if path.stat().st_size > 110*1024**2: raise ValueError('저장한 PNG 이미지의 크기가 올바르지 않습니다')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != options['asset']:
        raise ValueError('저장한 PNG 이미지가 변경됐습니다. 이미지를 다시 선택하세요')
    return decode(raw)


def preview(project, asset):
    """드래그 미리보기용 작은 사본. 저장 합성에는 원래 PNG를 계속 사용한다."""
    image = load(project, {'asset': asset})
    width, height = image.size
    image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    out = io.BytesIO(); image.save(out, format='PNG')
    return dict(png=base64.b64encode(out.getvalue()).decode('ascii'), width_px=width, height_px=height)


def layer(size, image, options):
    canvas = Image.new('RGBA', size)
    if image is None or not options: return canvas
    w = max(1, round(size[0]*options['width']/100)); h = max(1, round(w*image.height/image.width))
    # 세로로 매우 긴 PNG도 프레임 밖 부분 때문에 거대한 중간 이미지를 만들지 않는다.
    x = round(size[0]*options['x']/100-w/2); y = round(size[1]*options['y']/100-h/2)
    box = (max(0,x), max(0,y), min(size[0],x+w), min(size[1],y+h))
    if box[0] >= box[2] or box[1] >= box[3]: return canvas
    source_box = ((box[0]-x)*image.width/w, (box[1]-y)*image.height/h,
                  (box[2]-x)*image.width/w, (box[3]-y)*image.height/h)
    cut = image.resize((box[2]-box[0],box[3]-box[1]), Image.Resampling.LANCZOS, box=source_box)
    cut.putalpha(cut.getchannel('A').point(lambda v: round(v*options['opacity']/100)))
    canvas.alpha_composite(cut, (box[0],box[1])); return canvas
