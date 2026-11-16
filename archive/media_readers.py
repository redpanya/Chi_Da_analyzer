"""재생 또는 저장 응답이 보관함 파일을 사용 중인 동안만 추적한다."""
import socket
from contextlib import contextmanager
from threading import Condition

from .storage import Conflict


class MediaReaders:
    def __init__(self):
        self.changed = Condition()
        self.readers = {}
        self.draining = set()

    @contextmanager
    def open(self, path, connection):
        path = path.resolve()
        with self.changed:
            if any(root in path.parents for root in self.draining):
                raise Conflict('휴지통으로 이동 중인 영상입니다')
            stream = path.open('rb')
            self.readers[stream] = (path, connection)
        try:
            with stream:
                yield stream
        finally:
            with self.changed:
                self.readers.pop(stream)
                self.changed.notify_all()

    @contextmanager
    def drain(self, root):
        root = root.resolve()
        with self.changed:
            self.draining.add(root)
        try:
            with self.changed:
                for path, connection in self.readers.values():
                    if root in path.parents:
                        try:
                            connection.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                if not self.changed.wait_for(lambda: all(root not in p.parents for p, _ in self.readers.values()), timeout=5):
                    raise Conflict('열려 있는 재생 파일을 닫지 못했습니다. 잠시 후 다시 시도하세요')
            yield
        finally:
            with self.changed:
                self.draining.remove(root)
