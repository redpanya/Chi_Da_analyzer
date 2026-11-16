"""검증한 Electron에 기존 처리 서버와 외부 도구를 함께 담는다."""
import argparse
import hashlib
import tarfile
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

import legal
from macos_package_check import verify_bundle

ROOT = Path(__file__).resolve().parents[2]
NAME = 'ChiDaanalyzer'
SOURCES = json.loads(Path(__file__).with_name('electron-sources.json').read_text(encoding='utf-8'))


def source_digest(name, file):
    if name != 'chromium-ffmpeg.tar.gz':
        return legal.digest(file)
    # Gitiles는 내려받을 때마다 tar의 시각을 갱신한다. 경로, 권한, 링크와 내용은 고정한다.
    rows = []
    with tarfile.open(file, 'r|gz') as archive:
        for entry in archive:
            contents = hashlib.sha256(archive.extractfile(entry).read()).hexdigest() if entry.isfile() else ''
            rows.append([entry.name, entry.type.decode('ascii'), entry.mode, entry.linkname, contents])
    return hashlib.sha256(json.dumps(sorted(rows), separators=(',', ':')).encode()).hexdigest()


def source(name):
    url, expected = SOURCES['files'][name]
    dest = ROOT / 'build/desktop-downloads' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        part = dest.with_suffix('.part')
        try:
            legal.download(url, part)
            if source_digest(name, part) != expected:
                raise ValueError('Electron 자료 해시 불일치: ' + name)
            part.replace(dest)
        finally:
            part.unlink(missing_ok=True)
    if source_digest(name, dest) != expected:
        raise ValueError('캐시 해시 불일치: ' + name)
    return dest


def mac_shell(archive, package):
    with tempfile.TemporaryDirectory(dir=package.parent) as temp:
        subprocess.run(['ditto', '-x', '-k', archive, temp], check=True)
        (Path(temp) / 'Electron.app').rename(package)
    plist = package / 'Contents/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    version = json.loads((ROOT / 'desktop/package.json').read_text())['version']
    info.update(CFBundleName=NAME, CFBundleDisplayName='치다 분석기', CFBundleIdentifier='local.chzzk.archive',
                CFBundleExecutable=NAME, CFBundleShortVersionString=version, CFBundleVersion=version,
                LSMinimumSystemVersion='14.0', LSApplicationCategoryType='public.app-category.video')
    info.pop('ElectronAsarIntegrity', None)  # 기본 데모 앱 대신 resources/app을 실행한다.
    plist.write_bytes(plistlib.dumps(info))
    (package / 'Contents/MacOS/Electron').rename(package / 'Contents/MacOS' / NAME)
    resources = package / 'Contents/Resources'
    shutil.copyfile(ROOT / 'packaging/icons/ChiDaanalyzer.icns', resources / info['CFBundleIconFile'])
    return resources


def windows_shell(archive, package):
    from PyInstaller.utils.win32.icon import CopyIcons
    with zipfile.ZipFile(archive) as content:
        content.extractall(package)
    exe = package / (NAME + '.exe')
    (package / 'electron.exe').rename(exe)
    (package / 'electron_wer.dll').rename(package / (NAME + '_wer.dll'))
    CopyIcons(str(exe), [str(ROOT / 'packaging/icons/ChiDaanalyzer.ico')])
    resources = package / 'resources'
    shutil.copy2(ROOT / 'build/desktop-helper/chida-update.exe', resources)
    return resources


def assemble(version):
    desktop = ROOT / 'desktop'
    project = json.loads((desktop / 'package.json').read_text(encoding='utf-8'))
    if version != project['version'] or project['devDependencies']['electron'] != SOURCES['version']:
        raise ValueError('앱 또는 Electron 버전 불일치')
    mac = sys.platform == 'darwin'
    if not mac and sys.platform != 'win32':
        raise ValueError('대상 운영체제에서 빌드하세요')
    output = ROOT / 'dist/release'
    output.mkdir(parents=True, exist_ok=True)
    package = output / (NAME + '.app' if mac else NAME)
    if package.exists():
        raise ValueError('대상 패키지가 이미 있습니다. 빈 빌드 출력 폴더를 사용하세요')
    archive = source('electron-mac.zip' if mac else 'electron-win.zip')
    resources = mac_shell(archive, package) if mac else windows_shell(archive, package)
    (resources / 'default_app.asar').unlink(missing_ok=True)
    app = resources / 'app'
    app.mkdir()
    for file in [desktop / 'package.json', desktop / 'release-public.pem', *sorted(desktop.glob('*.cjs'))]:
        shutil.copy2(file, app)
    backend = resources / 'backend'
    shutil.copytree(ROOT / 'build/frozen/backend', backend)
    native = backend / '_internal/native'
    shutil.copytree(ROOT / 'build/native', native)
    (native / 'ffmpeg/build-config.log').unlink(missing_ok=True)
    (backend / '_internal/basic-release.json').write_text('{"speakers":["sherpa"]}', encoding='utf-8')
    if mac:
        trash = backend / '_internal/bin/vod-trash'
        trash.parent.mkdir(exist_ok=True)
        subprocess.run(['swiftc', '-O', '-target', 'arm64-apple-macos14.0', ROOT / 'packaging/Trash.swift',
                        '-o', trash], check=True)
    notices = resources / 'THIRD-PARTY-NOTICES'
    legal.collect(notices)
    legal.check_folder(notices)
    shutil.copy2(ROOT / 'packaging/release/sources.json', notices / 'native-sources.json')
    with zipfile.ZipFile(archive) as content:
        (notices / 'LICENSE.electron.txt').write_bytes(content.read('LICENSE'))
        (notices / 'LICENSES.chromium.html').write_bytes(content.read('LICENSES.chromium.html'))
    shutil.copy2(source('node-LICENSE.txt'), notices)
    shutil.copy2(ROOT / 'packaging/release/electron-sources.json', notices)
    shutil.copy2(ROOT / 'docs/배포-사용안내.md', resources / 'README.ko.md')
    if mac:
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', package], check=True)
        verify_bundle(package)
    else:
        files = sorted(p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file())
        directories = sorted(p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_dir())
        inventory = {'app': NAME, 'version': version, 'files': files, 'directories': directories}
        (package / 'chida-package.json').write_text(json.dumps(inventory), encoding='utf-8')
    print(package)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default=json.loads((ROOT/'desktop/package.json').read_text())['version'])
    assemble(parser.parse_args().version)
