# HTML 매뉴얼 게시

공개 주소: https://redpanya.github.io/Chi_Da_analyzer/

GitHub Pages는 `codex/manual-site` 브랜치의 루트(`/`)를 게시합니다. 앱 소스는 `main`에서 관리합니다.

## 수정과 확인

- 안내 내용: `source/content.json`
- 설명별 스크린샷 배치: `source/shots.json`
- 스크린샷 원본 크기: `source/images.json`
- HTML 생성: `python3 scripts/build.py`
- 구조, 링크, 스크린샷 범위 검사: `python3 scripts/check.py`
- 자바스크립트 구문 검사: `node --check manual.js`

검사를 마치고 매뉴얼 브랜치를 푸시한 뒤 Pages 배포 완료를 확인합니다. 매뉴얼 수정에는 앱 패키징이 필요하지 않습니다. 오프라인 안내에는 HTML, CSS, JavaScript, patterns, screenshots를 함께 보관합니다.

앱 다운로드는 https://github.com/redpanya/Chi_Da_analyzer/releases/latest 를 사용합니다. 과거 게시 과정과 삭제한 구형 화면은 Git 이력에서 확인할 수 있습니다.
