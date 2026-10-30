"""성능 비교에 필요한 항목만 읽는다. 컴퓨터 이름·일련번호는 조회하지 않는다."""
import json
import ntpath
import os
import platform
import subprocess
from functools import lru_cache


def command(args):
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    return subprocess.check_output(args, timeout=12, stderr=subprocess.DEVNULL, **flags).decode('utf-8-sig', errors='replace').strip()


def windows_command():
    # 패키지의 제한된 PATH를 넓히지 않고 Windows의 시스템 도구만 실행한다.
    root = os.environ.get('SystemRoot') or os.environ.get('WINDIR')
    if not root or not ntpath.isabs(root):
        raise OSError('Windows 시스템 경로를 확인할 수 없습니다')
    script = "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); "
    script += "$c=Get-CimInstance Win32_Processor; $m=Get-CimInstance Win32_ComputerSystem; @{cpu=($c.Name -join ' / '); cores=($c.NumberOfCores | Measure-Object -Sum).Sum; ram_bytes=$m.TotalPhysicalMemory; gpu=((Get-CimInstance Win32_VideoController).Name -join ' / ')} | ConvertTo-Json -Compress"
    return [ntpath.join(root, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
            '-NoProfile', '-NonInteractive', '-Command', script]


@lru_cache(maxsize=1)
def collect():
    result = dict(os=platform.system(), os_version=platform.release(), architecture=platform.machine(),
                  cpu=None, cores=None, threads=os.cpu_count(), ram_bytes=None, gpu=None)
    try:
        if platform.system() == 'Darwin':
            for key, field in [('cpu', 'machdep.cpu.brand_string'), ('cores', 'hw.physicalcpu'), ('ram_bytes', 'hw.memsize')]:
                value = command(['sysctl', '-n', field])
                result[key] = value if key == 'cpu' else int(value)
            displays = json.loads(command(['system_profiler', 'SPDisplaysDataType', '-json']))
            result['gpu'] = ' / '.join(str(v['sppci_model']) for v in displays.get('SPDisplaysDataType', []) if v.get('sppci_model')) or None
        elif platform.system() == 'Windows':
            values = json.loads(command(windows_command()))
            if not isinstance(values, dict):
                raise ValueError('장치 정보 형식을 확인할 수 없습니다')
            result.update({key: values.get(key) for key in ('cpu', 'cores', 'ram_bytes', 'gpu')})
    except (OSError, ValueError, subprocess.SubprocessError):
        pass  # 조회 불가 항목은 0으로 꾸미지 않는다.
    return result
