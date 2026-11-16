"""생성된 설명서의 문서 연결과 로컬 화면 파일을 확인한다."""
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
chapters = json.loads((ROOT / 'source/content.json').read_text())
shots = json.loads((ROOT / 'source/shots.json').read_text())


class Manual(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.targets, self.assets, self.entries, self.chapters = [], [], [], 0, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag == 'section' and attrs.get('class') == 'chapter':
            self.chapters += 1
        if tag == 'details' and attrs.get('class') == 'entry':
            self.entries += 1
            assert attrs.get('data-search'), '검색 원문 누락'
        if tag == 'a' and attrs.get('href', '').startswith('#'):
            self.targets.append(attrs['href'][1:])
        if tag in ('img', 'script') and attrs.get('src'):
            self.assets.append(attrs['src'])
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.assets.append(attrs['href'])


page = (ROOT / 'index.html').read_text()
parser = Manual()
parser.feed(page)
assert parser.chapters == len(chapters), '주제 수 불일치'
assert parser.entries == sum(len(c['rows']) for c in chapters), '안내 수 불일치'
assert len(parser.ids) == len(set(parser.ids)), '중복 ID'
assert set(parser.targets) <= set(parser.ids), '끊어진 내부 링크'
assert '네이버 및 치지직과 아무런 제휴나 공식 관계가 없습니다' in page, '첫 안내 관계 고지 누락'
assert page.index('독립 도구 사용 안내') < page.index('class="chapter"'), '관계 고지는 첫 안내보다 먼저 표시해야 함'
assert '/releases/latest' in page, '최신 배포 링크 누락'
assert not re.search(r'/Users/|/Volumes/|[A-Za-z]:[\\/]Users[\\/]', page), '개인 경로 노출'
for asset in parser.assets:
    path = ROOT / urlsplit(asset).path
    assert path.is_file(), f'빠진 로컬 자원: {asset}'
    assert not asset.startswith(('http:', 'https:', '//')), f'외부 필수 자원: {asset}'
for shot in shots:
    assert (ROOT / 'screenshots' / shot['source']).is_file(), f"빠진 앱 화면: {shot['source']}"
rows = {(c['id'], row[0]) for c in chapters for row in c['rows']}
assert len(rows) == parser.entries, '같은 주제에 중복된 안내 제목'
assert all(c['id'] in parser.targets for c in chapters), '목차에서 도달할 수 없는 주제'
legacy = json.loads((ROOT / 'source/legacy-links.json').read_text())
assert set(legacy) <= set(parser.ids), '이전 개별 안내 링크 누락'
keys = [(shot['chapter'], shot['item']) for shot in shots]
assert len(keys) == len(set(keys)) and set(keys) <= rows, '화면 자료에 대응하는 안내 제목 확인 필요'
assert all(shot['caption'] and 'screenshots/' + shot['source'] in parser.assets for shot in shots), '화면 연결 누락'
assert 'v1.2.1' in page, '앱 기준 버전 확인 필요'
print(f'확인 완료: {len(chapters)}개 주제, {parser.entries}개 안내, {len(shots)}개 화면 연결')
