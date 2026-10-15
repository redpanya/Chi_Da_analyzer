# GitHub 배포 준비 기록 — 2026-10-15

## 구현

- `redpanya/Chi_Da_analyzer` 비공개 저장소 생성. 기존 전체 작업 폴더 대신 앱 소스·테스트·빌드 스크립트와 배포 문서만 반출한다.
- macOS 설정·모델 기본 경로 유지. Windows AppData·Videos 기본 경로 추가.
- Windows 파일 잠금 핸들의 자식 상속, Job Object에 의한 강제 종료 정리, 작업 취소 시 해당 프로세스 트리 종료.
- 요청 JSON의 UTF-8 명시, Windows 휴지통 분기. 기존 원본·수동 수정·배정·결과를 이동하거나 삭제하지 않음.
- 고정 커밋·SHA-256의 llama.cpp 0.6.0, whisper.cpp 1.9.5, FFmpeg 8.1.3, x264 소스 빌드.
- GitHub Actions macOS arm64·Windows x64 CPU 빌드, Python 독립 패키지, ZIP·체크섬·대응 소스, 선택적인 초안 Release.
- 기본 배포는 sherpa 엔진만 포함. 모델은 앱에서 다운로드. macOS 임시 서명, Developer ID·공증·Windows 서명 없음. DMG 없음.

## 검증 진행 상태

macOS 로컬 잠금·한글 JSON·자식 프로세스 잠금 유지 검사를 통과했다. 샌드박스 안에서는 HTTP 포트 바인딩이 차단되어 앱 시작 검사를 별도 권한으로 재실행한다. Windows 실제 실행과 두 OS CI 빌드는 아직 진행 중이다. 최종 결과를 이 문서에 갱신한다.

## 남은 항목

깨끗한 실제 장치의 VOD 다운로드·음성 전사·Gemma 요약·중단 복구·외장 볼륨 휴지통 실사용, Windows GPU 가속, macOS 최소 버전 장치 실행, 공개 라이선스 결정, 서명·공증. 저장소 공개 전환은 이번 작업에서 자동 수행하지 않는다.
