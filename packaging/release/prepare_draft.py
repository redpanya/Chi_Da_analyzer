"""두 OS 산출물의 체크섬을 확인하고 초안 릴리스 자료만 모은다."""
import hashlib
from pathlib import Path
import shutil

root=Path('artifacts');out=Path('release');out.mkdir(exist_ok=False)
for label in ('macOS-arm64','Windows-x64'):
    folder=root/('package-'+label)
    for line in (folder/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        sha,name=line.split('  ',1)
        if Path(name).name!=name:raise ValueError('잘못된 아티팩트 경로')
        with (folder/name).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==sha
    shutil.copy2(folder/('Chi_Da_analyzer-'+label+'.zip'),out)
    shutil.copy2(folder/'smoke.json',out/(label+'-smoke.json'))
shutil.copy2(root/'package-macOS-arm64/native-corresponding-sources.zip',out)
rows=[]
for file in sorted(out.iterdir()):
    with file.open('rb') as f:rows.append(hashlib.file_digest(f,'sha256').hexdigest()+'  '+file.name)
(out/'SHA256SUMS.txt').write_text('\n'.join(rows)+'\n',encoding='utf-8')
