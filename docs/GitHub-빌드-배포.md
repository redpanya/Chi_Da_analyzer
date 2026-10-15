# macOS·Windows 빌드와 배포

## 범위

`ChiDaanalyzer.app`을 담은 macOS Apple Silicon 앱 ZIP, Windows x64 CPU + Vulkan 선택형 포터블 ZIP을 각 OS의 GitHub Actions에서 빌드합니다. DMG는 만들지 않습니다. 기본 화자 엔진 sherpa와 미디어·전사·요약 실행 도구를 포함하며 모델은 설치 후 다운로드합니다. 기존 전체 macOS 개발 패키징 스크립트와 로컬 결과는 유지합니다.

저장소는 `redpanya/Chi_Da_analyzer` 비공개입니다. Actions의 `앱 빌드`를 수동 실행하면 두 OS 빌드와 간단한 실행 검사를 거쳐 아티팩트를 생성합니다. `draft_tag`를 입력하면 두 빌드가 모두 성공했을 때만 비공개 저장소에 초안 Release와 체크섬·대응 소스를 함께 올립니다. 빈 값이면 아티팩트만 생성합니다. 초안 공개와 저장소 공개 전환은 자동으로 하지 않습니다.

## 로컬 재현

Python 3.11, CMake, C/C++ 컴파일러가 필요합니다. macOS는 Xcode Command Line Tools와 pkg-config, Windows는 Visual Studio 2022 C++ 도구 및 MSYS2 UCRT64의 gcc·make·pkgconf가 필요합니다. 실행은 저장소 루트 기준입니다. 로컬에서 PyInstaller 캐시를 분리하려면 `PYINSTALLER_CONFIG_DIR`를 저장소의 `build/pyinstaller-cache`로 지정합니다.

```text
python -m pip install -r packaging/release/requirements.txt
python packaging/release/fetch_sources.py
python packaging/release/build_native.py
bash packaging/release/build_ffmpeg.sh
python -m PyInstaller --noconfirm --clean --distpath build/frozen --workpath build/pyinstaller packaging/release/backend.spec
python packaging/release/assemble.py --version 0.18.0
python packaging/release/smoke.py
python packaging/release/archive_release.py
```

Windows에서는 `setup_vulkan.py`를 먼저 실행하고 출력된 `VULKAN_SDK` 경로를 환경 변수에 지정한 뒤 `python packaging/release/build_native.py --vulkan`을 추가 실행합니다. CPU와 Vulkan 실행기를 별도 디렉터리에 함께 포함해야 합니다. SDK 설치 파일은 공식 1.4.328.1과 SHA-256으로 고정하고 앱에는 포함하지 않습니다.

Windows의 FFmpeg 빌드 명령만 MSYS2 UCRT64 셸에서 실행합니다. 나머지는 Python/Visual Studio가 있는 PowerShell에서 실행합니다. 빌드 폴더 `build`, 배포 폴더 `dist`는 Git에 올리지 않습니다.

## 재현성과 공급 구성

- 네이티브 소스는 `sources.json`의 커밋 및 SHA-256으로 고정합니다. whisper/llama는 각각 정적 빌드해 ggml 버전 충돌을 피합니다.
- FFmpeg+x264는 직접 빌드하며 사용한 전체 소스 압축 파일·명령·설정·라이선스 사본을 배포합니다. 기본 빌드의 FFmpeg는 GPLv2 이상 구성입니다.
- Python 의존성은 직접 버전을 고정하고 최종 환경 목록·라이선스 사본을 패키지에 보존합니다. 전이 의존성까지 완전히 잠근 비트 단위 재현 빌드는 아닙니다.
- 모델·HF 토큰·설정·쿠키·VOD·전사·요약·개인 로그는 소스와 배포물에서 제외합니다.
- macOS 임시 서명만 수행합니다. Windows 서명, Apple 공증, 자동 업데이트는 포함하지 않습니다.

## 예외와 사이드이펙트

- Windows 파일 잠금은 Win32 핸들로 유지하며 작업 자식에게 상속합니다. 앱 강제 종료 시 Job Object가 자식을 정리합니다. 해당 보호 기능을 만들지 못하면 실행을 중단합니다.
- 취소는 해당 작업 프로세스 트리만 종료합니다. 종료 중 완료되지 않은 파일은 기존 복구 정책을 따릅니다.
- Windows 휴지통이 불가능한 볼륨에서 삭제가 실패하면 영구 삭제로 전환하지 않습니다.
- Windows는 CPU를 기본으로 하며 Vulkan 가속을 선택할 수 있습니다. GPU 실행기를 별도 폴더에 두어 드라이버가 없어도 CPU 앱이 실행됩니다. 실제 GPU 추론 속도와 모델 메모리 요구는 장치별 수동 검증 대상입니다. CUDA SDK나 GPU 드라이버를 앱이 자동 설치하지 않습니다.
- AppData와 macOS 기존 경로를 분리해 기존 설정을 덮어쓰지 않습니다. UTF-8 요청·결과 파일을 명시적으로 읽습니다.
- Windows의 pyannote 실행 경로는 준비하지만 기본 배포에는 포함하지 않습니다. 준비되지 않은 추가 엔진은 GUI에서 설치 필요 상태로 남습니다.
- 모델을 받지 않은 CI는 모델 로드·추론 정확도·처리 시간의 통과를 주장하지 않습니다. 네트워크 장애, 디스크 부족, 라이선스 동의 미완료는 기존 GUI 오류로 안내합니다.

## 공개 전 검증 기준

자동: 두 OS Python 검사, 잠금 중복 거부와 자식 잠금 유지, 앱 강제 종료 시 Windows 자식 종료, 한글·공백 경로, 패키지 독립 실행, 포함 도구 버전, H.264/AAC 영상 생성·probe·디코딩, 서버 페이지·정적 모듈, 준비 파일 생성·종료, 체크섬. macOS 최종 ZIP은 ditto·unzip 두 방식으로 해제한 뒤 서명과 ASCII 번들 경로를 확인하고 LaunchServices로 실제 앱을 시작해 HTTP 응답을 확인합니다. Gatekeeper 허용 결과는 별도로 기록하며 임시 서명 초안의 거부를 공증 통과로 표시하지 않습니다.

수동: 깨끗한 실제 Mac과 Windows PC에서 다운로드 또는 로컬 가져오기→전사→선택 화자 구분→Gemma 요약→반응 이동→댓글 편집/복사. 중단·재실행, 외장 보관함, 모델 최초 다운로드·오프라인 재사용, 휴지통 복원. 기존 원본·수동 교정·화자 배정·분석 보존. CPU 속도와 메모리 측정.

검증 JSON의 Release 파일명은 GitHub 업로드 정규화를 피하기 위해 `macOS-arm64-smoke.json`, `Windows-x64-smoke.json`을 사용합니다. 초안 Release URL은 공개 전환 시 바뀔 수 있으므로 외부 안내는 저장소의 Releases 페이지를 사용하세요.
