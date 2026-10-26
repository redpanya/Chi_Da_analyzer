# Python과 선택 음성 엔진을 한 실행 파일에 모으고 실제 추론은 별도 프로세스로 실행한다.
from pathlib import Path
import shutil, ssl
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
root=Path(SPECPATH).parent
binary=[(shutil.which(name),'bin') for name in ('ffmpeg','ffprobe','whisper-cli','llama-completion','llama-tokenize','llama-server')]
data=[(str(root/'web'),'web'),(ssl.get_default_verify_paths().cafile,'certs')]
data.insert(1,(str(root/'archive/diarization_catalog.json'),'archive'))
# cert.pem은 실행 시 일관된 이름을 사용한다.
cert=Path(ssl.get_default_verify_paths().cafile)
cert_copy=Path(SPECPATH)/'cacert.pem'
shutil.copyfile(cert,cert_copy)
data[-1]=(str(cert_copy),'certs')
for package in ('sherpa_onnx','soundfile','numpy','yt_dlp'):
    data+=copy_metadata(package.replace('_','-'))
a=Analysis([str(root/'app.py')],pathex=[str(root)],binaries=binary,datas=data,
           hiddenimports=['workers.voices','sherpa_onnx'],
           excludes=['torch','torchaudio','demucs','tkinter','matplotlib','IPython','pytest'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='archive-backend',console=True,target_arch='arm64')
coll=COLLECT(exe,a.binaries,a.datas,name='backend')
