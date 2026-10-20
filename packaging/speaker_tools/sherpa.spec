from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata
root = Path(SPECPATH).parents[1]
data = []
for package in ('sherpa-onnx', 'sherpa-onnx-core', 'numpy', 'soundfile'):
    data += copy_metadata(package)
a = Analysis([str(root/'workers/sherpa_tool.py')], pathex=[str(root)], datas=data,
    hiddenimports=['workers.voices','workers.speech_vad','workers.voice_candidates'],
    excludes=['torch','torchaudio','demucs','pytest','tkinter','matplotlib'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='sherpa-worker',console=True)
coll = COLLECT(exe,a.binaries,a.datas,name='sherpa')
