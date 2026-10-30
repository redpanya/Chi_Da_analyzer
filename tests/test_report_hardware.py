"""패키지의 제한된 PATH 및 비영문 Windows 출력 회귀 검사."""
import json
import subprocess
import unittest
from unittest.mock import patch

from archive import report_hardware


class HardwareTests(unittest.TestCase):
    def tearDown(self):
        report_hardware.collect.cache_clear()

    def test_windows_uses_system_path_and_utf8(self):
        values = dict(cpu='테스트 CPU', cores=4, ram_bytes=16*1024**3, gpu='그래픽 장치')
        with patch.dict('os.environ', {'SystemRoot': r'C:\Windows', 'PATH': r'C:\app\native'}, clear=True), \
             patch('archive.report_hardware.platform.system', return_value='Windows'), \
             patch('archive.report_hardware.subprocess.check_output', return_value=json.dumps(values, ensure_ascii=False).encode('utf-8-sig')) as run:
            result = report_hardware.collect()
        self.assertEqual({k: result[k] for k in values}, values)
        args = run.call_args.args[0]
        self.assertEqual(args[0], r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')
        self.assertIn('[Console]::OutputEncoding', args[-1])
        self.assertEqual(run.call_args.kwargs['timeout'], 12)
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_failed_lookup_is_unknown_without_private_fields(self):
        for failure in (OSError('missing'), subprocess.TimeoutExpired('powershell', 12)):
            report_hardware.collect.cache_clear()
            with patch.dict('os.environ', {'SystemRoot': r'C:\Windows'}), \
                 patch('archive.report_hardware.platform.system', return_value='Windows'), \
                 patch('archive.report_hardware.command', side_effect=failure):
                result = report_hardware.collect()
            self.assertIsNone(result['cpu'])
            self.assertIsNone(result['ram_bytes'])
            self.assertEqual(set(result), {'os','os_version','architecture','cpu','cores','threads','ram_bytes','gpu'})

    def test_invalid_json_shape_does_not_break_report(self):
        with patch.dict('os.environ', {'SystemRoot': r'C:\Windows'}), \
             patch('archive.report_hardware.platform.system', return_value='Windows'), \
             patch('archive.report_hardware.command', return_value='null'):
            self.assertIsNone(report_hardware.collect()['cpu'])

    def test_no_system_root_does_not_search_user_path(self):
        with patch.dict('os.environ', {'PATH': 'untrusted'}, clear=True):
            with self.assertRaises(OSError):
                report_hardware.windows_command()


if __name__ == '__main__':
    unittest.main()
