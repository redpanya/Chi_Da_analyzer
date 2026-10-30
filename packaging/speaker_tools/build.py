"""실행 도구 ZIP만 만든다. 앱·모델·사용자 설정을 포함하거나 업로드하지 않는다."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from importlib.metadata import distributions

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from archive import speaker_tools
sys.path.insert(0,str(ROOT/'packaging/release'))
import legal


def source_archive(target):
    """공개 작업기 코드와 이 빌드의 레시피만 담는다. 모델·인증·환경 변수는 제외한다."""
    files = []
    for name in ('archive', 'workers'):
        files += [(p, p.relative_to(ROOT).as_posix()) for p in (ROOT/name).glob('*.py')]
    for name in ('packaging/speaker_tools',):
        files += [(p, p.relative_to(ROOT).as_posix()) for p in (ROOT/name).iterdir()
                  if p.is_file() and p.suffix in ('.py', '.spec', '.txt', '.md')]
    for name in ('LICENSE', 'THIRD-PARTY-NOTICES.md', 'archive/diarization_catalog.json',
                 'packaging/pyannote.spec', '.github/workflows/speaker-tools.yml'):
        files.append((ROOT/name, name))
    legal.zip_files(target, files)


def build(backend, output, fluid=None):
    if not speaker_tools.supported(backend): raise SystemExit('현재 빌드 장치에서 지원하지 않는 실행 도구입니다')
    output = output.resolve(); output.mkdir(parents=True, exist_ok=True)
    package = output/backend
    if package.exists(): raise SystemExit('새 출력 폴더를 지정하세요. 기존 패키지를 덮어쓰지 않습니다')
    if backend == 'fluid':
        if not fluid or not fluid.is_file(): raise SystemExit('--fluid에 빌드된 archive-fluid-diarizer를 지정하세요')
        package.mkdir(); shutil.copy2(fluid,package/speaker_tools.entry_name(backend))
    else:
        spec = ROOT/('packaging/speaker_tools/sherpa.spec' if backend=='sherpa' else 'packaging/pyannote.spec')
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(output/'dist'),
                        '--workpath',str(output/'work'),str(spec)],cwd=ROOT,check=True,
                       env=os.environ|{'PYINSTALLER_CONFIG_DIR':str(output/'pyinstaller-cache')})
        # 설치기는 연결 파일을 받지 않으므로 패키지 안 연결을 실파일로 복사한다.
        shutil.copytree(output/'dist'/backend,package,symlinks=False)
    manifest = {'backend':backend,'protocol':speaker_tools.PROTOCOL,'platform':speaker_tools.platform_id(),
                'entry':speaker_tools.entry_name(backend), 'release':speaker_tools.RELEASE}
    (package/'tool.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    notices = package/'LICENSES'
    legal.collect(notices, python_runtime=backend!='fluid')
    legal.check_folder(notices)
    build_info = {'backend': backend, 'platform': speaker_tools.platform_id(),
                  'python': sys.version.split()[0],
                  'packages': sorted([{'name': d.metadata['Name'], 'version': d.version} for d in distributions()],
                                     key=lambda row: row['name'].lower())}
    (notices/'build-environment.json').write_text(json.dumps(build_info, ensure_ascii=False, indent=2), encoding='utf-8')
    entry=package/speaker_tools.entry_name(backend)
    result=subprocess.run([str(entry),'--speaker-tool-check'],capture_output=True,text=True,timeout=120,check=True)
    if f'CHIDA_SPEAKER_TOOL:1:{backend}' not in result.stdout.splitlines(): raise SystemExit('실행 도구 검사가 실패했습니다')
    target=output/f'chida-{backend}-{speaker_tools.platform_id()}.zip'
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(package.rglob('*')):
            if file.is_file(): archive.write(file,str(file.relative_to(package)))
    suffix = f'{backend}-{speaker_tools.platform_id()}'
    legal.source_archive(output/f'legal-corresponding-sources-{suffix}.zip')
    legal.notice_archive(notices, output/f'license-notices-{suffix}.zip')
    source_archive(output/f'speaker-tool-source-{suffix}.zip')
    digest=hashlib.sha256()
    with target.open('rb') as file:
        while block:=file.read(1024*1024):digest.update(block)
    summary={'file':target.name,'size':target.stat().st_size,'sha256':digest.hexdigest(),'self_check':'passed'}
    (output/f'{suffix}-build.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/f'SHA256SUMS-{suffix}.txt').write_text(''.join(
        f'{legal.digest(file)}  {file.name}\n' for file in sorted(output.glob('*.zip'))), encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backend',choices=['sherpa','pyannote','fluid'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fluid',type=Path)
    args=parser.parse_args()
    build(args.backend,args.output,args.fluid)
