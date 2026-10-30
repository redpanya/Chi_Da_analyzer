# Windows 화자 도구 별도 배포

`.github/workflows/speaker-tools.yml`을 수동 실행하면 sherpa와 pyannote를
각각 독립된 Windows Python 3.11 환경에서 빌드한다. 앱 본체 빌드와 섞지 않는다.

- sherpa: 본체와 같은 NumPy 1.26.4, sherpa-onnx 1.13.8 CPU 실행기.
- pyannote: pyannote.audio 4.0.7, NumPy 2.4.6, 공식 PyTorch 2.8.0 CPU wheel.
  Windows GPU 추론은 이 화자 실행기의 지원 범위가 아니다.
- FluidAudio는 Apple Silicon 전용이므로 Windows 빌드에 포함하지 않는다.

`build.py`가 도구 ZIP, 실제 빌드 환경 고지, 별도 고지 ZIP, LGPL/MPL 대응 소스,
자체 작업기·빌드 코드 ZIP, 해시 목록을 만든다. 모델과 Hugging Face 인증 정보는
담지 않는다. CPU wheel을 사용하므로 CUDA 런타임도 요구하지 않는다.

`smoke.py`는 생성 ZIP을 실제 앱 설치기로 격리 경로에 설치하고 기존 설치·모델·결과
보존, 검사 후 활성 버전 변경, 워커 재실행, 손상 해시 거부를 확인한다. 8kHz 합성 WAV를
실제 워커에 전달해 SoundFile 읽기와 입력 규격 거부까지 검사한다. 이 검사는 실제
Community-1 모델 추론이나 Hugging Face 로그인·다운로드 확인을 대신하지 않는다.

워크플로는 공개 게시를 하지 않는다. 결과를 확인한 뒤 기존 `speaker-tools-v1`에
`chida-sherpa-Windows-x64.zip`, `chida-pyannote-Windows-x64.zip`과 각 고지·소스·검사자료를
새 자산으로 추가한다. 기존 macOS 자산을 교체하거나 `--clobber`로 덮어쓰지 않는다.
같은 이름의 Windows 자산이 이미 있으면 멈추고 해시를 대조한다. 추후 수정판은
새 도구 릴리즈와 앱의 고정 태그를 함께 갱신한다.
