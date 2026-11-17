"""첫 방문 예약, 다시 보기, 독립 사용자 설정의 회귀 검사."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from archive import runtime, tutorial


class TutorialTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        setting = patch.object(runtime, 'SUPPORT', Path(folder.name))
        setting.start()
        self.addCleanup(setting.stop)

    def visit(self, guide):
        return tutorial.update({'action': 'visit', 'guide': guide})['show']

    def test_first_visit_shared_between_windows_and_restarts(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(self.visit, ['register'] * 4)), 1)
        self.assertTrue(self.visit('library'))
        self.assertFalse(self.visit('register'))
        self.assertEqual(tutorial.state()['guides'], {'register': 'seen', 'library': 'seen'})

    def test_disable_manual_replay_and_enable(self):
        self.assertTrue(self.visit('welcome'))
        tutorial.update({'action': 'disable'})
        self.assertFalse(self.visit('jobs'))
        tutorial.update({'action': 'replay', 'guide': 'mix'})
        self.assertTrue(self.visit('mix'))
        self.assertFalse(self.visit('mix'))
        self.assertFalse(tutorial.state()['enabled'])
        tutorial.update({'action': 'enable'})
        self.assertTrue(self.visit('jobs'))
        self.assertFalse(self.visit('welcome'))

    def test_invalid_preferences_do_not_block_startup_or_change_app_settings(self):
        folder = runtime.SUPPORT / 'tutorial'
        folder.mkdir()
        marker = runtime.SUPPORT / 'settings.json'
        marker.write_bytes(b'{"library":"old"}')
        for bad in ('{', '[]', '{"guides": null}'):
            (folder / 'state.json').write_text(bad)
            self.assertTrue(self.visit('library'))
        with self.assertRaises(ValueError):
            self.visit('../settings')
        self.assertEqual(marker.read_bytes(), b'{"library":"old"}')

    def test_mix_list_and_editor_share_one_intro_and_pending_replay(self):
        self.assertTrue(self.visit('mixList'))
        self.assertFalse(self.visit('mix'))
        file = runtime.SUPPORT/'tutorial'/'state.json'
        file.write_text('{"guides":{"mix":"seen","mixList":"replay","clip":"seen"}}')
        self.assertTrue(self.visit('mix'))
        self.assertFalse(self.visit('mixList'))
        self.assertFalse(self.visit('clip'))
