# GitHub 배포용 기본 패키지

`docs/GitHub-빌드-배포.md`의 순서로 각 운영체제에서 빌드합니다. 공식 Electron 앱은 이 폴더의 `backend.spec`과 `assemble.py`로 만들며 FFmpeg와 ffprobe를 포함합니다. sherpa와 ONNX Runtime은 사용 시 모델 폴더의 화자 실행 도구로 설치합니다.

기존 `packaging/build_macos.py`는 Swift 실행기와 로컬에서 지정한 pyannote 및 FluidAudio 도구를 조립하던 개발용 경로입니다. 공식 Electron 앱, DMG 및 Windows 포터블 빌드는 이 스크립트를 호출하지 않습니다.

모델, 개발 가상환경, 개인 보관함, 자격증명, 이전 앱 패키지는 업로드하지 않습니다. `sources.json`의 해시가 다르면 빌드를 중단합니다. 모든 빌드 및 앱의 상태 자료는 `build`, `dist`, 사용자 보관함에 저장하며 원본 소스와 분리합니다.
