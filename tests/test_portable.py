"""실제 OS에서 잠금 상속·종료와 한글 자료 보존을 검사한다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from archive import processes
from archive.storage import ProjectLock, Conflict, save_json, read_json

ROOT=Path(__file__).resolve().parents[1]


class PortableTests(unittest.TestCase):
    def test_state_replace_waits_for_short_lived_reader(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'state.json';save_json(file,{'value':'이전'})
            reader=file.open('rb')
            release=threading.Timer(.15,reader.close);release.start()
            try:
                save_json(file,{'value':'새 상태'})
                self.assertEqual(read_json(file),{'value':'새 상태'})
            finally:
                release.join();reader.close()

    def test_unicode_atomic_json_and_exclusive_lock(self):
        with tempfile.TemporaryDirectory(prefix='치 다 ') as temp:
            root=Path(temp)
            with ProjectLock(root):
                save_json(root/'자료.json',{'text':'원본·수동 교정 보존'})
                with self.assertRaises(Conflict):ProjectLock(root)
            self.assertEqual(read_json(root/'자료.json')['text'],'원본·수동 교정 보존')
            with ProjectLock(root):pass

    def test_lock_outlives_parent_handle(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);lock=ProjectLock(root)
            child=processes.popen([sys.executable,'-c','import sys,time; print("ready",flush=True);sys.stdin.read()'],
                                   lock_fd=lock.fd,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
            try:
                self.assertEqual(child.stdout.readline().strip(),b'ready');lock.close()
                with self.assertRaises(Conflict):ProjectLock(root)
                child.stdin.close();child.wait(timeout=10)
                with ProjectLock(root):pass
            finally:
                lock.close();processes.stop(child);child.stdout.close()

    def test_moving_retains_exclusion_and_recovers_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'project'
            code=('from pathlib import Path; from archive.storage import ProjectLock,Conflict; import sys; '
                  '\ntry: ProjectLock(Path(sys.argv[1]))\nexcept Conflict: sys.exit(19)\n')
            with ProjectLock(root) as lock:
                with self.assertRaisesRegex(OSError,'이동 실패'),lock.moving():
                    child=subprocess.run([sys.executable,'-c',code,str(root)],cwd=ROOT,timeout=10)
                    self.assertEqual(child.returncode,19)
                    raise OSError('이동 실패')
                self.assertIsNotNone(lock.fd)
                with self.assertRaises(Conflict):ProjectLock(root)
                with lock.moving():root.rename(Path(temp)/'moved')
                self.assertFalse(root.exists())

    @unittest.skipUnless(os.name=='nt','Windows Job Object 전용')
    def test_parent_crash_terminates_grandchild(self):
        import ctypes
        from ctypes import wintypes as w
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
        kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
        kernel.CloseHandle.argtypes=[w.HANDLE]
        code=('from archive.windows_runtime import protect_process_tree; protect_process_tree(); '
              'import subprocess,sys; p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]); '
              'print(p.pid,flush=True);sys.stdin.read()')
        parent=subprocess.Popen([sys.executable,'-c',code],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        handle=None
        try:
            pid=int(parent.stdout.readline());handle=kernel.OpenProcess(0x100000,False,pid)
            self.assertTrue(handle);parent.kill();parent.wait(timeout=10)
            self.assertEqual(kernel.WaitForSingleObject(handle,10000),0)
        finally:
            if parent.poll() is None:parent.kill();parent.wait()
            parent.stdin.close();parent.stdout.close()
            if handle:kernel.CloseHandle(handle)

    def test_app_start_and_graceful_stop(self):
        with tempfile.TemporaryDirectory(prefix='치 다 ') as temp:
            root=Path(temp);ready=root/'ready.json';stop=root/'stop'
            child=subprocess.Popen([sys.executable,str(ROOT/'app.py'),'--no-open','--library',str(root/'보관함'),
                                    '--ready-file',str(ready),'--stop-file',str(stop)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                for _ in range(1200):
                    if ready.exists() or child.poll() is not None:break
                    time.sleep(.05)
                self.assertTrue(ready.exists(),child.stderr.read().decode('utf-8','replace') if child.poll() is not None else '준비 지연')
                value=read_json(ready);self.assertEqual(value['pid'],child.pid)
                stop.touch();self.assertEqual(child.wait(timeout=15),0);self.assertFalse(ready.exists())
            finally:
                processes.stop(child);child.stdout.close();child.stderr.close()


if __name__=='__main__':unittest.main()
