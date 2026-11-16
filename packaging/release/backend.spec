from pathlib import Path
import certifi
import sys
from PyInstaller.utils.hooks import copy_metadata, collect_submodules
root = Path(SPECPATH).parents[1]
data = [(str(root/'web'),'web'),
        (str(root/'archive/diarization_catalog.json'),'archive'), (certifi.where(),'certs')]
for package in ('yt-dlp','fonttools'):
    data += copy_metadata(package)
a = Analysis([str(root/'app.py')], pathex=[str(root)], binaries=[], datas=data,
             hiddenimports=['send2trash']+collect_submodules('fontTools.ttLib.tables'),
             excludes=['sherpa_onnx','onnxruntime','numpy','soundfile','torch','torchaudio','demucs','tkinter','matplotlib','IPython','pytest'],noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='archive-backend',console=True,
          icon=str(root/'packaging/icons/ChiDaanalyzer.ico') if sys.platform=='win32' else None,
          target_arch='arm64' if sys.platform=='darwin' else None)
coll = COLLECT(exe,a.binaries,a.datas,name='backend')
