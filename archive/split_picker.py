"""큰 파일을 업로드하지 않는 OS 선택창. 경로 입력도 항상 제공한다."""
import base64
import os
import subprocess
import sys
from . import processes


def choose(folder=False):
    if sys.platform == 'darwin':
        kind = 'folder' if folder else 'file'
        script = f'try\nreturn POSIX path of (choose {kind} with prompt "영상 나누기: {"저장 폴더" if folder else "MP4 파일"} 선택")\non error number -128\nreturn ""\nend try'
        args = ['/usr/bin/osascript', '-e', script]
    elif os.name == 'nt':
        script = 'Add-Type -AssemblyName System.Windows.Forms; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; '
        if folder:
            script += '$d=New-Object System.Windows.Forms.FolderBrowserDialog; if($d.ShowDialog() -eq "OK"){[Console]::Write($d.SelectedPath)}'
        else:
            script += '$d=New-Object System.Windows.Forms.OpenFileDialog; $d.Filter="MP4|*.mp4"; if($d.ShowDialog() -eq "OK"){[Console]::Write($d.FileName)}'
        args = [os.path.join(os.environ['SystemRoot'], 'System32/WindowsPowerShell/v1.0/powershell.exe'),
                '-NoProfile', '-STA', '-EncodedCommand', base64.b64encode(script.encode('utf-16-le')).decode()]
    else:
        raise ValueError('이 환경에서는 아래에 전체 경로를 입력하세요')
    child = processes.popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = child.communicate(timeout=120)
        if child.returncode:
            raise ValueError('파일 선택창을 열지 못했습니다. 전체 경로를 입력하세요')
        return out.decode('utf-8-sig').strip()
    finally:
        if child.poll() is None:
            processes.stop(child)
