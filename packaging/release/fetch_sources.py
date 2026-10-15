"""고정 소스를 받고 체크섬 검증 후 빌드 폴더에 푼다."""
import hashlib
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name('sources.json')


def fetch():
    specs = json.loads(MANIFEST.read_text(encoding='utf-8'))
    folder = ROOT/'build/release-sources'
    folder.mkdir(parents=True, exist_ok=True)
    for name, spec in specs.items():
        file = folder/(name+'.tar.gz')
        if not file.exists():
            url = f"https://codeload.github.com/{spec['repo']}/tar.gz/{spec['commit']}"
            with urlopen(url, timeout=120) as response, file.with_suffix('.part').open('wb') as output:
                while block := response.read(1024*1024): output.write(block)
            file.with_suffix('.part').replace(file)
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        if digest != spec['sha256']:
            raise ValueError(f'{name} 소스 체크섬 불일치: 다운로드를 다시 확인하세요')
        target = ROOT/'build/native-src'/name
        if target.exists(): continue
        target.mkdir(parents=True)
        with tarfile.open(file) as archive:
            # GitHub 소스의 최상위 폴더를 유지하고 경로 탈출은 거부한다.
            archive.extractall(target, filter='data')
        print(name, digest, flush=True)
    return specs


if __name__ == '__main__': fetch()
