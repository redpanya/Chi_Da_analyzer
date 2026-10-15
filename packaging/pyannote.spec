# Community-1은 전용 PyTorch 환경을 유지해 BS/SAM과 버전이 섞이지 않게 한다.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
root=Path(SPECPATH).parent
data=[(str(root/'archive/diarization_catalog.json'),'archive')]
for package in ('pyannote.audio','pyannote.database','pyannote.metrics','pyannote.pipeline'):
    data+=collect_data_files(package)
data+=copy_metadata('pyannote.audio',recursive=True)
a=Analysis([str(root/'workers/diarization_pyannote.py')],pathex=[str(root)],datas=data,
    hiddenimports=collect_submodules('pyannote.audio.models')+collect_submodules('pyannote.audio.pipelines'),
    excludes=['IPython','pytest','tkinter','tensorboard','torchvision'],
    hooksconfig={'matplotlib':{'backends':['Agg']}},noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='pyannote-worker',console=True,target_arch='arm64')
coll=COLLECT(exe,a.binaries,a.datas,name='pyannote')
