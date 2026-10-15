# 치(지직) 다(시보기) 분석기

다시보기를 AI로 요약하는 로컬 프로그램입니다. 치지직 VOD·제공 채팅을 저장하고, 음성을 전사한 뒤 Gemma로 문맥을 정리합니다. 저장 영상과 채팅 반응을 시간순으로 탐색하고 댓글용 타임스탬프를 편집·복사할 수 있습니다.

현재 **비공개 사전 검증판**입니다. 모델·VOD·인증정보는 저장소에 포함하지 않습니다.

## 사용

- [배포·사용 안내](docs/배포-사용안내.md)
- [빌드·배포와 검증 기준](docs/GitHub-빌드-배포.md)
- [진행 결과와 남은 검증](docs/GitHub-구현기록.md)

Actions → **앱 빌드** → Run workflow에서 macOS Apple Silicon 앱 ZIP과 Windows x64 CPU 포터블 ZIP을 만듭니다. `draft_tag`가 비어 있으면 아티팩트만 생성하며, 태그를 넣으면 두 OS 검사 성공 후 초안 Release를 생성합니다. 비공개 상태에서는 접근 권한을 가진 사용자만 다운로드할 수 있습니다.

모델은 실행 후 다운로드합니다. macOS는 Metal, 첫 Windows 기준판은 CPU 추론입니다. FluidAudio와 pyannote는 기본 ZIP에 포함하지 않습니다. Windows GPU 가속과 장시간 실제 모델 추론은 후속 검증 대상입니다.

## 개발

Python 3.11 환경에서 `packaging/release/requirements.txt`를 설치합니다. 기본 앱은 `python app.py`로 실행합니다. 소스 실행의 sherpa 작업을 사용하려면 가상환경 이름을 `.voice-venv`로 만듭니다. FFmpeg·ffprobe·whisper-cli·llama-server·llama-tokenize·llama-completion은 PATH에서 찾을 수 있어야 합니다. 재현 가능한 네이티브 도구 빌드 방법은 빌드 문서를 참고하세요.

이 저장소의 자체 코드에 대한 공개 라이선스는 아직 정하지 않았습니다. 공개 전 소유자가 선택해야 하며, 제3자 구성요소와 모델은 각 배포처의 라이선스를 따릅니다. 배포 ZIP에는 구성요소 고지를, Release에는 빌드한 네이티브 도구의 대응 소스를 함께 제공합니다.
