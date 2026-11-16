"""포터블 앱이 종료된 뒤 검증된 프로그램 폴더만 교체한다."""
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import zipfile


APP = 'ChiDaanalyzer'
INVENTORY = 'chida-package.json'
IMAGE = APP + '.exe'
MAX_BYTES = 12 * 1024 ** 3
RESERVED = re.compile(r'^(?:con|prn|aux|nul|conin\$|conout\$|(?:com|lpt)[1-9¹²³])(?:\.|$)', re.I)
VERSION = re.compile(r'(?:0|[1-9]\d{0,5})(?:\.(?:0|[1-9]\d{0,5})){2}')
TOKEN = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def relative_name(text):
    if not isinstance(text, str) or not text or '\\' in text:
        raise ValueError('패키지 경로 형식이 올바르지 않습니다.')
    parts = text.split('/')
    for part in parts:
        if (not part or part.endswith(('.', ' ')) or RESERVED.match(part)
                or re.search(r'[\x00-\x1f:<>"|?*]', part)):
            raise ValueError('패키지에 사용할 수 없는 경로가 있습니다.')
    return PurePosixPath(*parts)


def read_plan(config):
    work = config.parent.resolve(strict=True)
    plan = json.loads(config.read_text(encoding='utf-8'))
    if plan.get('app') != APP or not work.name.startswith('.chida-update-'):
        raise ValueError('업데이트 작업 폴더를 확인하세요.')
    target = Path(plan['target'])
    if (not target.is_absolute() or target.parent.resolve(strict=True) != work.parent or target in (work, work.parent)
            or not VERSION.fullmatch(plan['version']) or not VERSION.fullmatch(plan['previousVersion'])
            or not TOKEN.fullmatch(plan['token']) or not re.fullmatch('[a-f0-9]{64}', plan['sha256'])
            or not 0 < plan['size'] <= MAX_BYTES or plan['pid'] < 1):
        raise ValueError('업데이트 작업 정보를 확인하세요.')
    return work, target, plan


def reparse(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def inspect_install(root, version):
    if reparse(root) or reparse(root / INVENTORY):
        raise ValueError('연결된 앱 폴더에서는 자동 교체할 수 없습니다.')
    if (root / INVENTORY).stat().st_size > 8 * 1024 ** 2:
        raise ValueError('프로그램 파일 목록이 너무 큽니다.')
    inventory = json.loads((root / INVENTORY).read_text(encoding='utf-8'))
    if inventory.get('app') != APP or inventory.get('version') != version or not isinstance(inventory.get('files'), list):
        raise ValueError('이 앱의 포터블 프로그램 폴더를 확인할 수 없습니다.')
    files = {relative_name(name).as_posix().casefold() for name in inventory['files']}
    if len(files) != len(inventory['files']) or IMAGE.casefold() not in files or INVENTORY in files:
        raise ValueError('프로그램 파일 목록과 실행 파일을 확인하세요.')
    files.add(INVENTORY)
    dirs = {str(parent) for name in files for parent in PurePosixPath(name).parents}
    declared_dirs = inventory.get('directories', [])
    if not isinstance(declared_dirs, list):
        raise ValueError('프로그램 폴더 목록의 형식이 올바르지 않습니다.')
    for name in declared_dirs:
        dirs.add(relative_name(name).as_posix().casefold())
    present = set()
    for current, folders, names in os.walk(root, onerror=raise_error):
        for name in folders:
            child = Path(current) / name
            rel = child.relative_to(root).as_posix().casefold()
            if reparse(child) or rel not in dirs:
                raise ValueError('프로그램 외의 파일이나 폴더가 있어 자동 교체를 멈췄습니다: ' + name)
        for name in names:
            child = Path(current) / name
            rel = child.relative_to(root).as_posix().casefold()
            if reparse(child) or rel not in files or rel in present or not child.is_file():
                raise ValueError('등록하지 않은 파일이 있어 자동 교체를 멈췄습니다: ' + name)
            present.add(rel)
    if present != files:
        raise ValueError('기존 프로그램 파일 목록과 실제 폴더 내용이 다릅니다.')


def raise_error(error):
    raise error


def save_json(file, data):
    tmp = file.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(file)


def extract_verified(archive, workspace, plan):
    with archive.open('rb') as source:
        if source.seek(0, os.SEEK_END) != plan['size']:
            raise ValueError('ZIP 파일 크기가 일치하지 않습니다.')
        source.seek(0)
        if hashlib.file_digest(source, 'sha256').hexdigest() != plan['sha256']:
            raise ValueError('저장한 ZIP이 변경됐습니다. 다시 다운로드하세요.')
        source.seek(0)
        with zipfile.ZipFile(source) as package:
            entries = package.infolist()
            total = sum(e.file_size for e in entries)
            if not 0 < len(entries) <= 50000 or total > MAX_BYTES or shutil.disk_usage(workspace).free < total + 16 * 1024 ** 2:
                raise ValueError('패키지의 파일 수 또는 사용 가능한 디스크 공간을 확인하세요.')
            output = workspace / 'new'
            output.mkdir()
            seen, spellings = set(), {}
            for entry in entries:
                path = relative_name(entry.orig_filename[:-1] if entry.is_dir() else entry.orig_filename)
                key = str(path).casefold()
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if (path.parts[0] != APP or (len(path.parts) == 1 and not entry.is_dir()) or key in seen
                        or mode not in (0, stat.S_IFDIR, stat.S_IFREG) or entry.external_attr & 0x400):
                    raise ValueError('ZIP 안에 중복 경로나 허용되지 않은 파일이 있습니다.')
                seen.add(key)
                for parent in [path, *path.parents]:
                    full = parent.as_posix()
                    if spellings.setdefault(full.casefold(), full) != full:
                        raise ValueError('대소문자만 다른 경로가 겹칩니다.')
                dest = output.joinpath(*path.parts[1:])
                if entry.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(entry) as reader, dest.open('xb') as writer:
                        shutil.copyfileobj(reader, writer, length=1024 * 1024)
    inspect_install(output, plan['version'])


def prepare(work, target, plan):
    inspect_install(target, plan['previousVersion'])
    extract_verified(Path(plan['archive']), work, plan)
    save_json(work / 'step.json', {'phase':'prepared'})


def wait_for_parent(pid):
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return
        raise OSError('기존 앱 종료 여부를 확인할 수 없습니다.')
    try:
        if kernel.WaitForSingleObject(handle, 180000) != 0:
            raise OSError('기존 앱 종료를 기다리다 업데이트를 중지했습니다.')
    finally:
        kernel.CloseHandle(handle)


def rename_dir(source, dest):
    end = time.monotonic() + 8
    while True:
        try:
            source.rename(dest)
            return
        except OSError:
            if time.monotonic() >= end:
                raise
            time.sleep(.3)


def launch(target, env=None):
    env = {key:value for key,value in (env if env is not None else os.environ).items()
           if not key.startswith('_PYI_') and key != '_MEIPASS2'}
    if sys.platform == 'win32' and getattr(sys,'frozen',False):
        # 일회성 도구의 임시 DLL 검색 경로가 새 Electron 앱으로 이어지지 않게 한다.
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    return subprocess.Popen([str(target / IMAGE)], cwd=target, env=env)


def launch_checked(target, plan):
    env = dict(os.environ, CHIDA_UPDATE_ATTEMPT=plan['token'], CHIDA_UPDATE_VERSION=plan['version'])
    ready = Path(plan['updateRoot']) / (plan['token'] + '.ready')
    child = launch(target, env)
    end = time.monotonic() + 120
    while time.monotonic() < end:
        if ready.is_file() and ready.read_text(encoding='utf-8') == plan['version']:
            ready.unlink(missing_ok=True)
            return
        if child.poll() is not None:
            break
        time.sleep(.25)
    if child.poll() is None:
        # 이 교체 작업에서 시작한 프로세스 트리만 종료한다.
        subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/taskkill.exe'),
                        '/PID', str(child.pid), '/T', '/F'], timeout=20, capture_output=True)
        child.wait(timeout=20)
    raise OSError('새 앱과 처리 서버의 시작을 확인하지 못했습니다.')


def recover(work, target, plan):
    previous = work / 'previous'
    if not previous.is_dir():
        raise ValueError('복구할 이전 프로그램이 없습니다.')
    inspect_install(previous, plan['previousVersion'])
    if target.exists():
        inspect_install(target, plan['version'])
        rename_dir(target, work / 'failed')
    rename_dir(previous, target)
    save_json(work / 'step.json', {'phase':'restored'})
    record_result(work, plan, '새 버전 적용을 마치지 못해 이전 버전으로 돌아왔습니다.')
    launch(target)


def replace(work, target, plan, *, wait=wait_for_parent, check=launch_checked):
    wait(plan['pid'])
    if (work / 'cancel').exists():
        return
    try:
        inspect_install(target, plan['previousVersion'])
        inspect_install(work / 'new', plan['version'])
        save_json(work / 'step.json', {'phase':'moving'})
        rename_dir(target, work / 'previous')
    except Exception:
        record_result(work, plan, '업데이트를 적용하지 못해 기존 프로그램을 다시 열었습니다.')
        launch(target)
        raise
    try:
        rename_dir(work / 'new', target)
        save_json(work / 'step.json', {'phase':'starting'})
        check(target, plan)
    except Exception:
        recover(work, target, plan)
        raise
    save_json(work / 'step.json', {'phase':'complete'})
    # 기동 확인 이후에도 보관 폴더에 사용자가 추가한 파일은 삭제하지 않는다.
    inspect_install(work / 'previous', plan['previousVersion'])
    shutil.rmtree(work / 'previous')
    archive = Path(plan['archive'])
    if archive.parent == Path(plan['updateRoot']) / 'downloads':
        archive.unlink(missing_ok=True)


def record_result(work, plan, message):
    save_json(Path(plan['updateRoot']) / 'last-result.json',
              {'message':message,'folder':str(work),'token':plan['token']})


def main(argv):
    if not argv:
        command = 'recover'
        config = Path(sys.executable).parent / 'plan.json'
    else:
        command, config = argv
        config = Path(config)
    work, target, plan = read_plan(config)
    message = ''
    try:
        if command == 'prepare':
            prepare(work, target, plan)
        elif command == 'replace':
            replace(work, target, plan)
            message = '새 버전으로 업데이트했습니다.'
        elif command == 'recover':
            recover(work, target, plan)
            message = '이전 프로그램을 복구했습니다.'
        else:
            raise ValueError('알 수 없는 업데이트 단계입니다.')
    except Exception as error:
        message = str(error)
        (work / 'error.txt').write_text(message, encoding='utf-8')
        raise
    finally:
        if command in ('replace','recover'):
            record_result(work, plan, message)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        # 결과는 main에서 기록한다. 무인 교체 실패 시 콘솔 없는 실행기를 종료한다.
        sys.exit(1)
