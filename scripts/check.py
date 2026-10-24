"""설명·링크·화면 표시 범위의 정합성을 검사한다."""
import json
import hashlib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

root = Path(__file__).resolve().parents[1]
source = json.loads((root/'source/content.json').read_text())
shots = json.loads((root/'source/shots.json').read_text())
dimensions = json.loads((root/'source/images.json').read_text())

class Manual(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.targets, self.assets = [], [], []
        self.entries, self.images, self.chapters = 0, 0, 0
        self.stack, self.image_entries = [], set()
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        assert tag not in ('aside', 'nav'), '왼쪽 차례가 남음'
        if 'id' in a: self.ids.append(a['id'])
        if tag == 'section' and a.get('class') == 'chapter': self.chapters += 1
        if tag == 'details' and a.get('class') == 'entry':
            self.entries += 1
            assert a.get('data-search'), '검색 원문 누락'
            assert 'open' in a, '기본으로 접힌 설명'
            self.stack.append(a['id'])
        if tag == 'a' and a.get('href', '').startswith('#'): self.targets.append(a['href'][1:])
        if tag in ('img', 'script') and 'src' in a: self.assets.append(a['src'])
        if tag == 'link' and a.get('rel') == 'stylesheet': self.assets.append(a['href'])
        if tag == 'img' and 'src' in a:
            self.images += 1
            assert a.get('alt'), '화면 설명 누락'
            assert self.stack, '설명 밖으로 분리된 스크린샷'
            self.image_entries.add(self.stack[-1])
    def handle_endtag(self, tag):
        if tag == 'details': self.stack.pop()

p=Manual(); page=(root/'index.html').read_text(); p.feed(page)
assert p.entries == sum(len(c['rows']) for c in source)
assert p.chapters == len(source) and p.images == len(shots)
assert len(p.image_entries) == len(shots), '화면이 한 설명에 몰림'
assert len(p.ids) == len(set(p.ids)), '중복 ID'
assert set(p.targets) <= set(p.ids), '깨진 내부 링크'
for asset in p.assets:
    assert not asset.startswith(('http:', 'https:', '//')), '외부 필수 자원'
    path = root/urlsplit(asset).path
    assert path.is_file(), f'빠진 자원: {asset}'
    if path.name in ('styles.css', 'pattern-background.css', 'pattern-background.js'):
        assert parse_qs(urlsplit(asset).query).get('v') == [hashlib.sha256(path.read_bytes()).hexdigest()[:12]], '스타일·배경 캐시 버전 불일치'
labels={c['id']:{r[0] for r in c['rows']} for c in source}
assert len({(s['chapter'],s['item']) for s in shots}) == len(shots)
for s in shots:
    assert s['item'] in labels[s['chapter']], '화면 연결 대상 없음'
    x,y,w,h=s['crop']; iw,ih=dimensions[s['source']]
    assert 0 <= x < x+w <= iw and 0 <= y < y+h <= ih, f'원본 밖 자르기: {s}'
    for fx,fy,fw,fh in s['focus']:
        assert x <= fx < fx+fw <= x+w and y <= fy < fy+fh <= y+h, f'잘린 버튼 표시: {s}'
for stale in ('0.18.0', 'preview.5', '실제 화면 8장', '102개 안내'):
    assert stale not in page, f'이전 버전 안내: {stale}'
assert 'v0.20.0-preview.2' in page
assert '/Users/brightp' not in page and 'vod-15655103' not in page
print(f'통과: {p.chapters}개 주제 · {p.entries}개 기본 펼침 · 설명별 화면 {p.images}개 · 링크/로컬 자원/크롭/표시 경계')
