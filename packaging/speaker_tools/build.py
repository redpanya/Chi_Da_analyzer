"""실행 도구 ZIP만 만든다. 앱·모델·사용자 설정을 포함하거나 업로드하지 않는다."""
import argparse
import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from archive import speaker_tools


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
    notices = package/'LICENSES'; notices.mkdir()
    if backend == 'fluid':
        source=ROOT/'.diarization-tools/fluid/FluidAudio'
        for license in source.rglob('LICENSE*'):
            if license.is_file() and '.build' not in license.parts and '.git' not in license.parts:
                target=notices/license.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(license,target)
        if not list(notices.rglob('*')): raise SystemExit('FluidAudio 라이선스 원문이 필요합니다')
        (notices/'출처.txt').write_text('FluidInference/FluidAudio · 224de0fb3c304b41bbae24e85e1801900865ff3e\nhttps://github.com/FluidInference/FluidAudio\n모델은 포함하지 않음\n',encoding='utf-8')
    else:
        manifest=[]
        for dist in distributions():
            name=dist.metadata.get('Name','unknown')
            manifest.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License')})
            for entry in dist.files or []:
                if entry.name.lower().startswith(('license','copying','notice')):
                    file=Path(dist.locate_file(entry))
                    if file.is_file():
                        target=notices/name/str(entry).replace('/','_');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
        (notices/'빌드환경.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    entry=package/speaker_tools.entry_name(backend)
    result=subprocess.run([str(entry),'--speaker-tool-check'],capture_output=True,text=True,timeout=120,check=True)
    if f'CHIDA_SPEAKER_TOOL:1:{backend}' not in result.stdout.splitlines(): raise SystemExit('실행 도구 검사가 실패했습니다')
    target=output/f'chida-{backend}-{speaker_tools.platform_id()}.zip'
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(package.rglob('*')):
            if file.is_file(): archive.write(file,str(file.relative_to(package)))
    digest=hashlib.sha256()
    with target.open('rb') as file:
        while block:=file.read(1024*1024):digest.update(block)
    summary={'file':str(target),'size':target.stat().st_size,'sha256':digest.hexdigest(),'self_check':'passed'}
    (output/f'{backend}-검증.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backend',choices=['sherpa','pyannote','fluid'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fluid',type=Path)
    args=parser.parse_args()
    build(args.backend,args.output,args.fluid)
