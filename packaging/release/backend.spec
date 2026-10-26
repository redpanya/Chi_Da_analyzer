from pathlib import Path
import certifi
import sys
from PyInstaller.utils.hooks import copy_metadata
root = Path(SPECPATH).parents[1]
data = [(str(root/'web'),'web'),
        (str(root/'archive/diarization_catalog.json'),'archive'), (certifi.where(),'certs')]
for package in ('sherpa-onnx','sherpa-onnx-core','soundfile','numpy','yt-dlp'):
    data += copy_metadata(package)
a = Analysis([str(root/'app.py')], pathex=[str(root)], binaries=[], datas=data,
             hiddenimports=['workers.voices','workers.voice_candidates','sherpa_onnx','send2trash'],
             excludes=['torch','torchaudio','demucs','tkinter','matplotlib','IPython','pytest'],noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='archive-backend',console=True,
          target_arch='arm64' if sys.platform=='darwin' else None)
coll = COLLECT(exe,a.binaries,a.datas,name='backend')
