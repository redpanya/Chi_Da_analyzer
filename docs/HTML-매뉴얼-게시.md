# HTML 매뉴얼 업로드와 웹 게시 준비

작성일: 2026-10-16

## 현재 상태

HTML 사용설명서와 설명용 스크린샷을 같은 비공개 저장소의 `codex/manual-site` 브랜치에 업로드했습니다. 사용자가 저장소를 나중에 공개하기로 했으므로, 현재 GitHub Pages는 활성화하지 않았습니다.

- [매뉴얼 파일 보기](https://github.com/redpanya/Chi_Da_analyzer/tree/codex/manual-site)
- 게시 후 사용할 주소: `https://redpanya.github.io/Chi_Da_analyzer/`
- 위 웹 주소는 아직 활성화된 매뉴얼 링크가 아닙니다. GitHub 파일 보기에서 `index.html`을 누르면 소스가 표시되며, 실제 웹페이지로 보려면 아래 Pages 설정이 필요합니다.
- 매뉴얼 ZIP은 릴리스에 첨부하지 않았습니다. 기존 앱 릴리스·실행 파일은 유지했습니다.

## 저장소를 공개한 뒤 웹페이지 열기

1. 저장소의 공개 전환을 완료합니다.
2. **Settings → Pages**로 이동합니다.
3. **Build and deployment → Source**에서 **Deploy from a branch**를 선택합니다.
4. 브랜치는 **codex/manual-site**, 폴더는 **/(root)**로 지정하고 **Save**를 누릅니다.
5. Pages 배포가 완료되면 **Visit site**를 누릅니다. 사용자에게는 `https://redpanya.github.io/Chi_Da_analyzer/` 링크를 공유합니다.

별도의 ZIP 다운로드나 HTML 파일 실행이 필요 없습니다. 앞으로 같은 브랜치의 HTML·CSS·JavaScript·이미지를 수정해 푸시하면 Pages가 해당 내용을 배포합니다. Pages 활성화 이전에는 브랜치에 파일을 올리는 것만으로 웹페이지가 게시되지 않습니다.

GitHub Pages 공개와 저장소 공개는 서로 다른 설정입니다. 비공개 저장소에서 Pages를 이용할 수 있는지는 요금제에 따라 달라지며, 이용 가능하더라도 Pages 사이트는 인터넷에 공개될 수 있습니다. 이번에는 사용자의 나중에 공개한다는 의사에 맞춰 게시를 보류했습니다.

공식 안내: [GitHub Pages 소개](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages), [브랜치 게시 설정](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

## 포함 파일과 보존 범위

- 게시 브랜치는 매뉴얼 `index.html`, `styles.css`, `manual.js`, `screenshots/`의 실제 앱 화면 8장, 사용안내, README, `.nojekyll`만 포함합니다. 앱 소스의 커밋 내역과 분리한 루트 커밋으로 만들었습니다.
- `.nojekyll`은 정적 HTML·이미지를 Jekyll 변환 없이 게시하도록 둔 파일입니다.
- 9개 주제·102개 설명·33개 설명별 화면 배치와 검색·확대·기본 펼침을 유지했습니다.
- 앱 코드, 모델, 영상·음성·채팅 원본, 전사·요약 결과, 인증정보, 로컬 경로 설정, 백업 ZIP과 이전 미리보기 파일은 게시 브랜치에 넣지 않았습니다. 매뉴얼에 사용한 설명용 화면 이미지는 포함합니다.
- 앱의 기본 `main` 브랜치는 게시용으로 사용하지 않습니다. 매뉴얼 업데이트로 앱을 다시 패키징하지 않습니다.

## 확인 결과와 남은 작업

- 매뉴얼 구조 검사 통과: 안내 102개·9개 주제, 설명별 화면 33곳, 원본 화면 8장 동일, 모든 설명 기본 펼침, 내부 링크·로컬 자원·이미지 영역 정상.
- 게시용 폴더의 매뉴얼 12개 파일이 기존 최신 `dist`와 바이트 단위로 일치합니다. README와 `.nojekyll`을 포함해 Git 추적 파일은 14개입니다.
- 매뉴얼 브랜치 커밋: `946f9e3`. 원격 업로드 완료.
- GitHub Pages 활성화는 자동 승인 검토에서 공개 범위 확인을 요구해 거절되었습니다. 이후 사용자가 저장소를 나중에 공개할 예정이라고 답해 활성화를 보류했습니다. 제한을 우회하거나 저장소를 공개하지 않았습니다.
- Pages 배포, 실제 웹 주소 응답, 게시된 화면의 검색·확대 동작은 아직 검증하지 않았습니다. 공개 후 Pages 활성화와 해당 검증이 남아 있습니다.
