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

- macOS에서 모의 Windows 분기·실행 연결 검사 7개 통과: 설정 저장·타 설정 보존, CPU/GPU/감지 실패 경로, 정상 종료 코드만으로 GPU 존재를 단정하지 않기, 감지 시간 초과, 작업 중 변경 차단, macOS 기존 인자 유지.
- GUI 모듈 검사 통과: Windows 전용 표시, 선택 중 폴링에 의한 입력 초기화 방지, 저장 실패 안내, 작업 중 변경 차단. 기존 모델 폴더 UI 검사도 통과.
- 관련 Python 회귀 모음 33개 실행: 32개 통과, Windows 전용 1개는 macOS에서 건너뜀. 전사 저장·복구, 품질 입력, 요약 서버, GUI 자산 제공, 포터블 잠금 계약을 검사했다.
- `test_speech_ui.mjs`는 `작은 발화` 설명문을 기대하는 기존 검사 1건이 실패했다. 변경 전 커밋 `545df71`을 별도 임시 폴더로 추출해 동일 실패를 재현했다. 설명문을 도움말로 옮긴 현재 UI와 테스트의 불일치이며 이번 GPU 설정 코드로 인한 회귀로 분류하지 않았다. 테스트를 삭제하거나 통과 처리하지 않았다.
- 첫 CI Windows 실행은 공식 SDK 자동 다운로드의 HTTP 403에서 실패했다. LunarG 공식 자동 다운로드 안내에 있는 공유 IP용 `?Human=true` 주소로 변경했다. 변경 후 두 OS 빌드가 성공했고, 마지막 오류 처리 보완본도 두 OS 빌드·패키지 기본 실행 검사를 통과했다.
- 실제 Windows GPU가 없는 현재 Mac에서 GPU 추론의 성능·VRAM·드라이버 호환성 통과를 주장하지 않는다. GTX 1060 등 실제 장치에서 CPU와 GPU 각각 같은 짧은 음성·요약을 실행하고 로그의 GPU 오프로딩, 취소·재개, VRAM 부족 시 복구를 확인해야 한다.

## 빌드 근거

고정된 llama.cpp·whisper.cpp 소스의 Vulkan 지원과 인자를 확인했다. Windows 빌드에서만 `GGML_VULKAN=ON` 실행기를 추가한다. 공식 LunarG SDK 1.4.328.1 설치 파일을 SHA-256 `a8675df6d538079c2a719a9373994948091db785b48f142e024254e76348d16c`로 확인하고 CI 임시 경로에 복사 설치한다.

- [llama.cpp 공식 빌드 안내](https://github.com/ggml-org/llama.cpp/blob/d81235049384534c167caea52b85a694f6103d14/docs/build.md#vulkan)
- [whisper.cpp 공식 소스](https://github.com/ggml-org/whisper.cpp/tree/d1be6fde11ac6e0407606b4e42fe72d34add8037)
- [LunarG Windows SDK 설치·드라이버 안내](https://vulkan.lunarg.com/doc/view/1.4.328.1/windows/getting_started.html)
- [공식 SDK 해시 조회](https://sdk.lunarg.com/sdk/sha/1.4.328.1/windows/vulkan_sdk.exe.json)

## 실제 Windows 장치 확인 방법

1. 새 ZIP 전체를 풀고 가져오기에서 CPU만 사용을 적용한다. 짧은 테스트 영상의 전사·요약을 실행해 기본 동작과 시간을 기록한다.
2. 작업이 끝난 뒤 CPU + GPU 가속을 적용한다. 감지된 장치명과 CPU 대체 안내 유무를 확인한다. 처리 내용이 같은 별도 테스트 자료로 비교해 기존 완료 결과 재사용 시간을 추론 속도로 잘못 비교하지 않는다.
3. 전사 조각의 `speech/runs/<실행 ID>/<조각>-engine.log`에서 `using Vulkan… backend`, 요약의 `context/engines/<실행 ID>/engine.log`에서 `offloaded N/M layers to GPU`를 확인한다. `compute.json`의 요청값이나 GPU 감지 성공만으로 실제 가속을 판정하지 않는다. 요약의 N이 0이면 GPU 모델 연산을 수행한 것으로 기록하지 않는다.
4. CPU와 GPU가 늘 같은 사용률을 보여야 한다는 기준은 사용하지 않는다. 같은 입력·모델의 완료 시간, 오류·VRAM 사용량, 전사 시각·요약 의미를 비교한다. 비트 단위 결과 일치는 요구하지 않는다.
5. 테스트 작업 중 중단·앱 재실행 후 이어하기와 CPU 전환을 확인한다. 완료 자료와 수동 교정이 남아 있어야 한다. 기존 버전·입력 지문이 바뀐 경우에는 기존 복구 정책에 따라 새 작업이 필요하다.

## 최종 CI 확인

- 빌드 커밋: `73cd09129cf80e60bc72606af95bcbd17d826257`.
- [최종 Actions 실행](https://github.com/redpanya/Chi_Da_analyzer/actions/runs/38726283425): macOS-arm64와 Windows-x64 모두 성공.
- Windows Server 2022 CI에서 포터블 잠금·프로세스 정리 5개, 처리 장치 검사 7개 통과. Windows 물리 PC에서 GPU 추론을 실행한 결과로 해석하지 않는다.
- 두 OS 패키지에서 포함 도구 버전 실행, H.264/AAC 생성·읽기·디코딩, 한글·공백 경로, HTTP·정적 모듈, 정상 종료 검사 통과. Windows에는 CPU 실행기와 GPU 실행기 3개가 함께 들어 있으며 처리 장치 설정 API를 CPU + GPU → CPU로 변경·저장하는 검사도 통과했다.
- macOS는 GPU 선택 UI를 숨기고 기존 Metal 경로를 유지한다. 기존 원본·모델·분석 결과는 수정하지 않았다.
- 공식 서명·공증 상태는 기존과 같다. macOS 임시 서명, Windows Authenticode 미서명. 실제 GPU 모델 추론 성능·정확도·메모리 측정은 남아 있다.

## 배포본

`v0.18.0-preview.2`를 비공개 초안으로 준비했다. 기존 `preview.1`은 CPU 전용 기준판으로 보존한다. 저장소와 Release를 공개로 바꾸지 않았다. [저장소 Releases](https://github.com/redpanya/Chi_Da_analyzer/releases)에서 초안과 파일을 구분한다.

- Windows: `Chi_Da_analyzer-Windows-x64.zip`, 126,704,148바이트(약 127 MB). SHA-256 `a688b47d67a2e22b43b555ca4d1c1da9bb6e7691bf64d5e1f388abb9c1cc80a4`.
- macOS: `Chi_Da_analyzer-macOS-arm64.zip`, 102,065,841바이트(약 102 MB). SHA-256 `22929561a03ed1fe0a559be9f2deb3f95f32d08b6f5b29f103963ef341f92b23`.
- Windows ZIP은 기존 CPU 전용 ZIP보다 약 48.6 MB 증가했다. 별도의 Vulkan 실행기 3개가 추가된 영향이다. 모델·SDK·드라이버는 포함하지 않는다.
- ZIP 내부를 확인해 GPU 실행기 3개의 존재와 `.gguf`, `.onnx`, `.safetensors`, 영상·오디오 파일이 들어가지 않았음을 확인했다. 아티팩트의 원래 체크섬도 검증했다.
- Windows 패키지 진단 JSON의 실제 값은 `visible: true`, `bundled: true`, `available: false`, `mode: cpu`였으며 Vulkan 드라이버 미설치 안내를 반환했다. GPU가 없는 CI에서 기본 앱·CPU 경로가 동작하는 확인이며 실제 GPU 추론 검증이 아니다. macOS는 `visible: false`였다.
