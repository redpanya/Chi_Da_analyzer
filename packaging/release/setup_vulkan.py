"""Windows CI에 고정된 공식 SDK를 복사 설치한다. 배포본에는 SDK를 넣지 않는다."""
import hashlib
import os
from pathlib import Path
import subprocess
from urllib.request import urlopen

VERSION = '1.4.328.1'
SHA256 = 'a8675df6d538079c2a719a9373994948091db785b48f142e024254e76348d16c'


def install():
    if os.name != 'nt': raise RuntimeError('Windows 빌드에서만 SDK를 준비합니다')
    work = Path(os.environ.get('RUNNER_TEMP', 'build')).resolve()
    work.mkdir(parents=True, exist_ok=True)
    installer = work/f'vulkan-{VERSION}.exe'
    with urlopen(f'https://sdk.lunarg.com/sdk/download/{VERSION}/windows/vulkan_sdk.exe', timeout=120) as response, installer.open('wb') as file:
        while block := response.read(1024*1024): file.write(block)
    with installer.open('rb') as file:
        if hashlib.file_digest(file, 'sha256').hexdigest() != SHA256:
            raise ValueError('Vulkan SDK 해시가 일치하지 않습니다')
    dest = work/f'VulkanSDK-{VERSION}'
    subprocess.run([str(installer), '--root', str(dest), '--accept-licenses', '--default-answer',
                    '--confirm-command', 'install', 'copy_only=1'], check=True, timeout=600)
    for relative in ('Bin/glslc.exe', 'Lib/vulkan-1.lib', 'Include/vulkan/vulkan.h'):
        if not (dest/relative).is_file(): raise ValueError('Vulkan SDK 설치 파일이 없습니다: '+relative)
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as file: file.write(f'VULKAN_SDK={dest}\n')
    print(f'VULKAN_SDK={dest}')


if __name__ == '__main__': install()
