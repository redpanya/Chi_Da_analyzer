"""별도 Git 저장소에 소스만 복사한다. 모델·보관함·개발 환경은 선택하지 않는다."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]


def export(target, *, docs=True):
    target=target.resolve()
    if target==ROOT or target in ROOT.parents:raise ValueError('별도 내보내기 폴더를 선택하세요')
    files=[ROOT/'app.py',ROOT/'requirements.txt',ROOT/'.gitignore',ROOT/'.gitattributes',ROOT/'LICENSE',ROOT/'THIRD-PARTY-NOTICES.md']
    files += [p for p in (ROOT/'licenses').rglob('*') if p.is_file() and not p.is_symlink()]
    files += [p for p in (ROOT/'packaging/release/legal-recipes').rglob('*') if p.is_file() and not p.is_symlink()]
    for name in ('archive','web','workers','tests','.github','native', *(('docs',) if docs else ())):
        files += [p for p in (ROOT/name).rglob('*') if p.is_file() and not p.is_symlink()
                  and '__pycache__' not in p.parts and '.build' not in p.parts
                  and p.suffix in ('.py','.json','.js','.mjs','.html','.css','.svg','.md','.yml','.swift')]
    # 글꼴은 출처 목록에 고정된 파일만 반출한다. 사용자 설치 글꼴은 포함하지 않는다.
    fonts = ROOT/'web/fonts'
    font_files = []
    for row in json.loads((fonts/'sources.json').read_text(encoding='utf-8')):
        file = fonts/row['file']
        if not file.resolve().is_relative_to(fonts.resolve()) or file.is_symlink():
            raise ValueError('글꼴 자산 경로를 확인하세요')
        if hashlib.sha256(file.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('글꼴 자산 해시가 다릅니다: '+row['file'])
        font_files.append(file)
    files += font_files
    files += list((ROOT/'web/patterns').glob('pattern-*.webp'))
    # 직접 생성한 HTTPS 회귀 검사 영상만 허용한다. 사용자 영상은 반출하지 않는다.
    fixtures = {
        'https-media.mp4': '064e914cf3ac2c20cc1df6761abc348cecdf7cf898c0a3e68373624e76eef653',
        'https-master.m3u8': '6bcce75c2bbe6bcf82c8f835f6f5dc4a1b792e5a0b68553e734ced27465d4c9e',
        'https-media.m3u8': 'ed7a9e5fb71c28f0733657513c879292740d3c6f18c9ab6afc0690499954461e',
        'https-segment.ts': 'f07419d4427ec4927855a6caefbf3a0628cdda746d31794b30abb5790db89010',
    }
    for name, digest in fixtures.items():
        fixture = ROOT/'tests/fixtures'/name
        if hashlib.sha256(fixture.read_bytes()).hexdigest() != digest:
            raise ValueError('HTTPS 합성 검사 자료 해시가 다릅니다: '+name)
        files.append(fixture)
    files += [p for p in (ROOT/'packaging').glob('*') if p.is_file() and p.suffix in ('.py','.swift','.spec','.txt','.md')]
    files += [p for p in (ROOT/'packaging/release').iterdir() if p.is_file()]
    files += [p for p in (ROOT/'packaging/speaker_tools').iterdir() if p.is_file() and p.suffix in ('.py','.spec','.txt','.md')]
    files += [ROOT/'tools/install_diarization.py',ROOT/'requirements-diarization.txt']
    for file in files:
        if file.stat().st_size>2*1024*1024 and file not in font_files:raise ValueError(f'예상보다 큰 소스 파일: {file.name}')
        dest=target/file.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
    shutil.copy2(ROOT/'packaging/release/repository-README.md',target/'README.md')
    print(f'소스 {len(files)+1}개 복사: {target}')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('target',type=Path)
    parser.add_argument('--without-docs', action='store_true', help='공개 검토한 문서는 별도로 복사')
    args=parser.parse_args();export(args.target, docs=not args.without_docs)
