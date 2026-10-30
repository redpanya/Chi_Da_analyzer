# 외부 도구·모델 고지와 대응 소스

치다 분석기 자체 코드에는 루트 [MIT 라이선스](LICENSE)를 적용합니다. 아래 외부 코드·실행 파일·모델 및 제3자 영상·이미지의 권리는 자체 코드의 MIT 허가로 대체하지 않습니다. 라이선스 원문은 번역으로 의미가 바뀌지 않도록 원문 그대로 보존합니다.

## 동봉 도구

| 구성요소 | 조건 | 제공 위치 |
|---|---|---|
| Pillow 12.3.0 | MIT-CMU 및 wheel 내 제3자 조건. 클립 자막 렌더링에 사용 | 배포본 Python 고지의 Pillow LICENSE 및 bundled third-party 고지. OS 글꼴은 배포하지 않음 |
| fontTools 4.68.0 | MIT. 설치 글꼴의 문자표를 읽어 언어 지원 확인 | 빌드 환경 고지에 원문 수집. [공식 소스](https://github.com/fonttools/fonttools) |
| yt-dlp | Unlicense 및 포함 의존성 조건 | 배포본 Python 고지 |
| llama.cpp·whisper.cpp | MIT 및 내부 구성요소 조건 | `licenses/llama.cpp`, 네이티브 도구의 LICENSE |
| FFmpeg·x264 | GPL-2.0-or-later 구성 | 네이티브 도구 고지, 릴리스의 `native-corresponding-sources.zip` |
| sherpa-onnx | Apache-2.0 | Python 고지 |
| ONNX Runtime 1.28.2 | MIT 및 제3자 조건 | `licenses/onnxruntime` |
| Python·OpenSSL | PSF 및 부속 조건 / Apache-2.0 | `licenses/python-*`, `licenses/openssl-*`, 빌드 시 실제 Python 런타임 고지 |
| SoundFile / libsndfile 1.2.2 | BSD / LGPL-2.1-or-later | Python 고지 및 `licenses/libsndfile-1.2.2` |
| libsndfile 내 Ogg·Vorbis·FLAC·Opus | BSD 계열 등 원 프로젝트 조건 | 해당 이름의 `licenses/` 하위 폴더 |
| libsndfile 내 mpg123·LAME | LGPL 계열 | 해당 이름의 `licenses/` 하위 폴더 및 대응 소스 |
| pyannote.audio / PyTorch 계열 | MIT / BSD 및 부속 조건 | 선택 도구의 Python 고지 |
| FluidAudio / fastcluster / VBx | Apache-2.0 / BSD-2-Clause / Apache-2.0 | `licenses/fluidaudio` |
| NumPy·SciPy·CFFI·SoundFile 등 | 각 BSD·MIT 등 및 부속 조건 | Python 고지. OpenBLAS·GCC 런타임의 고지·예외 포함 |
| certifi·tqdm | MPL-2.0 등 해당 파일의 조건 | Python 고지 및 대응 소스 안내 |
| PyInstaller | GPL 배포 예외 등 | Python 고지. 해당 예외가 다른 구성요소의 의무를 면제하지 않음 |

Windows의 Microsoft VC 런타임은 Microsoft의 재배포 조건을 따릅니다. 이 DLL에 자체 MIT를 적용하지 않습니다. [허용 파일·배포 조건](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)

## 다운로드 모델

가중치는 기본 앱 ZIP에 포함하지 않습니다. 설치 후 원 배포처에서 받습니다. 모델 파일을 따로 재배포할 때에도 출처·라이선스·변환 고지를 함께 전달해야 합니다.

| 모델 | 조건·출처 |
|---|---|
| Gemma 4 E4B IT, Unsloth Q4_K_M 변환 | Apache-2.0. [Google](https://huggingface.co/google/gemma-4-E4B-it), [실제 사용 리비전](https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF/tree/bfc15c382204943c3a8fff0c750b94ae2364d7a3). GGUF 양자화는 Unsloth 제공 |
| Whisper large-v3-turbo, whisper.cpp 변환 | MIT. [OpenAI](https://github.com/openai/whisper), [변환 모델](https://huggingface.co/ggerganov/whisper.cpp). 엔진과 가중치 고지를 구분 |
| Silero VAD | MIT. [원 프로젝트](https://github.com/snakers4/silero-vad), sherpa 배포 ONNX 사용 |
| pyannote segmentation 3.0 | MIT. [원 모델](https://huggingface.co/pyannote/segmentation-3.0), sherpa 배포 ONNX 사용 |
| 3D-Speaker ERes2Net | Apache-2.0. [원 모델](https://www.modelscope.cn/models/iic/speech_eres2net_base_sv_zh-cn_3dspeaker_16k), sherpa 배포 ONNX 사용 |
| pyannote Community-1 | CC-BY-4.0. [원 배포처](https://huggingface.co/pyannote/speaker-diarization-community-1). 공식 다운로드에는 사용자 본인의 HF 이용 동의·인증 필요 |
| Fluid Community-1 Core ML 변환 | 지정 가중치 CC-BY-4.0. pyannote·WeSpeaker·BUT Speech@FIT·Fluid Inference 출처와 Core ML 변환 사실 보존. `licenses/models/Fluid-NOTICE.md`의 정확한 적용 범위 확인 |

모델 원문·출처 자료는 `licenses/models`에 있습니다. CC-BY-4.0은 비상업 전용 조건이 아닙니다. 기존 호환용 모델·다른 파생 모델에 위 조건을 자동 적용하지 않습니다. 모델의 허가가 방송 콘텐츠 권리까지 허가하는 것은 아닙니다.

## 재배포와 소스 받기

- [릴리스 다운로드](https://github.com/redpanya/Chi_Da_analyzer/releases)에서 실행 파일과 같은 버전의 네이티브 소스 ZIP, 라이선스 보충 ZIP, LGPL·MPL 대응 소스 ZIP을 함께 받으세요. `license-supplement-20261020` 릴리스에도 기존 배포본의 보충 자료를 제공합니다.
- FFmpeg·x264에는 `native-corresponding-sources.zip`, 음성 라이브러리·정적 코덱에는 `legal-corresponding-sources.zip`을 사용합니다. 소스·빌드 자료·해시 목록을 포함합니다. 단순 upstream 홈페이지 링크로 대응 소스 제공을 대체하지 않습니다.
- 프로그램을 재배포할 때 MIT 및 제3자 고지를 제거하지 말고, GPL·LGPL 대상에는 정확한 소스를 함께 전달하거나 해당 라이선스에 맞는 소스 제공 방식을 유지하세요.
- LGPL 라이브러리 수정·교체와 이를 디버깅하기 위한 역공학을 금지하지 않습니다. [교체·재빌드 안내](docs/third-party-source-guide.md)를 참고하세요.
- `licenses/manifest.json`은 보존한 공식 자료의 출처·해시입니다. `python-packages.json`은 빌드 환경 목록이며 실제 제품에 모두 포함됐다는 뜻은 아닙니다. 알려지지 않은 새 의존성은 배포 전에 별도 확인해야 합니다.

상표 사용·코덱 특허·치지직 서비스 약관·입력 콘텐츠의 권리는 별도입니다. 고지와 소스 제공은 이 권리들에 대한 포괄 허가가 아닙니다.

## 자막 템플릿 글꼴

Jua, Gaegu Bold, Black And White Picture 원본 글꼴을 SIL Open Font License 1.1에 따라 동봉합니다. 공식 Google Fonts 저장소의 고정 리비전 파일이며 글꼴 파일은 수정하지 않았습니다. 각 저작권·예약 글꼴 이름·OFL 원문은 `web/fonts/*/OFL.txt`, 출처 URL·리비전·SHA-256은 `web/fonts/sources.json`에 보존합니다. 배포 고지 묶음에도 해당 원문과 출처를 포함합니다.

사용자가 운영체제에 설치한 글꼴은 조회·렌더링에만 사용하며 앱에 복사하거나 외부로 전송하지 않습니다. 설치 글꼴의 영상 제작·상업적 사용 조건은 해당 글꼴 라이선스를 확인해야 합니다. SRT·ASS에는 폰트 파일을 포함하지 않습니다.
