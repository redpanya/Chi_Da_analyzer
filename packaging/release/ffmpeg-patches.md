# 배포 FFmpeg 수정 고지

수정 주체: ChiDa Analyzer 프로젝트. 수정일: 2026-10-30.

FFmpeg 8.1.3의 고정 소스 커밋 `1041abdc962f4cc4f394aa8de9dc5236c0c3b9e7`에
아래 변경을 적용해 macOS와 Windows 바이너리를 빌드한다. 원본 소스의 해시는
`sources.json`에, 적용 순서는 `build_ffmpeg.sh`에 기록한다.

- `ffmpeg-tls-verify.patch`: TLS 인증서 검증 기본값을 켜 HLS 하위 재생목록·세그먼트·키 연결에도 적용한다.
- `ffmpeg-hls-m4v.patch`: 초기 형식 판별 결과가 MP4인 HLS 입력에서 `.m4v` 별칭을 인정한다. 다른 형식·확장자 검사와 TLS 설정은 변경하지 않는다.

이 패키지의 FFmpeg는 수정한 버전이며, 상류 원본과 구별한다. 원래 저작권·라이선스를
유지한다. 전체 고정 소스·두 패치·빌드 레시피는 `native-corresponding-sources.zip`에
함께 제공한다.

재빌드할 때 ZIP의 `release/` 파일은 프로젝트의 `packaging/release/`에,
`release-sources/` 파일은 `build/release-sources/`에 배치한 뒤 `build_ffmpeg.sh`를 실행한다.
