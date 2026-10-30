"""기존 매뉴얼을 보존하고, 오프라인에서도 열리는 HTML을 만든다."""
import html
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source'
OUT = ROOT
chapters = json.loads((SOURCE / 'content.json').read_text())
ids = [chapter['id'] for chapter in chapters]
stickers = [chapter['sticker'] for chapter in chapters]
shots = json.loads((SOURCE / 'shots.json').read_text())
shot_map = {(shot['chapter'], shot['item']): shot for shot in shots}
dimensions = json.loads((SOURCE / 'images.json').read_text())
count = sum(len(c['rows']) for c in chapters)

def rich(text):
    parts = re.split(r'(https?://[^\s]+)', text)
    return ''.join(f'<a href="{html.escape(p, quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(p)}</a>'
                   if p.startswith(('https://', 'http://')) else html.escape(p) for p in parts).replace('\n', '<br>')

def illustration(chapter, item, key):
    shot = shot_map.get((chapter, item))
    if not shot:
        return ''
    x, y, w, h = shot['crop']
    iw, ih = dimensions[shot['source']]
    src = f"screenshots/{shot['source']}"
    # 원본 이미지를 변형하지 않고 HTML의 표시 범위만 제한한다.
    position = f'width:{iw/w*100:.5f}%;left:{-x/w*100:.5f}%;top:{-y/h*100:.5f}%'
    markers = []
    for fx, fy, fw, fh in shot['focus']:
        markers.append(f'<rect x="{fx-x}" y="{fy-y}" width="{fw}" height="{fh}" rx="4"/>')
    if shot['focus']:
        fx, fy, fw, fh = shot['focus'][0]
        # 버튼의 글씨를 가리지 않도록 테두리 밖의 여백에서 가리킨다.
        end_x, end_y = fx-x+fw/2, fy-y-2
        if end_y >= 22:
            markers.append(f'<path d="M {end_x} 3 L {end_x} {end_y}" marker-end="url(#{key}-arrow)"/>')
    overlay = f'''<svg class="shot-marks" viewBox="0 0 {w} {h}" aria-hidden="true"><defs><marker id="{key}-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7Z"/></marker></defs>{''.join(markers)}</svg>''' if markers else ''
    caption = html.escape(shot['caption'])
    return f'''<figure class="inline-shot" style="max-width:{min(760, w*1.4):.0f}px"><button class="image-button" type="button" aria-label="{html.escape(item)} 화면 크게 보기" data-caption="{caption}" data-source="{src}">
       <span class="shot-viewport" style="aspect-ratio:{w}/{h};--crop-width:{w}"><img src="{src}" width="{iw}" height="{ih}" alt="{caption}" loading="lazy" style="{position}">{overlay}</span></button>
       <figcaption><span class="image-key">화면 참고</span> {caption} <span class="image-action">클릭하면 확대</span></figcaption></figure>'''

sections = []
for n, chapter in enumerate(chapters):
    name = chapter['name']
    entries = []
    for k, row in enumerate(chapter['rows']):
        search = html.escape(' '.join(row), quote=True)
        key = f'{ids[n]}-{k+1}'
        picture = illustration(ids[n], row[0], key)
        entries.append(f'''<details class="entry" id="{key}" data-search="{search}" open>
          <summary><span>{html.escape(row[0])}</span><span class="plus" aria-hidden="true">+</span></summary>
          <div class="entry-body"><p>{rich(row[1])}</p><p class="outcome">{rich(row[2])}</p><p class="note">{rich(row[3])}</p>{picture}</div>
        </details>''')
    sections.append(f'''<section id="{ids[n]}" class="chapter" aria-labelledby="heading-{ids[n]}">
       <header class="chapter-heading"><div class="chapter-number">{n:02}</div><div><h2 id="heading-{ids[n]}">{html.escape(name)}</h2><p>{html.escape(chapter['intro'])}</p></div><span class="chapter-stamp" aria-hidden="true">{stickers[n]}</span></header>
       <div class="entries">{"".join(entries)}</div></section>''')

versioned_assets = {name: f'{name}?v={hashlib.sha256((OUT/name).read_bytes()).hexdigest()[:12]}'
                  for name in ('styles.css', 'pattern-background.css', 'pattern-background.js')}
page = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>치다 분석기 사용설명서 — 다시보기, 빠르게 이해하기</title>
<meta name="description" content="치다 분석기 preview.8 사용설명서. 구간 다운로드, 전사, AI 세 모드, 댓글, 클립 편집, 자막과 PNG, 영상 나누기, 오류 기록 사용법.">
<meta name="color-scheme" content="light"><link rel="stylesheet" href="{versioned_assets['styles.css']}"><link rel="stylesheet" href="{versioned_assets['pattern-background.css']}"><script src="{versioned_assets['pattern-background.js']}" defer></script><script src="manual.js" defer></script></head>
<body><a class="skip" href="#content">본문으로 바로가기</a>
<header class="masthead"><a class="brand" href="#top" aria-label="치다 분석기 사용설명서 처음으로"><span class="brand-icon" aria-hidden="true">↙</span><span>치<small>(지직)</small> 다<small>(시보기)</small> 분석기</span></a><span class="masthead-label">사용설명서 <span class="edition">preview.8</span></span></header>
<div class="layout">
<main id="content"><div id="top" class="hero"><div class="hero-topline"><span class="eyebrow">★ 치다 분석기 사용설명서 ★</span><span class="hero-edition">※ 나름 진지한 설명서입니다</span></div>
<div class="flyer-strip" aria-hidden="true"><span>설치!</span><span>전사!</span><span>요약!</span><span>암튼 다 알려줌 →</span></div>
<div class="hero-grid"><div class="hero-copy"><h1>다시보기<br><em>언제 다 봄?</em></h1><p>영상 가져오기부터 AI 요약, 댓글 정리와 클립 제작까지.<br>누를 버튼은 아래에 다 적어놨어요. 진짜로.</p>
<div class="hero-actions"><a class="primary" href="#setup">설치부터 시작하기 <span aria-hidden="true">↗</span></a><a class="text-link" href="#summary">요약부터 볼래요 →</a></div></div>
<div class="hero-art" aria-hidden="true"><span class="art-note">아~ 사용법?<br>여기 있잖아.</span><span class="art-spark">★</span><div class="smile-sticker"><span class="cheap-face">(ง •̀_•́)ง</span><strong>야 르.</strong><small>멋은 덜 챙김<br>설명은 챙김</small></div><span class="art-arrow">↙</span></div></div>
<div class="quick-route" aria-label="간단한 사용 순서"><a href="#import"><span>01</span>영상 가져오기</a><b aria-hidden="true">→</b><a href="#transcribe"><span>02</span>말을 글로</a><b aria-hidden="true">→</b><a href="#summary"><span>03</span>AI로 요약</a><b aria-hidden="true">→</b><a href="#comments"><span>04</span>댓글로 공유</a></div>
<p class="edition-update"><strong>★ preview.8 사용법까지 챙겼다 ★</strong><br>구간 다운로드 · AI 세 모드 · 댓글 시각 편집 · 자막·PNG 클립 제작 · 무인코딩 영상 나누기<br><a href="https://github.com/redpanya/Chi_Da_analyzer/releases/tag/v0.20.0-preview.8" target="_blank" rel="noopener noreferrer">앱 다운로드 ↗</a> · <a href="#external">외부 AI 사용법</a> · <a href="#clips">클립 만들기</a> · <a href="#split">영상 나누기</a> · <a href="#reports">오류·문의</a></p><p class="hero-footnote">채팅 반응도 보고 싶다면 <a href="#explore">통합 분석</a>을 함께 사용하세요. 화자 구분은 건너뛰어도 됩니다.</p></div>
<div class="tools" id="manual-tools"><div class="search-box"><label for="manual-search">설명서 검색</label><input id="manual-search" type="search" placeholder="예: 모델 준비, 요약 실패, 댓글" autocomplete="off"><button id="clear-search" type="button" hidden>검색 지우기</button></div><button class="quiet" id="expand-all" type="button" aria-expanded="true">모두 접기</button></div>
<p id="search-status" class="search-status" role="status" aria-live="polite">{len(chapters)}개 주제 · {count}개 안내 · 설명 바로 아래 화면 참고</p>
<div id="empty-state" hidden><h2>찾는 안내가 없어요.</h2><p>‘전사’, ‘모델’, ‘댓글’처럼 짧은 단어로 다시 검색해 보세요.</p><button type="button" id="empty-clear">전체 안내 보기</button></div>
<noscript><p class="noscript">검색·화면 확대는 자바스크립트가 필요합니다. 설명은 모두 펼쳐져 있고, 이미지는 브라우저 확대 기능으로 확인할 수 있어요.</p></noscript>
{''.join(sections)}
<footer><span class="footer-sticker" aria-hidden="true">☆ 설명서 엔딩 ☆</span><strong>여기까지 읽음?<br>당신… 제법인데.</strong><p>막히면 다시 와요. 설명서는 도망 안 갑니다.</p><p>2026.10.31 · v0.20.0-preview.8 기준. 새 버전에서는 메뉴와 지원 범위가 달라질 수 있습니다.</p><p>화면은 가상의 설명용 자료입니다. 실제 분석 품질·성능 측정 결과가 아닙니다.<br>이 페이지는 사용설명서이며 방송 자료를 읽거나 처리하지 않습니다.</p><a href="#top">처음으로 한 번 더 ↑</a></footer></main></div>
<dialog id="image-dialog" aria-labelledby="image-caption"><div class="dialog-top"><p id="image-caption"></p><button type="button" id="close-image" autofocus>닫기 ×</button></div><div class="dialog-image" id="enlarged-shot"></div><p class="dialog-tip"><a id="original-shot" target="_blank" rel="noopener">전체 원본 화면 보기 ↗</a> · Esc로 닫기</p></dialog>
</body></html>'''
OUT.mkdir(exist_ok=True)
(OUT / 'index.html').write_text(page)

print(f'HTML 생성: {len(chapters)}개 주제, {sum(len(c["rows"]) for c in chapters)}개 안내')
