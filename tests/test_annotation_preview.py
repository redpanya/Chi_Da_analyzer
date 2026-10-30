"""개발 주석 모드가 배포 정책이나 다른 보안 경계를 완화하지 않는지 검사한다."""
from contextlib import redirect_stderr
from http.client import HTTPConnection
from io import StringIO
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import app
from archive import runtime
from archive.server import make_server
from archive.web_security import content_security_policy

STRICT = "default-src 'self'; media-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"


class AnnotationPreviewTests(unittest.TestCase):
    def test_policy_is_strict_by_default_and_style_only_when_requested(self):
        with patch.object(runtime, 'FROZEN', False):
            self.assertEqual(content_security_policy(), STRICT)
            self.assertEqual(content_security_policy(True), STRICT + "; style-src 'self' 'unsafe-inline'")
        with patch.object(runtime, 'FROZEN', True):
            self.assertEqual(content_security_policy(), STRICT)
            with self.assertRaisesRegex(ValueError, '패키지에서는 주석 호환'):
                content_security_policy(True)

    def test_packaged_server_rejects_preview_before_binding(self):
        with patch.object(runtime, 'FROZEN', True), patch('archive.server.GuiServer') as server:
            with self.assertRaisesRegex(ValueError, '패키지에서는 주석 호환'):
                make_server(None, annotation_preview=True)
            server.assert_not_called()

    def test_packaged_cli_rejects_preview_before_opening_a_library(self):
        error = StringIO()
        with patch.object(runtime, 'FROZEN', True), patch.object(runtime, 'configure'), \
             patch.object(runtime, 'library_default', return_value=Path('/unused')), \
             patch('sys.platform', 'darwin'), patch('sys.argv', ['app.py', '--annotation-preview', '--no-open']), \
             patch('archive.jobs.Manager') as manager, redirect_stderr(error):
            with self.assertRaises(SystemExit) as exit:
                app.main()
            self.assertEqual(exit.exception.code, 2)
            manager.assert_not_called()
        self.assertIn('패키지에서는 주석 호환', error.getvalue())

    def test_http_policy_config_and_access_controls(self):
        manager = SimpleNamespace(default_root='/test', folders=lambda: {})
        for frozen, preview in [(False, False), (False, True), (True, False)]:
            with self.subTest(frozen=frozen, preview=preview), patch.object(runtime, 'FROZEN', frozen):
                server, url = make_server(manager, annotation_preview=preview)
            self.assertEqual(server.server_address[0], '127.0.0.1')
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            parsed = urlsplit(url)
            client = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
            expected = STRICT + ("; style-src 'self' 'unsafe-inline'" if preview else '')
            try:
                for route in ['', 'app.js', 'style.css', 'api/config', 'clip-studio.html', 'clip-studio.css', 'clip-studio.js', 'clip-studio-model.js', 'analysis-scope-preview.js']:
                    client.request('GET', parsed.path + route)
                    response = client.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.getheader('Content-Security-Policy'), expected)
                    self.assertEqual(response.getheader('Referrer-Policy'), 'no-referrer')
                    self.assertEqual(response.getheader('X-Content-Type-Options'), 'nosniff')
                    data = response.read()
                    if route == 'api/config':
                        self.assertIs(json.loads(data)['annotation_preview'], preview)
                for headers in [{'Origin':'https://example.com'}, {'Host':'example.com'}]:
                    client.request('GET', parsed.path, headers=headers)
                    response = client.getresponse()
                    self.assertEqual(response.status, 403)
                    response.read()
                for path in ['/wrong-token/', parsed.path + 'archive/server.py']:
                    client.request('GET', path)
                    response = client.getresponse()
                    self.assertEqual(response.status, 404)
                    response.read()
            finally:
                client.close()
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
