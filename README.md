# 치다 분석기 HTML 사용설명서

[매뉴얼 바로 열기](https://redpanya.github.io/Chi_Da_analyzer/) · [앱 다운로드](https://github.com/redpanya/Chi_Da_analyzer/releases/tag/v0.20.0-preview.8)

2026-10-31, v0.20.0-preview.8 기준. 13개 주제·83개 안내·설명별 화면 37개입니다. 구간 다운로드·부분 분석, AI 세 모드, 댓글 시간 편집, 클립 편집·자막·PNG, 오디오 트랙을 선택하는 영상 나누기, 오류 기록 안내를 포함합니다.

화면은 별도 가상 자료로 촬영했습니다. 실제 AI 품질·처리 성능 측정 결과가 아닙니다. 설명 기본 펼침, 검색, 화면 확대, 8종 픽셀 배경과 기존 디자인을 유지합니다.

## 수정·확인

- 본문: `source/content.json`
- 화면 배치·강조: `source/shots.json`, `source/images.json`
- 생성: `python3 scripts/build.py`
- 확인: `python3 scripts/check.py`, `node --check manual.js`
- 이번 변경·검증: [작업 기록](docs/2026-10-31-매뉴얼-preview8-업데이트.md)

GitHub Pages는 `codex/manual-site` 브랜치 루트에서 게시합니다. 앱 코드·패키징과는 별개입니다. 오프라인에서는 `index.html`, CSS·JS 파일, `patterns/`, `screenshots/`를 함께 보관하세요.
