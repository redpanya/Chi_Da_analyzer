# 패키징 안내

현재 macOS·Windows 공식 빌드는 [release/README.md](release/README.md)와 `.github/workflows/build.yml`을 사용한다. 기본 앱에는 말소리 분리 실행기와 모델 가중치를 넣지 않는다.

- `release/backend.spec`: 공개 배포용 Python 실행기.
- `build_macos.py`, `backend.spec`: 로컬 macOS 앱 조립 경로.
- `speaker_tools/`, `pyannote.spec`, `diarization_bundle.py`: 선택 화자 도구 빌드·조립.
- `collect_notices.py`, `collect_worker_notices.py`: 외부 도구 라이선스 고지 수집.

SAM/BS-Roformer의 새 분리 기능은 제거됐다. 관련 실행기·설치 목록·spec은 2026-10-27 정리했으며 기존 모델·분리본·전사 열람은 유지한다. 과거 빌드 절차는 이전 Git 버전에서 확인할 수 있다. 공개된 대응 소스·라이선스 자료는 유지한다.
