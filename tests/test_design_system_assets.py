"""로컬 디자인 자산의 의존 경로·고지·색상 계약 확인."""
import hashlib
import json
import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / 'web'
VENDOR = WEB / 'vendor' / 'webawesome'

class DesignSystemAssetsTests(unittest.TestCase):
    def test_vendor_hashes_and_relative_dependency_graph(self):
        manifest = json.loads((VENDOR / 'manifest.json').read_text())
        self.assertEqual(manifest['version'], '3.14.0')
        for entry in manifest['files']:
            path = VENDOR / entry['path']
            data = path.read_bytes()
            self.assertEqual(len(data), entry['bytes'], entry['path'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'], entry['path'])
            if path.suffix not in ('.css', '.js'):
                continue
            for relative in re.findall(r'''["']((?:\./|\.\./)[^"']+\.(?:js|css))["']''', data.decode()):
                resolved = (path.parent / relative).resolve()
                self.assertTrue(resolved.is_relative_to(VENDOR.resolve()))
                self.assertTrue(resolved.is_file(), (path, relative))
        for name in ('LICENSE.md', 'LICENSE-LIT.txt', 'LICENSE-FONTAWESOME.txt'):
            self.assertTrue((VENDOR / name).stat().st_size > 500)

    def test_no_remote_entrypoints_and_media_filter(self):
        module = (WEB / 'design-system.js').read_text()
        self.assertNotRegex(module, r'(?:import|fetch)\s*\(?["\']https?://')
        self.assertIn('setIconPath(new URL(', module)
        css = (WEB / 'design-system.css').read_text()
        self.assertNotRegex(css, r'(?i)(?:filter\s*:|url\s*\()')
        self.assertNotRegex(css, r'@media\s*\([^)]*(?:min|max)-width')

    def test_common_text_palette_contrast(self):
        def luminance(value):
            rgb = [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]
            linear = [c / 12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in rgb]
            return sum(a*b for a,b in zip(linear, (.2126,.7152,.0722)))
        css = (WEB / 'design-system.css').read_text()
        blocks = css.split(':root[data-theme=light]')[0].split(':root[data-theme=dark]')
        for block in blocks:
            tokens = dict(re.findall(r'--ds-([a-z-]+):\s*(#[a-fA-F0-9]{6})\s*;', block))
            for foreground,background in [('text','surface'),('muted','surface'),('text','surface-soft'),('muted','surface-soft'),('accent','tint'),('accent','selected'),('on-accent','accent-fill'),('on-accent','accent-strong'),('danger','danger-bg'),('warning','warning-bg'),('success','success-bg'),('on-success','success-fill'),('text','input'),('muted','input'),('secondary-text','secondary'),('info','info-bg'),('vod','vod-bg'),('on-danger','danger-fill'),('on-warning','warning-fill'),('on-info','info-fill'),('on-vod','vod-fill')]:
                a,b = sorted((luminance(tokens[foreground]),luminance(tokens[background])))
                self.assertGreaterEqual((b+.05)/(a+.05),4.5,(foreground,background,tokens[foreground]))
