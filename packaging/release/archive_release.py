"""포터블 앱과 대응 소스를 묶고 실제 배포 이미지에서 앱을 실행한다."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

import legal
from assemble import ROOT, NAME, source
from macos_package_check import verify_bundle


def desktop_smoke(binary):
    with tempfile.TemporaryDirectory(prefix='chida-desktop-') as directory:
        report = Path(directory) / 'smoke.json'
        run = subprocess.run([str(binary), '--desktop-smoke'], env=os.environ | {'CHIDA_DESKTOP_SMOKE_DIR': directory},
                             timeout=120, capture_output=True)
        if run.returncode or not report.is_file():
            failure = Path(directory) / 'failure.txt'
            raise RuntimeError(failure.read_text(encoding='utf-8') if failure.exists()
                               else run.stderr.decode('utf-8', 'replace')[-4000:] or f'앱 종료 코드 {run.returncode}')
        return json.loads(report.read_text(encoding='utf-8'))


def package_app(output, version):
    mac = sys.platform == 'darwin'
    label = 'macOS-arm64' if mac else 'Windows-x64'
    stem = output / f'{NAME}-{version}-{label}'
    package = ROOT / 'dist/release' / (NAME + '.app' if mac else NAME)
    with tempfile.TemporaryDirectory(prefix='chida-package-') as temp:
        workspace = Path(temp)
        if mac:
            volume = workspace / 'volume'
            volume.mkdir()
            subprocess.run(['ditto', package, volume / package.name], check=True)
            (volume / 'Applications').symlink_to('/Applications')
            image = Path(str(stem) + '.dmg')
            subprocess.run(['hdiutil', 'create', '-ov', '-srcfolder', volume, '-volname', NAME, '-format', 'UDZO', image], check=True)
            mount = workspace / 'mounted'
            subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, image], check=True)
            try:
                app = mount / package.name
                verify_bundle(app)
                result = desktop_smoke(app / 'Contents/MacOS' / NAME)
            finally:
                subprocess.run(['hdiutil', 'detach', mount], check=True)
            resources = package / 'Contents/Resources'
        else:
            packed = shutil.make_archive(str(stem), 'zip', package.parent, package.name)
            with zipfile.ZipFile(packed) as archive:
                archive.extractall(workspace)
            result = desktop_smoke(workspace / package.name / (NAME + '.exe'))
            resources = package / 'resources'
    return label, resources / 'THIRD-PARTY-NOTICES', result


def main():
    output = ROOT / 'dist/artifacts'
    output.mkdir(parents=True, exist_ok=True)
    version = json.loads((ROOT / 'desktop/package.json').read_text(encoding='utf-8'))['version']
    label, notices, desktop = package_app(output, version)
    smoke = json.loads((ROOT / 'dist/smoke.json').read_text(encoding='utf-8'))
    smoke['desktop'] = desktop
    (output / 'smoke.json').write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding='utf-8')
    legal.notice_archive(notices, output / f'license-notices-{label}.zip')
    legal.source_archive(output / 'legal-corresponding-sources.zip')
    with zipfile.ZipFile(output / 'native-corresponding-sources.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for folder in (ROOT/'build/release-sources', ROOT/'packaging/release'):
            for file in sorted(folder.iterdir()):
                if file.is_file():
                    archive.write(file, folder.name + '/' + file.name)
    with zipfile.ZipFile(output / 'electron-media-sources.zip', 'w') as archive:
        for name in ('electron-src.tgz', 'chromium-ffmpeg.tar.gz'):
            archive.write(source(name), name)
        for name in ('electron-sources.json', 'assemble.py'):
            archive.write(ROOT / 'packaging/release' / name, name)
        archive.write(ROOT / 'docs/third-party-source-guide.md', 'source-guide.md')
    lines = [legal.digest(file) + '  ' + file.name for file in sorted(output.iterdir())
             if file.suffix in {'.zip', '.dmg', '.json'}]
    (output/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
