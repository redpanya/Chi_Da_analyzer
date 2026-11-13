"""로컬 파일을 업로드하지 않는 OS 파일·폴더 선택창."""
import base64
import os
import subprocess
import sys
from . import processes


def choose(folder=False, kind=None):
    kind = kind or ('folder' if folder else 'video')
    if kind not in ('folder', 'video', 'image', 'file'):
        raise ValueError('선택할 파일 종류가 올바르지 않습니다')
    folder = kind == 'folder'
    label = {'folder': '폴더', 'video': '비디오 파일', 'image': 'PNG 이미지', 'file': '파일'}[kind]
    if sys.platform == 'darwin':
        target = 'folder' if folder else 'file'
        script = f'try\nreturn POSIX path of (choose {target} with prompt "치다 분석기: {label} 선택")\non error number -128\nreturn ""\nend try'
        args = ['/usr/bin/osascript', '-e', script]
    elif os.name == 'nt':
        script = 'Add-Type -AssemblyName System.Windows.Forms; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; '
        if folder:
            script += '$d=New-Object System.Windows.Forms.FolderBrowserDialog; if($d.ShowDialog() -eq "OK"){[Console]::Write($d.SelectedPath)}'
        else:
            filters = {'video': 'Video|*.mp4;*.m4v;*.mov;*.mkv;*.webm', 'image': 'PNG|*.png', 'file': 'Files|*.*'}
            script += '$d=New-Object System.Windows.Forms.OpenFileDialog; $d.Filter="'+filters[kind]+'"; if($d.ShowDialog() -eq "OK"){[Console]::Write($d.FileName)}'
        args = [os.path.join(os.environ['SystemRoot'], 'System32/WindowsPowerShell/v1.0/powershell.exe'),
                '-NoProfile', '-STA', '-EncodedCommand', base64.b64encode(script.encode('utf-16-le')).decode()]
    else:
        raise ValueError('파일·폴더 선택창은 macOS와 Windows에서 지원합니다')
    child = processes.popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = child.communicate(timeout=120)
        if child.returncode:
            raise ValueError('파일 선택창을 열지 못했습니다. 운영체제의 앱 실행 권한을 확인한 뒤 다시 선택하세요')
        return out.decode('utf-8-sig').strip()
    finally:
        if child.poll() is None:
            processes.stop(child)
