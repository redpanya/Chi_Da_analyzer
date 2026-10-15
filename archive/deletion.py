"""선택한 VOD 전용 폴더만 운영체제 휴지통으로 이동한다."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from .storage import load_project, Conflict


def preview(path, vod):
    data = load_project(path, vod)
    rows, size = [], 0
    for folder, dirs, files in os.walk(path, followlinks=False):
        for name in sorted(dirs + files):
            file = Path(folder)/name
            stat = file.lstat()
            rows.append([str(file.relative_to(path)), stat.st_ino, stat.st_size, stat.st_mtime_ns])
            if file.is_file() and not file.is_symlink(): size += stat.st_size
    stat = path.stat()
    token = hashlib.sha256(json.dumps([str(path), stat.st_dev, stat.st_ino, sorted(rows)]).encode()).hexdigest()
    return {'vod_id': vod, 'title': data['metadata']['title'], 'path': str(path), 'bytes': size,
            'entries': len(rows), 'token': token}


def trash(path, vod, token, confirmation):
    value = preview(path, vod)
    if confirmation != vod or token != value['token']:
        raise Conflict('확인한 VOD 또는 자료가 바뀌었습니다. 삭제 내용을 다시 확인하세요')
    if os.name == 'nt':
        from send2trash import send2trash
        send2trash(str(path))
        if path.exists(): raise OSError('휴지통으로 이동하지 못했습니다')
        return {'trashed_to': 'Windows 휴지통'}
    helper = (Path(sys._MEIPASS)/'bin/vod-trash' if getattr(sys, 'frozen', False)
              else Path(__file__).resolve().parent.parent/'packaging/bin/vod-trash')
    if not helper.is_file(): raise ValueError('macOS 휴지통 도구가 없습니다. 설치 앱을 다시 설치하세요')
    result = subprocess.run([str(helper), str(path)], capture_output=True, text=True)
    if result.returncode or path.exists():
        raise OSError('휴지통으로 이동하지 못했습니다. 폴더 권한·볼륨 연결과 휴지통을 확인하세요')
    return json.loads(result.stdout)
