"""출력 볼륨 제한을 확인한다. 디스크 설정은 변경하지 않는다."""
import os
import plistlib
import subprocess
import sys
from . import processes


def filesystem(folder):
    if os.name == 'nt':
        import ctypes
        root = ctypes.create_unicode_buffer(32768)
        kind = ctypes.create_unicode_buffer(256)
        api = ctypes.windll.kernel32
        if not api.GetVolumePathNameW(str(folder), root, len(root)):
            return ''
        if not api.GetVolumeInformationW(root.value, None, 0, None, None, None, kind, len(kind)):
            return ''
        return kind.value.lower()
    if sys.platform == 'darwin':
        child = None
        try:
            child = processes.popen(['/bin/df', '-P', str(folder)],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            rows, _ = child.communicate(timeout=5)
            if child.returncode or len(rows.splitlines()) < 2:
                return ''
            device = rows.splitlines()[-1].split()[0].decode('utf-8')
            if not device.startswith('/dev/'):
                return ''
            child = processes.popen(['/usr/sbin/diskutil', 'info', '-plist', device],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            data, _ = child.communicate(timeout=5)
            if child.returncode == 0:
                value = plistlib.loads(data)
                return str(value.get('FilesystemName', value.get('FilesystemType', ''))).lower()
        except (OSError, ValueError, subprocess.TimeoutExpired, plistlib.InvalidFileException):
            pass
        finally:
            if child and child.poll() is None:
                processes.stop(child)
    return ''


def check_volume(folder, source_bytes):
    kind = filesystem(folder)
    if 'fat' in kind and 'exfat' not in kind:
        # 가변 비트레이트는 길이 비례 크기를 보장하지 않는다. 큰 원본은 보수적으로 막는다.
        if source_bytes*1.05 + 16*1024**2 >= 2**32-1:
            raise ValueError('FAT32 계열은 파일당 4GB 제한이 있습니다. 이 큰 영상은 exFAT·APFS·NTFS 폴더에 저장하세요')
    return kind or '확인 불가'
