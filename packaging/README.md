# 현재 소스 · 말소리 분리 실행기 제외

2026-10-15 변경부터 새 말소리 분리 기능을 제공하지 않는다. `build_macos.py`는 SAM/BS-Roformer 실행기를 요구하거나 앱에 복사하지 않는다. 모델 캐시·과거 분리 결과·기존 앱은 삭제하지 않는다. 이번 변경에서는 패키지를 만들지 않았으며 새 앱 용량·서명·실행 검증은 하지 않았다.

다음 패키징 요청에서는 기본 backend와 화자 선택 실행기를 준비한 뒤 아래처럼 조립한다. 모델 가중치와 인증 정보는 앱에 포함하지 않는다. sherpa-onnx는 발화 검출·화자 분석에도 사용하므로 유지한다.

```sh
chzzk-archive/.voice-venv/bin/python chzzk-archive/packaging/build_macos.py --backend outputs/새빌드/dist/backend --pyannote-backend outputs/새빌드/pyannote-dist/pyannote --fluid-binary chzzk-archive/.diarization-tools/fluid/Runner/.build/release/archive-fluid-diarizer --output outputs/새빌드/앱 --ggml-source-archive outputs/새빌드/ggml-v0.26.0.tar.gz
```

아래는 **이전 배포 버전의 재현 기록**이다. 아래 SAM/BS 빌드 명령과 제거된 조립 옵션은 현재 소스용이 아니다. 현재 기능·검증 범위는 [구현 기록](../../docs/2026-10-15-기능단순화-전사옵션-반응지수-댓글편집-구현검증.md)을 따른다.

# 0.17.0 · 추가 화자 실행기 포함

현재 조립에는 아래 기존 세 번들 외에 pyannote·FluidAudio가 필수다. `tools/install_diarization.py`의 고정 버전으로 소스 도구를 준비한다. pyannote 전용 환경에 `requirements-build.txt`를 설치하고 `pyannote.spec`로 독립 실행기를 만든다. macOS 폰트 탐색 호환 패치는 도구 설치 단계에 포함된다.

```sh
MPLCONFIGDIR="$PWD/outputs/새빌드/matplotlib-cache" PYANNOTE_METRICS_ENABLED=0 HF_HUB_DISABLE_TELEMETRY=1 PYINSTALLER_CONFIG_DIR="$PWD/outputs/새빌드/pyannote-cache" chzzk-archive/.diarization-tools/pyannote/venv/bin/python -m PyInstaller --distpath outputs/새빌드/pyannote-dist --workpath outputs/새빌드/pyannote-work chzzk-archive/packaging/pyannote.spec
chzzk-archive/.diarization-tools/pyannote/venv/bin/python chzzk-archive/packaging/collect_worker_notices.py pyannote
```

조립 명령에는 `--pyannote-backend outputs/새빌드/pyannote-dist/pyannote`, `--fluid-binary chzzk-archive/.diarization-tools/fluid/Runner/.build/release/archive-fluid-diarizer`을 추가한다. `diarization_bundle.py`가 앱의 `Resources/diarization`에 배치한다. Fluid의 `LICENSE`와 `ThirdPartyLicenses`는 `notices/native/FluidAudio`에 보존한다. Nemotron 실행기는 현재 조립 대상에서 제외한다. 이미 만든 앱은 변경하지 않는다.

모델·HF 토큰·개발 가상환경·Swift 빌드 캐시를 통째로 복사하지 않는다. pyannote 모델 준비 카탈로그는 전용 실행기에도 포함한다. frozen 실행 경로·multiprocessing 진입점을 지원하며 matplotlib 캐시는 사용자 쓰기 가능 경로에 만든다.

0.17.0에서는 SHA-256이 동일한 SAM/BS 소스에 대해 기존 최종 실행기 번들을 재사용했다. 새 소스로 다시 빌드하려면 아래 절차를 사용한다. 이번 요청은 사용자 직접 기능 검증이므로 앱 실행·추론·회귀 테스트는 하지 않았다. [패키징 결과](../../docs/2026-10-14-치지직-VOD-017-앱패키지.md)를 참조한다.

# 0.16.0 · SAM/BS 실행기를 포함한 앱 조립

최신 패키지는 `backend.spec`, `sam.spec`, `roformer.spec`를 각각 `.voice-venv`, `.sam-venv`, `.roformer-venv`에서 빌드한다. 각 환경에 `requirements-build.txt`의 고정 빌드 도구를 준비한다. BS 환경은 `requirements-roformer.txt`, SAM 환경은 `requirements-sam.txt`를 사용한다. 기존 모델과 사용자 보관함은 빌드 입력에 포함하지 않는다.

BS 실행기 빌드 예시:

```sh
PYINSTALLER_CONFIG_DIR="$PWD/outputs/새빌드/roformer-cache" chzzk-archive/.roformer-venv/bin/python -m PyInstaller --distpath outputs/새빌드/roformer-dist --workpath outputs/새빌드/roformer-work chzzk-archive/packaging/roformer.spec
```

기본 `collect_notices.py` 실행 후 각각의 가상환경에서 `collect_worker_notices.py sam` / `collect_worker_notices.py roformer`도 실행한다. 조립에는 세 실행기가 모두 필요하다.

```sh
chzzk-archive/.voice-venv/bin/python chzzk-archive/packaging/build_macos.py --backend outputs/새빌드/dist/backend --sam-backend outputs/새빌드/sam-dist/sam --roformer-backend outputs/새빌드/roformer-dist/roformer --output outputs/새빌드/앱 --ggml-source-archive outputs/새빌드/ggml-v0.26.0.tar.gz
```

이전 출력 앱을 덮어쓰지 않는다. BS의 PyTorch와 SAM의 MLX를 별도 실행기로 유지한다. 실제 패키징·실행 검증은 [0.16.0 기록](../../docs/2026-10-14-치지직-VOD-016-앱패키지.md)을 참조한다. 아래는 이전 빌드 절차와 의존성 설명이다.

# 추가된 SAM 빌드 단계

기존 `.voice-venv`와 별개인 Python 3.11 `.sam-venv`를 사용한다. `requirements-sam.txt`를 설치하고 `sam.spec`로 실행기를 만든다. 모델 파일은 앱에 포함하지 않는다. PyInstaller 캐시는 작업 출력 폴더로 지정한다.

```sh
uv venv chzzk-archive/.sam-venv --python 3.11
uv pip install --python chzzk-archive/.sam-venv/bin/python -r chzzk-archive/packaging/requirements-sam.txt
PYINSTALLER_CONFIG_DIR="$PWD/outputs/새빌드/sam-cache" chzzk-archive/.sam-venv/bin/python -m PyInstaller --distpath outputs/새빌드/sam-dist --workpath outputs/새빌드/sam-work chzzk-archive/packaging/sam.spec
```

아래 조립 명령에는 `--sam-backend outputs/새빌드/sam-dist/sam`을 필수로 추가한다. SAM의 런타임 내부 모듈과 `mlx.metallib`를 포함하고, 개발 Python/Homebrew가 없는 시스템 PATH에서 실제 분리 추론을 검증한다. 이전 Demucs/Torch 실행 코드는 제거했으며 과거 분리 결과 파일 열기는 유지한다. SAM 관련 라이선스는 `notices/sam-python`에 함께 보존한다.

아래는 기존 빌드 환경 기록이다. 용량·최종 실제 검사 결과는 0.15.0 구현 보고서를 기준으로 확인한다.

# macOS 0.15.0 빌드

현재 빌드 대상은 Apple Silicon과 macOS 27이다. 설치된 FFmpeg/ffprobe 9.0.2, whisper.cpp 1.9.5, llama.cpp 0.6.0(build 11429), ggml 0.26.0와 libomp, CMake와 Xcode Swift 컴파일러를 사용한다. 실행 시에는 Homebrew나 개발 가상환경을 사용하지 않는다. 모델은 포함하지 않는다. 형식 7의 기존 Qwen 토큰 계산용 `llama-tokenize`와 Gemma 사고 모드용 `llama-server`를 함께 포함한다. Gemma는 모델 고유 템플릿·토크나이저와 작업당 한 번의 로딩을 사용한다.

프로젝트 상위 폴더에서 기존 음성 환경에 고정된 빌드 도구와 yt-dlp를 준비한다. 가상환경이 없다면 먼저 프로젝트의 M4 음성 도구 설치 절차를 진행한다.

```sh
uv pip install --python chzzk-archive/.voice-venv/bin/python -r chzzk-archive/packaging/requirements-build.txt -r chzzk-archive/requirements.txt
chzzk-archive/.voice-venv/bin/python chzzk-archive/packaging/collect_notices.py
chzzk-archive/.voice-venv/bin/python -m PyInstaller --distpath outputs/새빌드/dist --workpath outputs/새빌드/work chzzk-archive/packaging/backend.spec
curl -fL https://codeload.github.com/ggml-org/ggml/tar.gz/refs/tags/v0.26.0 -o outputs/새빌드/ggml-v0.26.0.tar.gz
chzzk-archive/.voice-venv/bin/python chzzk-archive/packaging/build_macos.py --backend outputs/새빌드/dist/backend --sam-backend outputs/새빌드/sam-dist/sam --output outputs/새빌드/앱 --ggml-source-archive outputs/새빌드/ggml-v0.26.0.tar.gz
```

출력 폴더와 앱이 이미 있으면 새 폴더를 선택한다. 앱은 모든 처리 엔진을 포함한 약 436MB(416MiB) 폴더형 패키지다. 단일 실행 파일의 매번 압축 해제는 사용하지 않는다. 앱은 AppKit 실행 창에서 로컬 서버를 관리하고 기존 웹 GUI를 기본 브라우저에 연다.

`archive/runtime.py`는 앱 내부 도구·인증서만 사용하게 하며, M4는 같은 포함 실행 파일의 별도 프로세스로 호출한다. Torch와 ggml의 OpenMP 라이브러리는 분리한다. Swift 실행기와 Python 프레임워크·수정된 dylib·앱 번들을 임시 서명한다. `--diagnose`는 각 엔진 import와 실행 경로·버전을 JSON으로 출력한다.

`ggml_bundle.py`는 위 공식 0.26.0 압축 파일의 SHA-256을 검사하고 CMake로 백엔드 로더를 재빌드한다. Homebrew에 고정된 플러그인 검색 경로를 제외하고 CPU·Metal·BLAS 플러그인을 실행 파일 옆에 넣는다. 플러그인도 앱의 ggml·분리한 OpenMP를 사용하도록 연결한다. 이를 생략하면 Homebrew 플러그인과 앱 라이브러리가 혼용되어 시작 중 충돌하거나 다른 Mac에서 엔진이 빠질 수 있다. 버전·해시가 다르면 빌드를 중단한다.

`codesign --verify --deep --strict`와 개별 Mach-O의 검사, `spctl --assess`, `xcrun stapler validate`는 서로 다른 검사다. 임시 서명 검사를 통과해도 Developer ID·Gatekeeper·공증이 승인된 것이 아니다. 현재 인증서가 없어 Apple 공증을 신청하지 않았다.

PyInstaller가 수집한 선택 의존성 중 tensorboard, CUDA/Linux/Windows 모듈과 사용하지 않는 SoX 확장은 이번 CPU 추론 경로에서 사용하지 않는다. 실제 전사·sherpa-onnx·Demucs 처리를 검증하고 빌드 경고를 별도로 보존한다. 공개 배포 전에 라이선스에 따른 정확한 대응 소스·빌드 재현 자료와 배포 서명·공증을 준비해야 한다.

빌드 스크립트는 `.app`만 생성한다. DMG 생성 옵션과 실행 경로는 제거했다. 삭제 보조 도구 `Trash.swift`도 앱 내부에 컴파일·임시 서명한다. 개발 실행에서 삭제를 확인할 때는 `mkdir -p packaging/bin` 후 `xcrun swiftc -O packaging/Trash.swift -o packaging/bin/vod-trash`로 준비한다.
