"""운영체제별 잠금 상속과 취소. 실행 중 자료의 중복 쓰기를 방지한다."""
import os
import subprocess
import threading

_spawn_lock = threading.Lock()


def inherited_lock(fd):
    if os.name == 'nt':
        import msvcrt
        return msvcrt.get_osfhandle(fd)
    return fd


def adopt_lock(value):
    if os.name == 'nt':
        import msvcrt
        return msvcrt.open_osfhandle(value, os.O_RDWR | os.O_BINARY)
    return value


def popen(args, *, lock_fd=None, **kwargs):
    if os.name != 'nt':
        if lock_fd is not None:
            kwargs['pass_fds'] = (lock_fd,)
        return subprocess.Popen(args, **kwargs)
    kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW
    if lock_fd is None:
        return subprocess.Popen(args, **kwargs)
    handle = inherited_lock(lock_fd)
    startup = subprocess.STARTUPINFO()
    startup.lpAttributeList = {'handle_list': [handle]}
    with _spawn_lock:
        previous = os.get_handle_inheritable(handle)
        os.set_handle_inheritable(handle, True)
        try:
            return subprocess.Popen(args, startupinfo=startup, close_fds=True, **kwargs)
        finally:
            os.set_handle_inheritable(handle, previous)


def stop(child, timeout=5):
    if child.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run([os.path.join(os.environ['SystemRoot'], 'System32', 'taskkill.exe'),
                        '/PID', str(child.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
    else:
        child.terminate()
    try:
        child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)
