"""문자표(cmap)의 실제 글리프로 언어별 기본 문자 지원을 확인한다."""
from functools import lru_cache
from fontTools.ttLib import TTFont

LANGUAGES = {
    'ko': dict(label='한국어', sample='오늘도 즐거운 방송입니다! 123'),
    'en': dict(label='영어', sample='Enjoy the show! ABC abc 123'),
    'ja': dict(label='일본어', sample='今日も楽しい配信です！ 123'),
    'zh-CN': dict(label='중국어 간체', sample='今天的直播很精彩！ 123'),
    'zh-TW': dict(label='중국어 번체', sample='今天的直播很精彩！ 123'),
}


@lru_cache(maxsize=128)
def characters(path, index, modified):
    with TTFont(path, fontNumber=index, lazy=True) as font:
        return frozenset(code for code,glyph in (font.getBestCmap() or {}).items()
                         if glyph not in ('.notdef','glyph00000'))


def encoded_rows(encoding, leads, trails):
    result=set()
    for a in leads:
        for b in trails:
            try: result.update(map(ord, bytes([a,b]).decode(encoding)))
            except UnicodeDecodeError: pass
    return result


@lru_cache(maxsize=1)
def required():
    latin=set(map(ord, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'))
    return {
        'ko': encoded_rows('euc_kr',range(0xb0,0xc9),range(0xa1,0xff)) | set(range(0x3131,0x3164)),
        'en': latin,
        'ja': encoded_rows('euc_jp',range(0xb0,0xd0),range(0xa1,0xff)) | set(range(0x3041,0x3094)) | set(range(0x30a1,0x30f7)),
        'zh-CN': encoded_rows('gb2312',range(0xb0,0xd8),range(0xa1,0xff)),
        'zh-TW': {n for n in encoded_rows('big5',range(0xa4,0xc7),[*range(0x40,0x7f),*range(0xa1,0xff)]) if 0x4e00<=n<=0x9fff},
    }


def inspect(path, index):
    # 같은 모양의 네모(.notdef)를 지원 문자로 오판하지 않도록 문자표를 읽는다.
    with TTFont(path, fontNumber=index, lazy=True) as font:
        if font['head'].flags & 0x4000:  # 마지막 대체 글꼴은 실제 문자가 아닌 범위 기호를 그린다.
            return dict(languages=[],full_korean=False)
        chars={code for code,glyph in (font.getBestCmap() or {}).items() if glyph not in ('.notdef','glyph00000')}
    return dict(languages=[key for key,values in required().items() if values.issubset(chars)],
                full_korean=set(range(0xac00,0xd7a4)).issubset(chars))
