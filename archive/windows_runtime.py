"""Windows 잠금 핸들과 앱 종료 시 자식 프로세스 정리."""
import ctypes
from ctypes import wintypes as w
import msvcrt
import os

k = ctypes.WinDLL('kernel32', use_last_error=True)
k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
k.CreateFileW.restype = w.HANDLE
k.CloseHandle.argtypes = [w.HANDLE]
k.CreateJobObjectW.argtypes = [w.LPVOID, w.LPCWSTR]
k.CreateJobObjectW.restype = w.HANDLE
k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
k.GetCurrentProcess.restype = w.HANDLE


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                ('flags', w.DWORD), ('min_working', ctypes.c_size_t), ('max_working', ctypes.c_size_t),
                ('active', w.DWORD), ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]


class IOCounts(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IOCounts), ('process_memory', ctypes.c_size_t),
                ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]


_job = None


def protect_process_tree():
    """현재 앱과 이후 자식을 묶는다. 핸들은 자식에게 상속하지 않는다."""
    global _job
    if _job is not None:
        return
    handle = k.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not k.AssignProcessToJobObject(handle, k.GetCurrentProcess()):
        error = ctypes.get_last_error()
        k.CloseHandle(handle)
        raise ctypes.WinError(error)
    _job = handle


def exclusive_file(path):
    if path.exists() and path.lstat().st_file_attributes & 0x400:
        raise ValueError('연결된 잠금 파일은 사용할 수 없습니다')
    # 쓰기 핸들은 계속 배타적으로 유지하되, 휴지통 이동의 읽기 접근은 허용한다.
    handle = k.CreateFileW(str(path), 0xC0000000, 5, None, 4, 0x80, None)
    if handle == w.HANDLE(-1).value:
        error = ctypes.get_last_error()
        if error in (32, 33):
            raise BlockingIOError('이미 사용 중인 폴더입니다')
        raise ctypes.WinError(error)
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
    except BaseException:
        k.CloseHandle(handle)
        raise
