# 치다 분석기 HTML 사용설명서

[바로 열기](https://redpanya.github.io/Chi_Da_analyzer/) · [앱 다운로드](https://github.com/redpanya/Chi_Da_analyzer/releases/tag/v0.20.0-preview.4)

2026-10-26, 앱 0.20.0-preview.4 기준. 11개 주제·63개 안내와 설명 위치에 배치한 화면 32개입니다. 화면은 가상의 예시 자료로 촬영했으며 실제 AI 품질·성능 측정 결과가 아닙니다.

왼쪽 차례 없이 기본 펼침, 검색, 화면 확대, 오프라인 열기를 지원합니다. `index.html`, `styles.css`, `manual.js`, `pattern-background.css`, `pattern-background.js`, `patterns/`, `screenshots/`를 함께 보관하세요. 기존 전단지 디자인은 유지하며, 페이지를 열 때 픽셀 패턴 8종 중 하나를 연한 배경으로 표시합니다.

## 수정·확인

- 본문: `source/content.json`
- 화면 배치·강조: `source/shots.json`, `source/images.json`
- 생성: `python3 scripts/build.py`
- 정합성 확인: `python3 scripts/check.py`, `node --check manual.js`

GitHub Pages는 `codex/manual-site` 브랜치 루트에서 게시합니다. 소스 앱 변경·패키징과는 별개입니다. 삭제된 다른 outputs 폴더에 의존하지 않습니다.
