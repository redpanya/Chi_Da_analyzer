# Windows CPU·GPU 선택 구현

작성일: 2026-10-15. 기존 macOS Metal 추론과 원본·저장 결과는 유지한다.

## 적용 범위

Windows의 가져오기 화면에 `Windows AI 처리 장치`를 추가했다. 기본값은 CPU이며 `CPU + GPU 가속 (Vulkan)`을 선택·적용할 수 있다. 설명은 💡 도움말에, 적용 결과·GPU 감지 상태·오류는 화면에 표시한다. 전사와 Gemma 요약, 같은 요약 엔진을 쓰는 선택적 화자 보정 후보의 문맥 판단에 적용한다. 화자 음향 구분, 다운로드, FFmpeg 음성 추출, 브라우저 재생 설정은 변경하지 않는다.

CPU는 입력 준비·일부 연산을, GPU는 지원되는 신경망 연산을 처리한다. 모든 코어의 사용률을 100%로 강제하는 옵션이 아니며 GPU 종류·VRAM·모델·입력에 따라 사용 비율과 속도가 달라진다. 요약은 `-ngl auto`로 메모리 여유에 맞게 배분하며 전사는 whisper.cpp의 Vulkan 경로를 쓴다. 현재 모델과 프롬프트·사고 설정은 바꾸지 않는다.

## 구현과 영향

- `archive/compute.py`에서 Windows 설정·감지·CPU 대체·실행 인자를 공통 관리한다. `%LOCALAPPDATA%/ChiDaAnalyzer/settings.json`의 `windows_compute` 키만 추가하며 다른 경로 설정은 보존한다. macOS에서는 UI를 숨기고 기존 인자를 유지한다.
- Windows 패키지는 독립 CPU 실행기와 `llama-vulkan`, `whisper-vulkan` 실행기를 함께 포함한다. CPU 실행기가 GPU 드라이버에 의존하지 않도록 분리한다. ZIP 용량과 빌드 시간은 GPU 실행기만큼 늘어난다. SDK·드라이버·모델은 앱에 추가하지 않는다.
- 작업 중 설정 변경은 GUI와 서버 양쪽에서 차단한다. 각 작업은 시작 때 정한 실행기를 유지한다. GPU 검사 결과는 프로세스 안에서 캐시하며 `GPU 다시 확인`으로 갱신한다.
- 새 실행 상태와 엔진 실행 폴더/전사 조각에 선택 장치를 기록한다. 기존 결과 파일을 일괄 수정하지 않는다. 장치 변경만으로 프롬프트·입력 지문을 바꾸지 않아 완료 조각/요약은 재사용할 수 있다. CPU·GPU의 수치 차이로 이어서 생성한 내용은 조금 달라질 수 있다.
- 감지는 GPU 초기화 가능성을 확인할 뿐 모델 추론 성공이나 실제 GPU 점유율을 보증하지 않는다. 화면은 ‘가속 요청’으로 표시하며 실제 오프로딩과 실행 오류는 엔진 로그에서 확인한다.

## 예외 처리

- 기존 CPU 전용 배포본/누락 실행기: CPU 사용 안내. 새 GPU 포함 배포본이 필요하다.
- Vulkan 드라이버 없음, 장치 목록 없음, 감지 실패·15초 초과: CPU로 실행하며 사유를 표시한다. CPU 모드도 계속 사용 가능하다.
- VRAM 부족·모델 로딩 실패: 완료 결과를 보존하고 CPU 모드로 변경 후 이어하기를 안내한다. 실패한 GPU 연산을 무한 재시도하지 않는다. 요약의 기존 부분 복구 정책은 유지한다.
- 잘못된 모드·macOS 설정 요청: 서버에서 거부한다. 저장 실패는 GUI에 남기며 설정 적용 완료로 표시하지 않는다.
- CPU·GPU 전환 시에도 원본·수동 교정·화자 배정·기존 요약을 삭제하지 않는다. 기존 모델 버전과 입력이 동일한 부분만 기존 복구 규칙으로 재사용한다.

## 검증 기록

- macOS에서 모의 Windows 분기 검사 6개 통과: 설정 저장·타 설정 보존, CPU/GPU/감지 실패 경로, 정상 종료 코드만으로 GPU 존재를 단정하지 않기, 감지 시간 초과, 작업 중 변경 차단, macOS 기존 인자 유지.
- GUI 모듈 검사 통과: Windows 전용 표시, 선택 중 폴링에 의한 입력 초기화 방지, 저장 실패 안내, 작업 중 변경 차단. 기존 모델 폴더 UI 검사도 통과.
- 관련 전사·요약·패키지 회귀 검사와 GitHub OS별 빌드 결과는 아래에 이어 기록한다.
- 실제 Windows GPU가 없는 현재 Mac에서 GPU 추론의 성능·VRAM·드라이버 호환성 통과를 주장하지 않는다. GTX 1060 등 실제 장치에서 CPU와 GPU 각각 같은 짧은 음성·요약을 실행하고 로그의 GPU 오프로딩, 취소·재개, VRAM 부족 시 복구를 확인해야 한다.

## 빌드 근거

고정된 llama.cpp·whisper.cpp 소스의 Vulkan 지원과 인자를 확인했다. Windows 빌드에서만 `GGML_VULKAN=ON` 실행기를 추가한다. 공식 LunarG SDK 1.4.328.1 설치 파일을 SHA-256 `a8675df6d538079c2a719a9373994948091db785b48f142e024254e76348d16c`로 확인하고 CI 임시 경로에 복사 설치한다.

- [llama.cpp 공식 빌드 안내](https://github.com/ggml-org/llama.cpp/blob/d81235049384534c167caea52b85a694f6103d14/docs/build.md#vulkan)
- [whisper.cpp 공식 소스](https://github.com/ggml-org/whisper.cpp/tree/d1be6fde11ac6e0407606b4e42fe72d34add8037)
- [LunarG Windows SDK 설치·드라이버 안내](https://vulkan.lunarg.com/doc/view/1.4.328.1/windows/getting_started.html)
- [공식 SDK 해시 조회](https://sdk.lunarg.com/sdk/sha/1.4.328.1/windows/vulkan_sdk.exe.json)
