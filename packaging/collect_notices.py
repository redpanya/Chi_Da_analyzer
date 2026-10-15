"""빌드 환경과 포함되는 시스템 도구의 라이선스·출처를 보존한다."""
from importlib.metadata import distributions
from pathlib import Path
import json,shutil,subprocess,ssl,sys
root=Path(__file__).resolve().parent/'notices';root.mkdir(exist_ok=True)
manifest=[]
for dist in distributions():
 name=dist.metadata['Name']; version=dist.version;folder=root/'python'/name
 for f in dist.files or []:
  if f.name.lower().startswith(('license','copying','notice')):
   file=Path(dist.locate_file(f))
   if file.is_file():
    target=folder/str(f).replace('/','_');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
 manifest.append({'name':name,'version':version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License'),'source':dist.metadata.get_all('Project-URL') or dist.metadata.get('Home-page')})
cellars=set()
for name in ('ffmpeg','ffprobe','whisper-cli','llama-completion','llama-server'):
 pending=[Path(shutil.which(name)).resolve()];seen=set()
 while pending:
  file=pending.pop()
  if file in seen:continue
  seen.add(file)
  if str(file).startswith('/opt/homebrew/Cellar/'):
   cellars.add(Path(*file.parts[:6]))
  for line in subprocess.check_output(['otool','-L',str(file)],text=True).splitlines()[1:]:
   dep=line.strip().split(' (')[0]
   if dep.startswith('/opt/homebrew/') and Path(dep).exists():pending.append(Path(dep).resolve())
# whisper @rpath 라이브러리와 Python도 출처에 포함한다.
for name in ('whisper-cpp','llama.cpp','ggml','python@3.11'):
 parent=Path('/opt/homebrew/Cellar')/name
 if parent.exists():cellars.update(v for v in parent.iterdir() if v.is_dir())
for cellar in sorted(cellars):
 folder=root/'native'/cellar.parent.name;folder.mkdir(parents=True,exist_ok=True)
 for file in cellar.rglob('*'):
  if file.is_file() and (file.name.lower().startswith(('license','copying','notice')) or file.name=='INSTALL_RECEIPT.json' or file.parent.name=='.brew'):
   shutil.copyfile(file,folder/str(file.relative_to(cellar)).replace('/','_'))
(root/'빌드-환경.json').write_text(json.dumps({'python':sys.version,'python_packages':manifest,'native_sources':[str(p) for p in sorted(cellars)],'certificate_source':ssl.get_default_verify_paths().cafile},ensure_ascii=False,indent=2))
(root/'읽어주세요.md').write_text('''# 포함 구성요소 안내\n\n현재 Mac에서 만든 로컬 검증용 앱이다. Python·yt-dlp·FFmpeg/ffprobe·whisper.cpp·llama.cpp·NumPy·sherpa-onnx·MLX/SAM Audio·audio-separator/PyTorch BS-Roformer와 관련 라이브러리를 포함한다. SAM과 BS는 독립 실행기를 사용하며 이전 Demucs 기능은 포함하지 않는다. AI 모델은 앱에 포함하지 않으며 최초 사용 시 기존 모델 준비 기능으로 검증해 사용자 캐시에 저장한다.\n\nPython 라이선스 사본과 Homebrew 도구의 라이선스·빌드 식별 정보는 하위 폴더에 있다. 빌드-환경.json은 빌드 도구도 포함한 환경 목록이며 모든 항목이 최종 앱에서 실행된다는 의미는 아니다.\n\n이 FFmpeg는 --enable-gpl --enable-version3와 x264/x265가 활성화된 빌드다. 관련 안내: https://ffmpeg.org/legal.html . 개발 앱을 외부에 배포하기 전에 정확한 대응 소스·빌드 설정·라이선스 고지를 함께 제공해야 한다. 이 패키지에는 대응 소스 전체가 없으므로 공개 배포 준비 완료로 취급하지 않는다.\n\n기본 문맥 모델 Gemma 4 E4B는 unsloth/gemma-4-E4B-it-GGUF에서 별도로 받는다: https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF . 이전 Qwen 모델도 별도로 받으며 앱에는 모델 가중치를 포함하지 않는다. 각 모델의 이용 조건은 배포처를 확인한다. 고정 버전과 SHA-256은 archive/context_catalog.py 및 archive/context_model.py에 기록했다.\n\nDeveloper ID 서명·Apple 공증은 없다. 로컬 임시 서명은 제작자 신원을 증명하지 않는다. 모델별 조건과 자동 화자/전사 결과의 제한은 사용 안내 및 프로젝트 docs를 참고한다.\n''')
print(len(manifest),len(cellars))
