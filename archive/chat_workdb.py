"""외장 보관함과 분리된 채팅 대조용 임시 DB."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import sys
import tempfile


def temporary_root():
    if sys.platform == 'darwin':
        # TMPDIR이 외장 보관함을 가리켜도 macOS 시스템 임시 위치를 사용한다.
        return Path('/private/tmp')
    from .runtime import SUPPORT
    return SUPPORT/'temporary'


@contextmanager
def database():
    root = temporary_root()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='chida-chat-', dir=root) as folder:
        try:
            with closing(sqlite3.connect(Path(folder)/'counts.sqlite')) as db:
                yield db
        except sqlite3.Error as error:
            code = getattr(error, 'sqlite_errorcode', 0) & 255
            if code == sqlite3.SQLITE_FULL:
                raise ValueError('채팅 작업용 내장 임시 공간이 부족합니다. 공간을 확보한 뒤 다시 시도하세요. 받은 채팅과 기존 결과는 유지됩니다') from error
            if code in (sqlite3.SQLITE_READONLY, sqlite3.SQLITE_CANTOPEN):
                raise ValueError('채팅 작업용 내장 임시 DB를 쓰지 못했습니다. 임시 폴더 접근 상태를 확인한 뒤 다시 시도하세요. 받은 채팅과 기존 결과는 유지됩니다') from error
            raise
