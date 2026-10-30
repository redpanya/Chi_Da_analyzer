"""표시용 계열과 변형 정보. 파일 ID나 글꼴 원본은 변경하지 않는다."""
from collections import defaultdict
import hashlib
import re
from fontTools.ttLib import TTFont

WEIGHTS = {'thin':100, 'extralight':200, 'ultralight':200, 'light':300,
           'regular':400, 'normal':400, 'medium':500, 'semibold':600,
           'demibold':600, 'bold':700, 'extrabold':800, 'ultrabold':800,
           'black':900, 'heavy':900}
SUFFIX = re.compile(r'(?i)(extra[ -]?light|ultra[ -]?light|semi[ -]?bold|demi[ -]?bold|extra[ -]?bold|ultra[ -]?bold|thin|light|regular|normal|medium|bold|black|heavy)$')


def normalized(value):
    return ' '.join(value.casefold().split())


def inspect(path, index, family, style):
    with TTFont(path, fontNumber=index, lazy=True) as font:
        names=font['name']; metrics=font.get('OS/2')
        preferred=names.getDebugName(16)
        variant=names.getDebugName(17) or style
        weight=int(getattr(metrics,'usWeightClass',400))
        italic=bool(getattr(metrics,'fsSelection',0)&1) or 'italic' in variant.casefold() or 'oblique' in variant.casefold()
        base=family; inferred=False
        # 확장 이름이 없는 구형 글꼴의 일관된 접미사만 후보로 삼는다.
        match=SUFFIX.search(family) if not preferred and normalized(style) in ('regular','normal') else None
        if match and match.start()>0:
            base=family[:match.start()].rstrip(' -_'); variant=match.group().replace('-', ' ')
            weight=WEIGHTS[re.sub('[ -]','',variant.casefold())]; inferred=True
        return dict(style=variant,weight=weight,italic=italic,width=int(getattr(metrics,'usWidthClass',5)),
                    family_name=preferred or family, family_candidate=base, family_inferred=inferred,
                    vendor=names.getDebugName(8) or str(getattr(metrics,'achVendID','')),
                    font_version=names.getDebugName(5) or '',font_format=path.suffix.lower().lstrip('.'))


def group(rows):
    candidates=defaultdict(list)
    for row in rows:
        if row['family_inferred']:
            candidates[(normalized(row['family_candidate']),normalized(row['vendor']),row['width'],row['italic'])].append(row)
    for row in rows:
        family=row['family_name']
        if row['family_inferred']:
            key=(normalized(row['family_candidate']),normalized(row['vendor']),row['width'],row['italic'])
            if len({r['weight'] for r in candidates[key]})>=2:family=row['family_candidate']
        row['family_name']=family
        # 동명인 다른 제작사와 서로 다른 폭을 임의로 합치지 않는다.
        key=f"{normalized(family)}|{normalized(row['vendor'])}|{row['width']}"
        row['family_id']=hashlib.sha256(key.encode()).hexdigest()[:24]
        row.pop('family_candidate',None)
    return rows
