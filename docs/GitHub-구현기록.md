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

- macOS 관련 회귀 검사 68개 통과. 임시 보관함의 시작·종료, 잠금·한글 JSON·자식 잠금 유지 검사 3개 추가 통과 (Windows 전용 1개 제외).
- 최초 GitHub Windows runner에서 시작·종료, 잠금·한글 JSON, 부모 핸들 종료 뒤 자식 잠금 유지, 부모 강제 종료 시 손자 종료 검사 4개 통과.
- 최초 macOS CI는 새 Python 환경의 준비 대기 10초를 넘어 실패. 다음 빌드의 시작 검사 대기를 60초로 조정.
- 로컬 최소 Python 패키지와 llama/whisper 네이티브 정적 빌드 생성. macOS 기본 Bash의 빈 배열 처리와 한글 경로의 pkg-config 이스케이프 문제를 빌드 단계에서 수정.
- Windows의 일시적인 JSON 읽기와 교체 충돌에 한해 최대 0.9초 재시도 추가. 권한 오류가 지속되면 원래 오류를 유지.
- 로컬 macOS 앱 패키지의 포함 엔진 실행, H.264/AAC 생성·probe·디코딩, 한글 경로, 페이지/정적 모듈, 정상 종료 검사 통과. 앱 약 266MiB, ZIP 약 96MiB. ZIP 안에 모델·영상·음성 파일 없음 확인.
- 최신 CI 두 OS 이식 검사 통과. 최초 Windows FFmpeg 타깃의 `.exe` 누락을 수정했고, 수정 버전의 네이티브 빌드와 초안 Release 생성은 진행 중이다.

## 남은 항목

깨끗한 실제 장치의 VOD 다운로드·음성 전사·Gemma 요약·중단 복구·외장 볼륨 휴지통 실사용, Windows GPU 가속, macOS 최소 버전 장치 실행, 공개 라이선스 결정, 서명·공증. 저장소 공개 전환은 이번 작업에서 자동 수행하지 않는다.
