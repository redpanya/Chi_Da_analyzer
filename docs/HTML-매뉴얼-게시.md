# HTML 매뉴얼 업로드와 웹 게시

작성일: 2026-10-16

## 현재 상태

사용자가 저장소를 공개로 변경한 뒤, `codex/manual-site` 브랜치의 HTML 사용설명서와 설명용 스크린샷을 GitHub Pages에 게시했습니다. 현재는 로그인이나 ZIP 다운로드 없이 웹에서 바로 열 수 있습니다.

- [매뉴얼 파일 보기](https://github.com/redpanya/Chi_Da_analyzer/tree/codex/manual-site)
- [매뉴얼 웹페이지 바로 열기](https://redpanya.github.io/Chi_Da_analyzer/)
- GitHub 저장소의 `index.html`은 소스 보기입니다. 실제 매뉴얼은 위 웹페이지 주소를 사용합니다.
- 매뉴얼 ZIP은 릴리스에 첨부하지 않았습니다. 기존 앱 릴리스·실행 파일은 유지했습니다.

## 적용한 게시 설정과 재설정 방법

1. 저장소의 공개 전환을 완료합니다.
2. **Settings → Pages**로 이동합니다.
3. **Build and deployment → Source**에서 **Deploy from a branch**를 선택합니다.
4. 브랜치는 **codex/manual-site**, 폴더는 **/(root)**로 지정하고 **Save**를 누릅니다.
5. Pages 배포가 완료되면 **Visit site**를 누릅니다. 사용자에게는 `https://redpanya.github.io/Chi_Da_analyzer/` 링크를 공유합니다.

별도의 ZIP 다운로드나 HTML 파일 실행이 필요 없습니다. 앞으로 같은 브랜치의 HTML·CSS·JavaScript·이미지를 수정해 푸시하면 Pages가 해당 내용을 배포합니다. Pages 활성화 이전에는 브랜치에 파일을 올리는 것만으로 웹페이지가 게시되지 않습니다.

GitHub Pages 공개와 저장소 공개는 서로 다른 설정입니다. 비공개 저장소에서 Pages를 이용할 수 있는지는 요금제에 따라 달라지며, 이용 가능하더라도 Pages 사이트는 인터넷에 공개될 수 있습니다. 처음에는 나중에 공개한다는 의사에 맞춰 보류했으며, 이후 사용자가 직접 저장소를 공개한 사실을 API로 확인한 뒤 게시를 활성화했습니다.

공식 안내: [GitHub Pages 소개](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages), [브랜치 게시 설정](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

## 포함 파일과 보존 범위

- 게시 브랜치는 매뉴얼 `index.html`, `styles.css`, `manual.js`, `screenshots/`의 실제 앱 화면 8장, 사용안내, README, `.nojekyll`만 포함합니다. 앱 소스의 커밋 내역과 분리한 루트 커밋으로 만들었습니다.
- `.nojekyll`은 정적 HTML·이미지를 Jekyll 변환 없이 게시하도록 둔 파일입니다.
- 9개 주제·102개 설명·33개 설명별 화면 배치와 검색·확대·기본 펼침을 유지했습니다.
- 앱 코드, 모델, 영상·음성·채팅 원본, 전사·요약 결과, 인증정보, 로컬 경로 설정, 백업 ZIP과 이전 미리보기 파일은 게시 브랜치에 넣지 않았습니다. 매뉴얼에 사용한 설명용 화면 이미지는 포함합니다.
- 앱의 기본 `main` 브랜치는 게시용으로 사용하지 않습니다. 매뉴얼 업데이트로 앱을 다시 패키징하지 않습니다.

## 확인 결과

- 매뉴얼 구조 검사 통과: 안내 102개·9개 주제, 설명별 화면 33곳, 원본 화면 8장 동일, 모든 설명 기본 펼침, 내부 링크·로컬 자원·이미지 영역 정상.
- 게시용 폴더의 매뉴얼 12개 파일이 기존 최신 `dist`와 바이트 단위로 일치합니다. README와 `.nojekyll`을 포함해 Git 추적 파일은 14개입니다.
- 매뉴얼 브랜치 커밋: `946f9e3`. 원격 업로드 완료.
- GitHub Pages 활성화는 자동 승인 검토에서 공개 범위 확인을 요구해 거절되었습니다. 이후 사용자가 저장소를 나중에 공개할 예정이라고 답해 활성화를 보류했습니다. 제한을 우회하거나 저장소를 공개하지 않았습니다.
- 2026-10-16 사용자 공개 전환 후 `private=false`를 확인했습니다. 동일 매뉴얼 브랜치만 게시 소스로 사용하는 Pages 활성화가 승인되어 완료됐습니다. 앞선 제한을 우회하지 않고 변경된 공개 상태와 사용자 요청을 근거로 다시 진행했습니다.
- [Pages 배포 실행](https://github.com/redpanya/Chi_Da_analyzer/actions/runs/38858422832): 성공. 소스는 `codex/manual-site`, 경로는 `/`입니다.
- 로그인 없는 공개 HTTPS 요청으로 HTML·CSS·JavaScript·스크린샷 8장, 총 11개 파일이 모두 HTTP 200을 반환하고 로컬 최신본과 SHA-256이 같음을 확인했습니다.
- 내부 브라우저에서 공개 URL의 문서 제목·본문·검색 입력·설명별 화면 버튼·기본 펼침 상태 표시를 확인했습니다. 검색 입력이나 확대 창 상호작용을 이번 게시 단계에서 다시 실행하지는 않았습니다.
