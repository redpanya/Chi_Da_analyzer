"""앱이 강제 종료돼도 상주 추론 서버와 보관함 잠금을 정리한다."""
import json
import os
import signal
import subprocess
import sys
import threading
from archive import processes

def main():
    request=json.load(sys.stdin);stop=threading.Event();child=None
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
    try:
        if os.getppid()!=request['parent']:return
        child=processes.popen(request['args'],stdin=subprocess.DEVNULL,lock_fd=processes.adopt_lock(request['lock_fd']))
        while child.poll() is None:
            if stop.wait(.25) or os.getppid()!=request['parent']:break
    finally:
        if child and child.poll() is None:
            processes.stop(child)

