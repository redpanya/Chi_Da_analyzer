# BS-Roformer의 PyTorch 실행 환경은 SAM/기본 백엔드와 분리한다.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
root=Path(SPECPATH).parent
data=collect_data_files('audio_separator')+collect_data_files('librosa')
for package in ('audio-separator','torch','numpy','soundfile','onnxruntime','librosa','einops','rotary-embedding-torch'):
    data+=copy_metadata(package)
a=Analysis([str(root/'workers/roformer.py')],pathex=[str(root)],datas=data,
    hiddenimports=['audio_separator.separator.architectures.mdxc_separator'],
    excludes=['matplotlib','IPython','pytest','tkinter','tensorboard','torchvision','torchaudio'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='roformer-worker',console=True,target_arch='arm64')
coll=COLLECT(exe,a.binaries,a.datas,name='roformer')
