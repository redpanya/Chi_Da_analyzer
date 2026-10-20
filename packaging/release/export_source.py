"""별도 Git 저장소에 소스만 복사한다. 모델·보관함·개발 환경은 선택하지 않는다."""
import argparse
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]


def export(target):
    target=target.resolve()
    if target==ROOT or target in ROOT.parents:raise ValueError('별도 내보내기 폴더를 선택하세요')
    files=[ROOT/'app.py',ROOT/'requirements.txt',ROOT/'.gitignore',ROOT/'.gitattributes',ROOT/'LICENSE',ROOT/'THIRD-PARTY-NOTICES.md']
    files += [p for p in (ROOT/'licenses').rglob('*') if p.is_file() and not p.is_symlink()]
    files += [p for p in (ROOT/'packaging/release/legal-recipes').rglob('*') if p.is_file() and not p.is_symlink()]
    for name in ('archive','web','workers','tests','docs','.github','native'):
        files += [p for p in (ROOT/name).rglob('*') if p.is_file() and not p.is_symlink()
                  and '__pycache__' not in p.parts and '.build' not in p.parts
                  and p.suffix in ('.py','.json','.js','.mjs','.html','.css','.svg','.md','.yml','.swift')]
    files += [p for p in (ROOT/'packaging').glob('*') if p.is_file() and p.suffix in ('.py','.swift','.spec','.txt','.md')]
    files += [p for p in (ROOT/'packaging/release').iterdir() if p.is_file()]
    files += [p for p in (ROOT/'packaging/speaker_tools').iterdir() if p.is_file() and p.suffix in ('.py','.spec','.txt','.md')]
    files += [ROOT/'tools/install_diarization.py',ROOT/'requirements-diarization.txt']
    for file in files:
        if file.stat().st_size>2*1024*1024:raise ValueError(f'예상보다 큰 소스 파일: {file.name}')
        dest=target/file.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
    shutil.copy2(ROOT/'packaging/release/repository-README.md',target/'README.md')
    print(f'소스 {len(files)+1}개 복사: {target}')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('target',type=Path)
    export(parser.parse_args().target)
