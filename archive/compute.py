"""Windows 전사·요약 가속 선택. CPU 실행기는 GPU 드라이버와 독립적으로 유지한다."""
from functools import lru_cache
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys

from . import runtime


def windows():
    return sys.platform == 'win32'


def mode():
    value = runtime.settings().get('windows_compute', 'cpu')
    return value if value in ('cpu', 'hybrid') else 'cpu'


def gpu_binary(name):
    base = Path(sys._MEIPASS) if runtime.FROZEN else Path(__file__).resolve().parents[1]/'build'
    engine = 'whisper' if name == 'whisper-cli' else 'llama'
    return base/'native'/f'{engine}-vulkan'/(name+'.exe')


@lru_cache(maxsize=4)
def probe(binary):
    loader = Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/vulkan-1.dll'
    if windows() and not loader.is_file():
        return {'available': False, 'note': 'Vulkan 드라이버가 없습니다. 그래픽 제조사의 드라이버 설치 후 GPU 다시 확인을 누르세요.'}
    try:
        # 드라이버 누락·초기화 실패도 별도 프로세스에서 끝나야 CPU 실행이 가능하다.
        result = subprocess.run([binary, '--list-devices'], capture_output=True, timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        text = result.stdout.decode('utf-8', 'replace')
        devices = re.findall(r'^\s*(Vulkan\d+):\s*(.+)$', text, re.M)
        if result.returncode or not devices:
            return {'available': False, 'note': '사용 가능한 Vulkan GPU를 확인하지 못했습니다. 그래픽 드라이버를 확인하고 GPU 다시 확인을 누르세요.'}
        return {'available': True, 'note': '감지된 GPU: '+ ' · '.join(label for _, label in devices)}
    except (OSError, subprocess.TimeoutExpired):
        return {'available': False, 'note': 'GPU 실행기 또는 Vulkan 드라이버를 사용할 수 없습니다. 드라이버 설치 후 GPU 다시 확인을 누르세요.'}


def status(refresh=False):
    if not windows():
        return {'visible': False}
    if refresh:
        probe.cache_clear()
    bundled = all(gpu_binary(name).is_file() for name in ('llama-server', 'llama-completion', 'whisper-cli'))
    result = (probe(str(gpu_binary('llama-server'))) if bundled else
              {'available': False, 'note': '이 배포본에는 GPU 실행기가 없습니다. CPU + GPU 지원 Windows 배포본이 필요합니다.'})
    selected = mode()
    note = ('CPU로 처리합니다. ' if selected == 'cpu' else
            '전사·문맥 요약에 CPU + GPU 가속을 요청합니다. ' if result['available'] else '현재는 CPU로 처리합니다. ')
    return {'visible': True, 'mode': selected, 'bundled': bundled, **result, 'note': note+result['note']}


def apply(value):
    if not windows():
        raise ValueError('처리 장치 선택은 Windows에서만 지원합니다')
    if not isinstance(value, str) or value not in ('cpu', 'hybrid'):
        raise ValueError('CPU 또는 CPU + GPU를 선택하세요')
    runtime.save_settings(windows_compute=value)


def select(name):
    binary = shutil.which(name)
    if not windows():
        return {'binary': binary, 'backend': 'default', 'args': [] if name == 'whisper-cli' else ['-ngl', '99']}
    info = status()
    gpu = info['mode'] == 'hybrid' and info['available']
    args = ([] if gpu else ['--no-gpu']) if name == 'whisper-cli' else ['-ngl', 'auto' if gpu else '0']
    return {'binary': str(gpu_binary(name)) if gpu else binary, 'backend': 'vulkan' if gpu else 'cpu',
            'requested': info['mode'], 'args': args, 'note': info['note']}


def failure_hint(plan):
    return (' GPU 오류·메모리 부족이면 가져오기에서 CPU만 사용으로 변경한 뒤 이어서 처리하세요. 완료 결과는 유지됩니다.'
            if plan.get('backend') == 'vulkan' else '')
