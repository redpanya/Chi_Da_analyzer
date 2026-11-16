"""두 OS 산출물의 체크섬을 확인하고 초안 릴리스 자료만 모은다."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

parser=argparse.ArgumentParser()
parser.add_argument('--artifacts',type=Path,default=Path('artifacts'))
parser.add_argument('--output',type=Path,default=Path('release'))
args=parser.parse_args()
root=args.artifacts;out=args.output;out.mkdir(parents=True,exist_ok=False)
version=json.loads((Path(__file__).resolve().parents[2]/'desktop/package.json').read_text(encoding='utf-8'))['version']
for label in ('macOS-arm64','Windows-x64'):
    folder=root/('package-'+label)
    for line in (folder/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        sha,name=line.split('  ',1)
        if Path(name).name!=name:raise ValueError('잘못된 아티팩트 경로')
        with (folder/name).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==sha
    shutil.copy2(folder/(f'ChiDaanalyzer-{version}-{label}' + ('.dmg' if label.startswith('macOS') else '.zip')),out)
    shutil.copy2(folder/'smoke.json',out/(label+'-smoke.json'))
    shutil.copy2(folder/('license-notices-'+label+'.zip'),out)
shutil.copy2(root/'package-Windows-x64/windows-update-smoke.json',out)
for name in ('native-corresponding-sources.zip','electron-media-sources.zip'):
    shutil.copy2(root/'package-macOS-arm64'/name,out)
source_name='legal-corresponding-sources.zip'
mac_source=root/'package-macOS-arm64'/source_name
win_source=root/'package-Windows-x64'/source_name
if hashlib.sha256(mac_source.read_bytes()).digest()!=hashlib.sha256(win_source.read_bytes()).digest():
    raise ValueError('OS별 라이선스 대응 소스가 다릅니다')
shutil.copy2(mac_source,out)
rows=[]
for file in sorted(out.iterdir()):
    with file.open('rb') as f:rows.append(hashlib.file_digest(f,'sha256').hexdigest()+'  '+file.name)
(out/'SHA256SUMS.txt').write_text('\n'.join(rows)+'\n',encoding='utf-8')
