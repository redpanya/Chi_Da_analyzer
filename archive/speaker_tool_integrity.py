"""공식 speaker-tools-v1 ZIP과 압축을 푼 실행 환경 전체의 SHA-256."""
import hashlib
import errno
import shutil
import unicodedata
import os
import stat
from pathlib import Path


# (배포 ZIP, 정렬된 상대 파일 이름과 개별 SHA-256으로 계산한 지문)
PINS = {
    ('macOS-arm64', 'sherpa'): ('f880eca0ec04894d9e33261d04bb0f57a7ae5e2c2ed0ec77a7dfb6e29b061c95', 'a362361e4894d0b08e97f6abf3e6d49644ee29ae9d2a884ef6efc67a56842bad'),
    ('macOS-arm64', 'pyannote'): ('2ff4ae06bbdf0a92763c46f85626db0793ba8036dd2c9cf130de6839ab22c865', '5c298946b88c45892e389418fa91818a9258fe59f8ba876d1ebe3d853721b59e'),
    ('macOS-arm64', 'fluid'): ('daa23085d5a69b85e12abd95235296bd9a20828818a8fb4ccb93ee7a97471f0b', 'cc1e356cb45aa33ebb5f1ba0b1c702a3eaff901da71df839cb0d5c1f247e8abf'),
    ('Windows-x64', 'sherpa'): ('80074677ddf02f8af07b5a23352e6498662fb6bafc5ba20226d7de8f261bee93', '51777c4105e3164be79965c17996a52754b509a200ee461fafc1adeea56dd27e'),
    ('Windows-x64', 'pyannote'): ('0b6a5367bd203c203365064e59ae7d7f47c0433805c841bd5c328c9562fc169b', '20f9dffdebe78329cd0055d3cecf46440b046909cecac10fe2585b23dc258da6'),
}


def plain(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError('실행 도구 경로의 연결 파일이나 폴더는 사용할 수 없습니다')


def safe_path(path):
    for p in (*reversed(path.parents), path):
        plain(p)


def verify_tree(folder, expected, stop):
    from .source import check_cancel
    def fail(error):
        raise error
    safe_path(folder)
    files = []
    for base, dirs, names in os.walk(folder, onerror=fail):
        check_cancel(stop)
        for name in dirs:
            plain(Path(base)/name)
        for name in names:
            p = Path(base)/name
            plain(p)
            if not p.is_file():
                raise ValueError('실행 도구 폴더에는 일반 파일만 사용할 수 있습니다')
            # exFAT의 macOS 메타데이터는 공식 ZIP에 없고 실행 코드도 아니다.
            # 이름만 보고 건너뛰지 않고 서식과 대응하는 원본 이름을 함께 확인한다.
            if name.startswith('._') and len(name) > 2 and p.with_name(name[2:]).exists():
                with p.open('rb') as sidecar:
                    if sidecar.read(8) == bytes.fromhex('0005160700020000'): continue
            if name == '.DS_Store':
                with p.open('rb') as finder:
                    if finder.read(8) == b'\x00\x00\x00\x01Bud1': continue
            files.append(p.relative_to(folder).as_posix())
    digest = hashlib.sha256()
    entries = sorted((unicodedata.normalize('NFC', name), name) for name in files)
    if len({key for key, _ in entries}) != len(entries):
        raise ValueError('실행 도구 안에 같은 이름으로 정규화되는 파일이 있습니다')
    for key, name in entries:
        entry = hashlib.sha256()
        with (folder/name).open('rb') as file:
            while block := file.read(1024 * 1024):
                check_cancel(stop)
                entry.update(block)
        digest.update(key.encode('utf-8') + b'\0' + entry.digest())
    if digest.hexdigest() != expected:
        raise ValueError('실행 도구의 파일 지문이 공식 배포본과 다릅니다. 실행 도구를 다시 설치하세요')


def remove_tree(folder):
    """일반 파일 삭제 뒤 남은 macOS 외장 드라이브 메타데이터까지 정리한다."""
    safe_path(folder)
    try:
        shutil.rmtree(folder)
        return
    except OSError as error:
        if error.errno != errno.ENOTEMPTY: raise
    # 일부 exFAT 드라이버는 디렉터리 FD로 열거하고 삭제할 때 파일을 건너뛴다.
    # 절대 경로로 스냅샷을 만들고 연결 디렉터리나 재분석 지점은 따라가지 않는다.
    def remove(path, directory=False):
        try:
            path.rmdir() if directory else path.unlink()
        except FileNotFoundError:
            # macOS exFAT는 NFD 이름으로 읽을 수 있지만 삭제에는 NFC 이름이 필요하다.
            nfc = path.with_name(unicodedata.normalize('NFC', path.name))
            if nfc != path:
                if directory: nfc.rmdir()
                else: nfc.unlink(missing_ok=True)

    def clear(path):
        for child in list(path.iterdir()):
            try:
                info = child.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISDIR(info.st_mode):
                plain(child)
                clear(child)
            else:
                remove(child)
        remove(path, directory=True)
    clear(folder)
