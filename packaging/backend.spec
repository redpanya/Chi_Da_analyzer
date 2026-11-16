# 앱의 Python 실행기와 기본 미디어 도구를 구성한다.
from pathlib import Path
import shutil, ssl
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_submodules
root=Path(SPECPATH).parent
binary=[(shutil.which(name),'bin') for name in ('ffmpeg','ffprobe','whisper-cli','llama-completion','llama-tokenize','llama-server')]
data=[(str(root/'web'),'web'),(ssl.get_default_verify_paths().cafile,'certs')]
data.insert(1,(str(root/'archive/diarization_catalog.json'),'archive'))
# cert.pem은 실행 시 일관된 이름을 사용한다.
cert=Path(ssl.get_default_verify_paths().cafile)
cert_copy=Path(SPECPATH)/'cacert.pem'
shutil.copyfile(cert,cert_copy)
data[-1]=(str(cert_copy),'certs')
for package in ('yt_dlp','fonttools'):
    data+=copy_metadata(package.replace('_','-'))
a=Analysis([str(root/'app.py')],pathex=[str(root)],binaries=binary,datas=data,
           hiddenimports=collect_submodules('fontTools.ttLib.tables'),
           excludes=['sherpa_onnx','onnxruntime','numpy','soundfile','torch','torchaudio','demucs','tkinter','matplotlib','IPython','pytest'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='archive-backend',console=True,target_arch='arm64')
coll=COLLECT(exe,a.binaries,a.datas,name='backend')
