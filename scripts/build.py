"""source 자료로 독립형 치다분석기 사용설명서를 만든다."""
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source'
VERSION = '1.2.1'
chapters = json.loads((SOURCE / 'content.json').read_text())
shots = {(s['chapter'], s['item']): s for s in json.loads((SOURCE / 'shots.json').read_text())}
count = sum(len(c['rows']) for c in chapters)


def rich(text):
    parts = re.split(r'(https?://[^\s]+)', text)
    return ''.join(
        f'<a href="{html.escape(p, quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(p)}</a>'
        if p.startswith(('https://', 'http://')) else html.escape(p)
        for p in parts
    ).replace('\n', '<br>')


legacy = json.loads((SOURCE / 'legacy-links.json').read_text())
sections = []
for index, chapter in enumerate(chapters, 1):
    entries = []
    for item, row in enumerate(chapter['rows']):
        title, body, result, caution = row
        key = f"{chapter['id']}-guide-{item + 1}"
        old_links = ''.join(f'<span class="old-link" id="{anchor}"></span>' for anchor, target in legacy.items() if target == title)
        search = html.escape(' '.join([chapter['name'], *row]), quote=True)
        shot = shots.get((chapter['id'], title))
        image = ''
        if shot:
            source = 'screenshots/' + shot['source']
            caption = html.escape(shot['caption'], quote=True)
            image = f'''<figure class="shot"><button class="shot-button" type="button" data-source="{source}" data-caption="{caption}" aria-label="{html.escape(title, quote=True)} 화면 크게 보기"><img src="{source}" alt="{caption}" loading="lazy"></button><figcaption>{html.escape(shot['caption'])} <span>화면을 누르면 확대</span></figcaption></figure>'''
        warning = f'<p class="caution"><strong>주의</strong>{rich(caution)}</p>' if caution else ''
        entries.append(f'''<details class="entry" id="{key}" data-search="{search}">
          <summary>{old_links}<span>{html.escape(title)}</span><span class="toggle" aria-hidden="true"></span></summary>
          <div class="entry-body"><p>{rich(body)}</p><p class="result"><strong>확인할 점</strong>{rich(result)}</p>{warning}{image}</div>
        </details>''')
    sections.append(f'''<section id="{chapter['id']}" class="chapter" aria-labelledby="title-{chapter['id']}">
      <header class="chapter-head"><span class="chapter-no">{index:02}</span><div><h2 id="title-{chapter['id']}">{html.escape(chapter['name'])}</h2><p>{html.escape(chapter['intro'])}</p></div><a class="to-contents" href="#contents">목차</a></header>
      <div class="entries">{''.join(entries)}</div></section>''')

toc = ''.join(f'<li><a href="#{c["id"]}">{html.escape(c["name"])}</a></li>' for c in chapters)
styles = 'styles.css?v=' + hashlib.sha256((ROOT / 'styles.css').read_bytes()).hexdigest()[:12]
script = 'manual.js?v=' + hashlib.sha256((ROOT / 'manual.js').read_bytes()).hexdigest()[:12]
page = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>치다분석기 사용설명서 | v{VERSION}</title>
<meta name="description" content="치다분석기 v{VERSION}의 설치, 다시보기 등록, 전사, AI 문맥 분석, 외부 AI 결과 가져오기, 클립 편집, 믹스클립과 영상 나누기 사용법">
<meta name="color-scheme" content="dark light"><link rel="stylesheet" href="{styles}"><script src="{script}" defer></script></head>
<body><a class="skip" href="#content">본문으로 건너뛰기</a>
<header class="topbar"><a class="brand" href="#top" aria-label="치다분석기 사용설명서 처음으로"><img src="app-icon.png" alt="" width="30" height="30"><span>치다분석기 <small>사용설명서</small></span></a><div class="top-actions"><span class="version">앱 기준 v{VERSION}</span><button id="theme-toggle" type="button" aria-label="밝은 화면으로 전환">테마 전환</button></div></header>
<main id="content"><section class="hero" id="top"><div class="hero-kicker"><span class="live-dot"></span> 독립 도구 사용 안내</div><h1>치다분석기 <em>사용설명서</em></h1><p class="hero-copy">다시보기에서 댓글용 타임스탬프를 만들거나 여러 방송의 장면을 한 영상으로 엮어 보세요.</p>
<aside class="independent" aria-label="제휴 관계 안내"><span class="notice-icon">i</span><div><strong>치다분석기는 네이버 및 치지직과 아무런 제휴나 공식 관계가 없습니다.</strong><p>네이버와 치지직이 제공하거나 보증하는 앱이 아닌 독립 도구입니다. 서비스 이용 조건과 방송 자료의 권리를 확인한 뒤 사용해 주세요.</p></div></aside>
<div class="hero-actions"><a class="primary" href="#start">처음 쓰는 분 바로가기 <span aria-hidden="true">↘</span></a><a class="secondary-link" href="https://github.com/redpanya/Chi_Da_analyzer/releases/latest" target="_blank" rel="noopener noreferrer">앱 배포 페이지 ↗</a></div>
</section>
<section class="manual-tools" aria-label="설명서 도구"><label for="manual-search">설명서 검색</label><div class="search"><span aria-hidden="true">⌕</span><input id="manual-search" type="search" placeholder="기능이나 메뉴 이름 검색" autocomplete="off"><button id="clear-search" type="button" hidden>지우기</button></div><button id="expand-all" class="quiet" type="button" aria-expanded="false">모두 펼치기</button></section>
<nav class="contents" id="contents" aria-labelledby="contents-title"><h2 id="contents-title">주제별 목차</h2><ul>{toc}</ul></nav>
<p id="search-status" class="search-status" role="status" aria-live="polite">{len(chapters)}개 주제, {count}개 안내</p>
<div id="empty-state" hidden><h2>검색 결과가 없습니다.</h2><p>‘전사’, ‘화질’, ‘화자’처럼 짧은 단어로 찾아보세요.</p><button id="empty-clear" type="button">검색 지우기</button></div>
<noscript><p class="noscript">자바스크립트를 켜면 검색과 화면 확대 기능을 사용할 수 있습니다. 설명은 브라우저에서 확인할 수 있습니다.</p></noscript>
{''.join(sections)}
<footer><p class="footer-brand">치다분석기 <span>v{VERSION} 기준</span></p><p>치다분석기는 네이버 및 치지직과 제휴 또는 공식 관계가 없는 독립 도구입니다.</p><p>앱 설정의 ‘앱 정보’에서 사용 중인 버전을 확인할 수 있습니다.</p><p>화면에 나온 방송과 구간은 기능을 설명하기 위한 예시입니다.</p><a href="#top">맨 위로 ↑</a></footer></main>
<dialog id="image-dialog" aria-labelledby="image-caption"><div class="dialog-head"><p id="image-caption"></p><button id="close-image" type="button" autofocus>닫기</button></div><img id="enlarged-shot" alt=""></dialog></body></html>'''
(ROOT / 'index.html').write_text(page)
print(f'HTML 생성: {len(chapters)}개 주제, {count}개 안내, {len(shots)}개 화면 자료 연결')
