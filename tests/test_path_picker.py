"""네이티브 선택창 명령과 취소·실패를 실제 창을 띄우지 않고 확인한다."""
import base64
import subprocess
import unittest
from unittest.mock import Mock, patch

from archive import split_picker


class PathPicker(unittest.TestCase):
    def child(self, output=b'', code=0):
        child = Mock(returncode=code)
        child.communicate.return_value = (output, b'')
        child.poll.return_value = code
        return child

    def test_mac_folder_and_cancel(self):
        child = self.child('/Volumes/외장 디스크/모델\n'.encode())
        with patch.object(split_picker.sys, 'platform', 'darwin'), patch.object(split_picker.processes, 'popen', return_value=child) as run:
            self.assertEqual(split_picker.choose(kind='folder'), '/Volumes/외장 디스크/모델')
            self.assertIn('choose folder', run.call_args.args[0][-1])
            self.assertEqual(run.call_args.args[0][0], '/usr/bin/osascript')
            child.communicate.return_value = (b'\n', b'')
            self.assertEqual(split_picker.choose(kind='video'), '')
            self.assertIn('choose file', run.call_args.args[0][-1])

    def test_windows_file_and_folder(self):
        child = self.child(b'\xef\xbb\xbfC:\\Videos\\sample.mp4')
        with patch.object(split_picker.sys, 'platform', 'win32'), patch.object(split_picker.os, 'name', 'nt'), patch.dict(split_picker.os.environ, {'SystemRoot': 'C:\\Windows'}), patch.object(split_picker.processes, 'popen', return_value=child) as run:
            self.assertEqual(split_picker.choose(kind='video'), 'C:\\Videos\\sample.mp4')
            args = run.call_args.args[0]
            self.assertIn('-STA', args)
            self.assertIn('-NoProfile', args)
            command = base64.b64decode(args[-1]).decode('utf-16-le')
            self.assertIn('OpenFileDialog', command)
            self.assertIn('*.mp4;*.m4v;*.mov;*.mkv;*.webm', command)
            split_picker.choose(kind='folder')
            command = base64.b64decode(run.call_args.args[0][-1]).decode('utf-16-le')
            self.assertIn('FolderBrowserDialog', command)

    def test_invalid_kind_never_runs_process(self):
        with patch.object(split_picker.processes, 'popen') as run:
            with self.assertRaisesRegex(ValueError, '종류'):
                split_picker.choose(kind='folder; echo test')
            run.assert_not_called()

    def test_failed_dialog_and_timeout(self):
        child = self.child(code=1)
        with patch.object(split_picker.sys, 'platform', 'darwin'), patch.object(split_picker.processes, 'popen', return_value=child), patch.object(split_picker.processes, 'stop') as stop:
            with self.assertRaisesRegex(ValueError, '선택창'):
                split_picker.choose()
            stop.assert_not_called()
            child.communicate.side_effect = subprocess.TimeoutExpired('picker', 120)
            child.poll.return_value = None
            with self.assertRaises(subprocess.TimeoutExpired):
                split_picker.choose()
            stop.assert_called_once_with(child)


if __name__ == '__main__':
    unittest.main()
