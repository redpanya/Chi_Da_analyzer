"""최종 ZIP의 서명·파일명과 실제 macOS 실행기를 별도로 검사한다."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unicodedata
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler


def verify_bundle(app):
    # 한글 화면 표시는 유지하되 봉인되는 경로는 정규화 차이가 없게 제한한다.
    for file in (app, *app.rglob('*')):
        if not file.name.isascii():
            raise ValueError(f'번들 파일명은 ASCII여야 합니다: {file.name}')
        if file.is_symlink() and not str(file.readlink()).isascii():
            raise ValueError(f'번들 링크 대상은 ASCII여야 합니다: {file.name}')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True, timeout=90)


def executable_is(pid, expected):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'comm='], capture_output=True, text=True, timeout=10)
    try:
        return bool(result.stdout.strip()) and Path(result.stdout.strip()).samefile(expected)
    except OSError:
        return False


def session_folders(root):
    return {p for p in root.iterdir() if p.is_dir() and
            unicodedata.normalize('NFC', p.name).startswith('실행-')} if root.exists() else set()


def launch(app, work):
    sessions = Path.home()/'Library/Application Support/치지직 보관함'
    before = session_folders(sessions)
    expected = app/'Contents/Resources/backend/archive-backend'
    launcher = app/'Contents/MacOS/ArchiveLauncher'
    library = work/'library'
    opener = subprocess.Popen(['open', '-n', '-W', str(app), '--args', '--no-browser', '--library', str(library)])
    child_pid = launcher_pid = None
    ready = None
    try:
        deadline = time.monotonic()+60
        while time.monotonic() < deadline:
            for folder in session_folders(sessions)-before:
                candidate = folder/'ready.json'
                try:
                    data = json.loads(candidate.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                if not executable_is(data['pid'], expected):
                    continue
                parent = int(subprocess.check_output(['ps', '-p', str(data['pid']), '-o', 'ppid=']))
                if not executable_is(parent, launcher):
                    continue
                child_pid, launcher_pid, ready = data['pid'], parent, candidate
                if urlsplit(data['url']).hostname != '127.0.0.1':
                    raise ValueError('실행기 주소가 로컬 주소가 아닙니다')
                http = build_opener(ProxyHandler({}))
                with http.open(data['url'], timeout=15) as response:
                    assert response.status == 200
                return {'launch_services': True, 'launcher_and_backend': True, 'http': True}
            if opener.poll() is not None:
                raise RuntimeError(f'앱이 준비 전에 종료됐습니다: {opener.returncode}')
            time.sleep(.2)
        raise RuntimeError('실제 앱 실행기 준비 시간 초과')
    finally:
        # 이번 임시 보관함을 연 프로세스만 정리한다. 기존 앱은 종료하지 않는다.
        stop_failed = False
        if child_pid and executable_is(child_pid, expected):
            try:
                os.kill(child_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic()+20
            while ready.exists() and time.monotonic() < deadline:
                time.sleep(.2)
            stop_failed = ready.exists()
        if not launcher_pid:
            listing = subprocess.check_output(['ps', '-axo', 'pid=,command='], text=True)
            for line in listing.splitlines():
                pid, _, args = line.strip().partition(' ')
                args = unicodedata.normalize('NFC', args.strip())
                if str(library) in args and executable_is(int(pid), launcher):
                    launcher_pid = int(pid)
        if launcher_pid and executable_is(launcher_pid, launcher):
            try:
                os.kill(launcher_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            opener.wait(timeout=20)
        except subprocess.TimeoutExpired:
            opener.terminate(); opener.wait(timeout=10)
        if stop_failed:
            raise RuntimeError('검사 앱 서버가 정상 종료되지 않았습니다')


def check_archive(archive):
    with tempfile.TemporaryDirectory(prefix='ChiDaanalyzer-check-') as folder:
        work = Path(folder).resolve()
        for method in ('ditto', 'unzip'):
            destination = work/method
            if method == 'ditto':
                args = ['ditto', '-x', '-k', str(archive), str(destination)]
            else:
                args = ['/usr/bin/unzip', '-q', str(archive), '-d', str(destination)]
            subprocess.run(args, check=True, timeout=90)
            verify_bundle(destination/'ChiDaanalyzer.app')
        app = work/'ditto/ChiDaanalyzer.app'
        opened = launch(app, work)
        policy = subprocess.run(['spctl', '--assess', '--type', 'execute', '--verbose=4', str(app)],
                                capture_output=True, text=True, timeout=60)
        return {'ascii_bundle_paths': True, 'zip_extractors': ['ditto', 'unzip'],
                'signature_after_extraction': True, 'app_startup': opened,
                'gatekeeper': {'accepted': policy.returncode == 0, 'returncode': policy.returncode,
                               'details': (policy.stdout+policy.stderr).replace(str(app), 'ChiDaanalyzer.app')},
                'notarized': False, 'downloaded_first_launch_verified': False}
