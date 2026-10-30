"""동봉·설치 글꼴 선택. 외부 경로는 요청으로 받지 않는다."""
from functools import lru_cache
from pathlib import Path
import hashlib
import os
import struct
import threading
import unicodedata
from fontTools.ttLib import TTLibError
from . import font_languages, font_families

BUNDLED = Path(__file__).resolve().parent.parent/'web/fonts'
_guard = threading.Lock()


@lru_cache(maxsize=64)
def face(path, index, pixels, modified):
    from PIL import ImageFont
    return ImageFont.truetype(str(path), pixels, index=index)


def roots():
    if os.name == 'nt':
        return [Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts',
                Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))/'Microsoft/Windows/Fonts', BUNDLED]
    return [Path('/System/Library/Fonts'), Path('/Library/Fonts'), Path.home()/'Library/Fonts',
            Path('/usr/share/fonts'), Path.home()/'.local/share/fonts', BUNDLED]


@lru_cache(maxsize=1)
def _installed():
    from PIL import ImageFont
    result = {}
    for root in roots():
        if not root.is_dir(): continue
        for path in sorted(root.rglob('*')):
            if path.suffix.lower() not in ('.ttf', '.otf', '.ttc', '.otc') or not path.is_file(): continue
            if not path.resolve().is_relative_to(root.resolve()): continue
            try:
                with path.open('rb') as stream: header = stream.read(12)
                count = min(64, struct.unpack('>I', header[8:12])[0]) if header[:4] == b'ttcf' else 1
            except (OSError, struct.error): continue
            for index in range(count):
                try:
                    font = ImageFont.truetype(str(path), 20, index=index)
                    family, style = font.getname()
                    bundled=path.is_relative_to(BUNDLED)
                    source=str(path.relative_to(BUNDLED)) if bundled else str(path.resolve())
                    key = hashlib.sha256(f'{source}:{index}'.encode()).hexdigest()[:24]
                    support=font_languages.inspect(path,index)
                    result[key] = dict(id=key, label=f'{family} · {style}', family=family,
                                       **font_families.inspect(path,index,family,style),
                                       korean='ko' in support['languages'], **support, bundled=bundled, path=path, index=index)
                except (OSError, ValueError, struct.error, TTLibError, KeyError, AssertionError): continue
    font_families.group(list(result.values()))
    return result


def catalog(refresh=False):
    with _guard:
        if refresh:
            _installed.cache_clear(); face.cache_clear(); font_languages.characters.cache_clear()
        return sorted([{k:v for k,v in row.items() if k not in ('path','index')} for row in _installed().values()],
                      key=lambda row:(not row['bundled'], row['label'].casefold(), row['id']))


def resolve(key='auto', language='ko'):
    if language not in font_languages.LANGUAGES: raise ValueError('자막 언어를 선택하세요')
    with _guard: rows = _installed()
    if key == 'auto':
        preferred={'ko':['Apple SD Gothic Neo','Malgun Gothic','Noto Sans CJK KR','Black And White Picture'],
                   'en':['Arial','Apple SD Gothic Neo','Malgun Gothic'],
                   'ja':['Hiragino Sans','Yu Gothic','Noto Sans CJK JP'],
                   'zh-CN':['PingFang SC','Microsoft YaHei','Noto Sans CJK SC'],
                   'zh-TW':['PingFang TC','Microsoft JhengHei','Noto Sans CJK TC']}[language]
        candidates=[r for r in rows.values() if language in r['languages'] and r['path'].is_file()]
        candidates.sort(key=lambda r:(preferred.index(r['family']) if r['family'] in preferred else len(preferred),
                                      not any(s in r['label'].casefold() for s in ('regular','normal','w3')),r['label']))
        if not candidates: raise ValueError('선택 언어를 지원하는 글꼴이 없습니다. 글꼴 설치 후 목록을 다시 불러오세요')
        row=candidates[0]
    else:
        row=rows.get(key)
        if not row or not row['path'].is_file():
            raise ValueError('선택한 글꼴이 없습니다. 목록을 새로 불러오거나 다른 글꼴을 선택하세요')
        # 기존 초안의 명시적 선택은 언어 필터만으로 덮어쓰지 않는다.
    return row['path'], row['index'], row['family']


def check_text(path, index, text):
    """목록의 기본 언어 지원과 별도로 실제 문장의 누락 글리프를 확인한다."""
    chars=font_languages.characters(path,index,path.stat().st_mtime_ns)
    # 공백·배치 제어·변형 선택자는 독립적인 그림이 없어도 된다. 원문은 수정하지 않는다.
    missing=sorted({ord(c) for c in text if ord(c) not in chars and not c.isspace()
                    and unicodedata.category(c)!='Cf'
                    and not (0xfe00<=ord(c)<=0xfe0f or 0xe0100<=ord(c)<=0xe01ef)})
    if missing:
        values=', '.join(f'{chr(code)} (U+{code:04X})' for code in missing[:5])
        raise ValueError('선택한 글꼴이 이 자막의 일부 글자를 지원하지 않습니다: '+values+'. 글꼴이나 자막을 확인하세요')


def ass_face(key='auto', language='ko'):
    path,index,family=resolve(key,language)
    with _guard:
        row=next(r for r in _installed().values() if r['path']==path and r['index']==index)
    return family, -1 if row['weight']>=600 else 0, -1 if row['italic'] else 0


def frozen_options(options):
    """중단 작업은 시작 당시 글꼴을 유지한다. 구형 템플릿 기본값만 여기서 이관한다."""
    value=dict(options)
    if value.get('font','auto')!='auto': return value
    legacy=None
    if 'caption_language' not in value:
        legacy={'variety':'jua/Jua-Regular.ttf','point':'jua/Jua-Regular.ttf',
                'game':'jua/Jua-Regular.ttf','gloom':'jua/Jua-Regular.ttf',
                'soft':'gaegu/Gaegu-Bold.ttf','rage':'blackandwhitepicture/BlackAndWhitePicture-Regular.ttf'}.get(value.get('style'))
    path,index,_=resolve(language=value.get('caption_language','ko')) if not legacy else (BUNDLED/legacy,0,None)
    with _guard:
        row=next((r for r in _installed().values() if r['path']==path and r['index']==index),None)
    if row is None: raise ValueError('이전 자막 글꼴이 없습니다. 글꼴을 다시 선택해 새 작업으로 저장하세요')
    value['font']=row['id']
    return value
