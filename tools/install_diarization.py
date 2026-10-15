"""선택 엔진만 설치한다. 모델/원본/기존 음성 환경을 변경하지 않는다."""
import argparse
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / '.diarization-tools'
FLUID_REV = '224de0fb3c304b41bbae24e85e1801900865ff3e'
FLUID_SHA = 'dfe0a9c6b8dae2d9b030f1127c74524daab289672cd7a324edca91d1469466e2'


def fetch(url, name, sha):
    file = TOOLS / name
    if not file.exists() or hashlib.sha256(file.read_bytes()).hexdigest() != sha:
        part = file.with_suffix('.part')
        with urllib.request.urlopen(url, timeout=60) as source, part.open('wb') as target:
            shutil.copyfileobj(source, target)
        if hashlib.sha256(part.read_bytes()).hexdigest() != sha:
            raise ValueError('공식 엔진 다운로드 해시가 일치하지 않습니다')
        part.replace(file)
    return file


def fix_font_probe(venv):
    # macOS 27의 빈 SPFontsDataType 결과에 _items가 없어 음성 엔진 import도 실패한다.
    # 전용 환경의 고정 matplotlib 3.11.2에만 빈 목록 처리를 적용한다.
    file=venv/'lib/python3.11/site-packages/matplotlib/font_manager.py'
    before='return [Path(entry["path"]) for entry in d["_items"]]'
    after='return [Path(entry["path"]) for entry in d.get("_items", []) if "path" in entry]'
    text=file.read_text()
    if before in text: file.write_text(text.replace(before,after))
    elif after not in text: raise ValueError('matplotlib 호환 패치 위치가 달라졌습니다. 설치 버전을 확인하세요')


def install(engine):
    if engine not in ('pyannote','fluid'): raise ValueError('지원하지 않는 화자 엔진입니다')
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('현재 준비 스크립트는 Apple Silicon macOS용입니다')
    TOOLS.mkdir(exist_ok=True)
    if engine == 'pyannote':
        uv = shutil.which('uv')
        if not uv: raise ValueError('uv를 먼저 설치하세요: https://docs.astral.sh/uv/getting-started/installation/')
        venv = TOOLS/'pyannote/venv'
        if not (venv/'bin/python').exists(): subprocess.run([uv,'venv','--python','3.11',str(venv)],check=True)
        subprocess.run([uv,'pip','install','--python',str(venv/'bin/python'),'-r',str(ROOT/'requirements-diarization.txt')],check=True)
        fix_font_probe(venv)
    elif engine == 'fluid':
        archive = fetch('https://api.github.com/repos/FluidInference/FluidAudio/tarball/'+FLUID_REV,'fluid-source.tar.gz',FLUID_SHA)
        folder = TOOLS/'fluid'; folder.mkdir(exist_ok=True)
        source = folder/'FluidAudio'
        if not source.exists():
            with tarfile.open(archive) as tar:
                prefix = tar.getmembers()[0].name
                tar.extractall(folder, filter='data')
            (folder/prefix).rename(source)
        runner = folder/'Runner'
        shutil.copytree(ROOT/'native/fluid-diarizer',runner,dirs_exist_ok=True)
        subprocess.run(['swift','build','--package-path',str(runner),'-c','release','--product','archive-fluid-diarizer','-j','4'],check=True)
    print('선택한 화자 엔진 설치 완료. 앱의 모델 준비·검사를 실행하세요.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('engine', choices=['pyannote','fluid'])
    install(parser.parse_args().engine)
