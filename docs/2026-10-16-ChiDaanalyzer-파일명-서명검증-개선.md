# ChiDaanalyzer 파일명과 배포 서명 검사 개선

작성일: 2026-10-16. 기존 원본·분석·설정과 이전 앱·배포 초안은 유지한다. DMG는 만들지 않는다.

## 변경 내용

- macOS 앱 파일명·Finder 표시 이름은 `ChiDaanalyzer.app`·`ChiDaanalyzer`로 변경한다. 앱 안의 한국어 제목·설명은 유지한다.
- Windows 포터블 폴더·실행 파일은 `ChiDaanalyzer/ChiDaanalyzer.exe`, 배포 ZIP은 `ChiDaanalyzer-macOS-arm64.zip`·`ChiDaanalyzer-Windows-x64.zip`으로 통일한다. GitHub 저장소 이름은 변경하지 않는다.
- macOS 번들 내부의 사용 안내를 `README.ko.md`로 바꾸고, 기존 전체 엔진용 로컬 조립 스크립트의 안내 디렉터리도 `NOTICES`·`third-party`로 바꾼다. 안내 내용은 한국어로 유지한다.
- 파일·디렉터리 이름과 심볼릭 링크 대상에 비ASCII 이름이 들어오면 빌드를 실패시킨다. 서명 뒤 파일 이름을 자동 교체하지 않는다.
- 최종 ZIP을 `ditto`와 macOS 기본 `unzip`으로 각각 해제하고 두 앱의 서명을 다시 검사한다. ASCII 경로는 NFC/NFD 정규화로 달라지지 않으므로 같은 유형의 한글 리소스 서명 손상을 예방한다.
- LaunchServices의 `open`으로 실제 Swift 앱을 시작하고 그 앱이 만든 서버의 HTTP 응답을 확인한다. 검사에 사용할 빈 보관함을 별도로 지정하고 해당 검사 프로세스만 종료한다. 내부 서버 직접 실행 검사와 별도로 수행한다.
- Gatekeeper 결과를 검사 보고서의 `macos_distribution.gatekeeper`에 별도로 남긴다. 임시 서명 앱의 시작 성공을 인터넷 다운로드 앱의 첫 실행 허용으로 간주하지 않는다.

## 보존·예외와 영향

번들 식별자 `local.chzzk.archive`, 기존 macOS 설정·모델·로그 경로와 Windows AppData 경로는 유지한다. 앱 이름 변경으로 보관함을 이동하거나 기존 전사·수동 교정·화자 배정·요약을 변경하지 않는다. 기존 앱을 종료한 뒤 새 앱을 실행한다. 예전 앱을 자동 삭제하지 않으므로 필요하면 사용자가 정리한다.

Windows 바로가기·외부 실행 스크립트가 이전 실행 파일을 가리킨다면 새 파일 경로로 바꿔야 한다. 이번 패키징 변경은 영상 다운로드·시간축·채팅 복구 로직을 바꾸지 않는다.

ZIP 손상·서명 실패·파일명 정책 위반·실행기 준비 실패·검사 서버 종료 실패는 CI 실패로 처리하며 배포 아티팩트 업로드 단계에 도달하지 못하게 한다. 저장소 공개 전환과 기존 초안 덮어쓰기는 수행하지 않는다. 검사 프로세스 식별은 파일 동일성으로 확인해 macOS의 `/var`·`/private/var` 별칭을 구분 오류로 처리하지 않는다. 한글 세션 폴더는 NFC/NFD를 정규화해 찾는다.

Developer ID 인증서·Apple 공증은 이번 변경에 포함하지 않는다. 임시 서명 배포본은 Gatekeeper에서 계속 거부될 수 있다. 보안 속성 제거·전역 보안 해제·앱 실행 허용 예외 자동 등록은 하지 않는다. 일반 사용자에게 경고 없이 배포하려면 별도 Developer ID 서명·공증·실제 다운로드 후 첫 실행 확인이 필요하다.

## 검증 기록

- 기존 배포본을 별도 작업 폴더에 복사해 검사했고 기존 한글 `사용안내.md`를 새 파일명 검사에서 거부하는 것을 확인했다.
- 그 복사본의 앱 이름·내부 안내 파일·번들 표시 이름을 바꾸고 임시 서명한 검증 ZIP으로 검사했다. `ditto`·`unzip` 해제본 모두 서명 통과, LaunchServices 실제 앱 시작·서버 응답 통과.
- 로컬 macOS 27.0.1의 Gatekeeper 평가는 `rejected`였다. `notarized=false`, `downloaded_first_launch_verified=false`를 유지한다. 사용자 다운로드 앱과 시스템 보안 설정은 바꾸지 않았다.
- 빌드 스크립트 11개의 구문 검사 통과. 서버 기능 변경은 없으며 모델 추론·장시간 영상 처리를 다시 실행하지 않았다.
- 전체 엔진용 로컬 조립 스크립트는 이름·내부 경로를 수정했지만 해당 대용량 패키지의 재빌드는 수행하지 않았다.
- 코드 커밋 `a5d8ec29f87de22640ec84abffe00d2626f76c89`의 [GitHub Actions 38774722602](https://github.com/redpanya/Chi_Da_analyzer/actions/runs/38774722602)에서 macOS arm64·Windows x64 빌드와 패키지 검사가 모두 통과했다. macOS 작업은 `116559280994`, Windows 작업은 `116559280442`다.
- 내려받은 macOS 검사 보고서에서 ZIP 해제 후 서명·ASCII 경로·LaunchServices 앱 실행·HTTP 응답이 모두 참이다. 영상 복구·원음 추출·채팅 누락 1건 보완·네트워크 요청 0회·기존 파일 보존 검사도 통과했다. ZIP 내부의 최상위 이름은 `ChiDaanalyzer.app`이며 비ASCII 경로는 없다.
- CI의 Gatekeeper 결과도 `accepted=false`, `returncode=3`, `rejected`다. 빌드 검사가 성공했다는 이유로 공증이나 다운로드 앱의 첫 실행 검증을 통과했다고 표시하지 않는다.
- Windows 보고서는 `text_encoding=cp1252`, `python_utf8_mode=0`에서 원음 조회·추출·저장 원본 복구·채팅 보완·기존 파일 보존 모두 통과다. 내려받은 ZIP에 새 `ChiDaanalyzer/ChiDaanalyzer.exe`가 있음을 확인했다. 두 앱 ZIP에 모델 가중치·영상·음성 파일이 포함되지 않았음을 확인했다.

로컬 증거: 작업 공간 `outputs/macos-ascii-package-20261016/validation.json`. 최종 배포본은 GitHub Actions에서 소스부터 다시 만든 산출물을 사용한다.

## 배포 자료

`v0.18.0-preview.5`의 실행 코드는 위 빌드 커밋이다. 빌드 뒤 검증 기록을 추가하는 문서 커밋은 실행 파일을 변경하지 않는다.

| 파일 | 크기 (바이트) | SHA-256 |
| --- | ---: | --- |
| `ChiDaanalyzer-macOS-arm64.zip` | 102,066,643 | `794f115943a90316e6dec5bac0d82843079bdcf3137331e6077a76f9761b75eb` |
| `ChiDaanalyzer-Windows-x64.zip` | 126,718,377 | `5696e936a9e1cc119277f69646c51ab2d204b519d3ddfe8f89ea030e9b0dbf57` |

각 OS의 검사 보고서, 네이티브 도구 대응 소스 ZIP, `SHA256SUMS.txt`도 함께 제공한다. 아티팩트 체크섬 검사를 거쳐 릴리스 자료를 구성했다.

2026-10-16 [비공개 초안 v0.18.0-preview.5](https://github.com/redpanya/Chi_Da_analyzer/releases/tag/untagged-e734909fe3197ef15a4e)에 6개 자료 업로드를 완료했다. 서버의 초안·사전 검증 상태, 대상 커밋, 모든 자료의 크기·SHA-256 일치를 확인했다. 기존 초안은 보존했으며 저장소 공개 전환이나 정식 릴리스 게시는 하지 않았다.
