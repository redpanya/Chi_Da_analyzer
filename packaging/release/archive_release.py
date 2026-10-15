"""배포 ZIP·대응 소스·체크섬을 함께 만든다."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
out=ROOT/'dist/artifacts';out.mkdir(parents=True,exist_ok=True)
if sys.platform=='darwin':
    app=next((ROOT/'dist/release').glob('*.app'))
    subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(app),str(out/'ChiDaanalyzer-macOS-arm64.zip')],check=True)
    from macos_package_check import check_archive
    report=json.loads((ROOT/'dist/smoke.json').read_text(encoding='utf-8'))
    report['macos_distribution']=check_archive(out/'ChiDaanalyzer-macOS-arm64.zip')
    report['checks'] += ['ZIP 2종 해제 후 서명·영문 파일명', 'LaunchServices 실제 앱 실행·서버 응답']
    (ROOT/'dist/smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
else:
    shutil.make_archive(str(out/'ChiDaanalyzer-Windows-x64'),'zip',ROOT/'dist/release','ChiDaanalyzer')
with zipfile.ZipFile(out/'native-corresponding-sources.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
    for folder in (ROOT/'build/release-sources',ROOT/'packaging/release'):
        for file in sorted(folder.iterdir()):
            if file.is_file():archive.write(file,folder.name+'/'+file.name)
checks=[]
for file in sorted(out.glob('*.zip')):
    with file.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    checks.append(f'{sha}  {file.name}')
(out/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n',encoding='utf-8')
shutil.copy2(ROOT/'dist/smoke.json',out/'smoke.json')
