"""모델·개인 자료 없이 .app 또는 Windows 포터블 폴더를 만든다."""
import argparse
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
from macos_package_check import verify_bundle

ROOT = Path(__file__).resolve().parents[2]
NAME = 'ChiDaanalyzer'


def run(args): subprocess.run([str(x) for x in args],check=True)


def notices(folder):
    rows=[]
    for dist in distributions():
        name=dist.metadata['Name']; rows.append({'name':name,'version':dist.version,'source':dist.metadata.get_all('Project-URL')})
        for f in dist.files or []:
            if f.name.lower().startswith(('license','copying','notice')):
                source=Path(dist.locate_file(f))
                if source.is_file():
                    dest=folder/'python'/name/str(f).replace('/', '_').replace('\\','_')
                    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'python-packages.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copy2(ROOT/'packaging/release/sources.json',folder/'native-sources.json')


def assemble(version):
    output=ROOT/'dist/release';output.mkdir(parents=True,exist_ok=True)
    backend=ROOT/'build/frozen/backend'
    if sys.platform=='darwin':
        package=output/(NAME+'.app');resources=package/'Contents/Resources'
        dest=resources/'backend'
    else:
        package=output/'ChiDaanalyzer';dest=package
    if package.exists():raise ValueError('기존 패키지가 있습니다. 빌드 출력 폴더를 별도로 사용하세요')
    shutil.copytree(backend,dest)
    shutil.copytree(ROOT/'build/native',dest/'_internal/native')
    (dest/'_internal/basic-release.json').write_text('{"speakers":["sherpa"]}',encoding='utf-8')
    notices(package/'THIRD-PARTY-NOTICES' if sys.platform!='darwin' else resources/'THIRD-PARTY-NOTICES')
    shutil.copy2(ROOT/'docs/배포-사용안내.md',package/'README.ko.md' if sys.platform!='darwin' else resources/'README.ko.md')
    if sys.platform=='darwin':
        executables=package/'Contents/MacOS';executables.mkdir()
        trash=dest/'_internal/bin/vod-trash';trash.parent.mkdir(exist_ok=True)
        for source,target in [('Launcher.swift',executables/'ArchiveLauncher'),('Trash.swift',trash)]:
            run(['swiftc','-O','-target','arm64-apple-macos14.0','-module-cache-path',ROOT/'build/swift-cache',ROOT/'packaging'/source,'-o',target])
        info={'CFBundleIdentifier':'local.chzzk.archive','CFBundleName':NAME,'CFBundleDisplayName':NAME,
              'CFBundleExecutable':'ArchiveLauncher','CFBundlePackageType':'APPL','CFBundleShortVersionString':version,
              'CFBundleVersion':os.environ.get('GITHUB_RUN_NUMBER','1'),'LSMinimumSystemVersion':'14.0',
              'NSHighResolutionCapable':True}
        with (package/'Contents/Info.plist').open('wb') as f:plistlib.dump(info,f)
        run(['codesign','--force','--deep','--sign','-',package])
        verify_bundle(package)
    else:
        (dest/'archive-backend.exe').rename(dest/'ChiDaanalyzer.exe')
    print(package)
    return package


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--version',default='0.18.1')
    assemble(parser.parse_args().version)
