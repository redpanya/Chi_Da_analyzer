# Metal SAM은 별도 Python·NumPy 환경에 묶어 기존 화자 런타임과 충돌을 방지한다.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
root=Path(SPECPATH).parent
data=[]
for package in ('mlx','mlx_audio','transformers','tokenizers','soundfile','sentencepiece'):
    data+=collect_data_files(package)
for package in ('mlx','mlx-metal','mlx-audio','transformers','huggingface-hub','tokenizers','numpy','soundfile','safetensors','tqdm','regex','packaging','pyyaml'):
    data+=copy_metadata(package)
a=Analysis([str(root/'workers/sam.py')],pathex=[str(root)],datas=data,
    hiddenimports=collect_submodules('mlx')+collect_submodules('mlx_audio.sts.models.sam_audio')+collect_submodules('transformers.models.t5')+['transformers.models.t5.tokenization_t5'],
    excludes=['torch','torchaudio','matplotlib','IPython','pytest','tkinter'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='sam-worker',console=True,target_arch='arm64')
coll=COLLECT(exe,a.binaries,a.datas,name='sam')
