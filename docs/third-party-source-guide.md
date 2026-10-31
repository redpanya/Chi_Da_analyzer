# 외부 라이브러리 소스와 교체

자체 코드는 MIT, 외부 구성요소는 각 라이선스를 유지한다. 프로그램 이용 조건으로 LGPL 라이브러리 수정·교체 및 그 수정 사항을 디버깅하기 위한 역공학을 제한하지 않는다.

## 대응 소스

릴리스의 `native-corresponding-sources.zip`에는 FFmpeg·x264·llama.cpp·whisper.cpp의 고정 소스와 빌드 스크립트가 있다. `legal-corresponding-sources.zip`에는 libsndfile 1.2.2, 정적 코덱 소스, 원 배포처 빌드 자료, 추가 파일 단위 소스 및 해시 목록이 있다. 모델 가중치나 사용자의 VOD는 포함하지 않는다.

`packaging/release/legal_sources.json`의 URL·해시를 기준으로 `python packaging/release/legal.py sources`를 실행해 대응 소스를 다시 확보할 수 있다. 해시가 다르거나 다운로드에 실패하면 불완전한 소스 묶음을 생성하지 않는다.

libsndfile은 SoundFile 0.13.1의 고정 하위 저장소 `bastibe/libsndfile-binaries@a3e6f9769d0c7e91d2d036cf0fdbe5b4bbf18b87`에서 제공한 라이브러리다. Mac 빌드 스크립트와 Windows triplet·작업 흐름을 소스 묶음에 보존한다. Windows 원 작업 흐름은 vcpkg 리비전을 고정하지 않았으므로 역사적 바이너리의 바이트 단위 재현을 보장하지 않는다. 확인된 코덱 버전·보완 범위는 구현 검증 문서에 기록한다.

## 이전 배포본의 소스 찾기

v1 정식 전환으로 이전 앱 릴리즈를 정리했다. 이전 버전의 대응 소스·고지·해시 자료는 [과거 배포본의 라이선스·대응 소스](https://github.com/redpanya/Chi_Da_analyzer/releases/tag/license-supplement-20261020)에 보존한다. `source-manifest.json`에서 버전과 소스 커밋으로 원래 파일명·보관 파일명·SHA-256을 확인한다. 같은 해시의 파일은 여러 버전에서 공유한다. 원래 해시 목록을 검사할 때는 대응표의 원래 이름으로 파일을 복사해 사용한다.

## libsndfile 교체

앱을 종료하고 **별도로 복사한 앱 폴더**에서 작업한다. VOD·AI 모델·전사·수동 화자 배정·요약 파일을 수정할 필요가 없다.

1. 소스 ZIP의 해당 libsndfile·코덱·빌드 자료를 사용해 같은 OS·CPU 아키텍처의 공유 라이브러리를 빌드한다. 기존 SoundFile과 호환되는 libsndfile API·파일 형식 지원을 유지한다.
2. 기존 라이브러리를 백업한 뒤 다음 파일을 교체한다.
   - macOS 기본 앱: `ChiDaanalyzer.app/Contents/Resources/backend/_internal/_soundfile_data/libsndfile_arm64.dylib`
   - Windows 기본 앱: `ChiDaanalyzer/_internal/_soundfile_data/libsndfile_x64.dll`
   - 별도 sherpa·pyannote 도구: 해당 도구의 `_internal/_soundfile_data/` 아래 파일
3. macOS 앱은 파일 교체로 기존 서명이 달라진다. 로컬 복사본에 `codesign --force --deep --sign - "ChiDaanalyzer.app"`으로 임시 서명을 다시 적용할 수 있다. 이것은 Apple 공증이나 인터넷 배포 허용을 뜻하지 않는다.
4. 원본 대신 짧은 사본 WAV로 로드·읽기·재생을 확인한다. 호환되지 않으면 백업한 라이브러리 또는 기존 앱으로 되돌린다.

앱 설치기의 다운로드 해시 검사는 배포 도구 ZIP이 변조되지 않았는지 확인하기 위한 것이다. 개인적으로 수정한 도구를 원 배포본이라고 같은 URL에 올리지 않는다. 소스에서 실행 도구를 다시 빌드할 수 있으며, 수정본의 고지·변경 사실·대응 소스를 함께 유지한다.

## 재배포 시

바이너리와 그 버전에 대응하는 고지·소스를 함께 제공한다. 릴리스에서 고지 ZIP만 받는 방식은 원본 ZIP 안의 고지를 제거해도 된다는 뜻이 아니다. 기존 배포본을 재배포할 때에는 라이선스 보충 자료를 같은 다운로드 위치에 두고 받는 사람이 함께 확인할 수 있게 한다.

libsndfile을 다른 버전·코덱 구성으로 바꾸거나 정적 링크 방식으로 바꾸면 대응 소스·객체 파일 또는 재링크 방식 등 해당 조건을 다시 확인한다. 앱의 처리 기능을 바꾸지 않는 고지 추가와 실제 라이브러리 변경은 별도 검증 대상이다.
