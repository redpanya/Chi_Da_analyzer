"""후보 검토의 독립 보존·동시 편집·경로 방어를 임시 프로젝트에서 검사한다."""
from pathlib import Path
import tempfile
import unittest

from archive import context_review as review
from archive.storage import Conflict, ProjectLock, save_json


class CandidateReviewTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.path = Path(folder.name); self.run = 'a' * 32
        save_json(self.path / 'context/state.json', {'runs': [{'id': self.run, 'mode': 'clips'}]})
        self.originals = []
        for relative in (f'context/runs/{self.run}/result.json', f'context/comments/{self.run}.json',
                         'speech/transcript.json', 'voices/manual.json'):
            file = self.path / relative; save_json(file, {'원본': relative}); self.originals.append((file, file.read_bytes()))
        self.change = {'revision': 0, 'item': 'C1', 'status': 'accepted'}

    def test_save_conflict_reset_preserves_every_input(self):
        self.assertEqual(review.read(self.path, self.run), {'revision': 0, 'items': {}})
        value = review.save(self.path, self.run, self.change)
        self.assertEqual(value['items'], {'C1': 'accepted'})
        with self.assertRaises(Conflict): review.save(self.path, self.run, self.change)
        value = review.save(self.path, self.run, self.change | {'revision': 1, 'status': 'unreviewed'})
        self.assertEqual(value['items'], {})
        for file, content in self.originals: self.assertEqual(file.read_bytes(), content)

    def test_version_and_partial_project_are_independent(self):
        other = self.path / 'other' / '.download-ranges' / 'range' / 'vod-1'
        save_json(other / 'context/state.json', {'runs': [{'id': self.run, 'mode': 'clips'}]})
        review.save(self.path, self.run, self.change)
        self.assertEqual(review.read(other, self.run)['items'], {})
        second = 'b' * 32
        save_json(self.path / 'context/state.json', {'runs': [{'id': self.run, 'mode': 'clips'}, {'id': second, 'mode': 'clips'}]})
        self.assertEqual(review.read(self.path, second)['items'], {})

    def test_project_lock_blocks_overlapping_delete_or_work(self):
        with ProjectLock(self.path):
            with self.assertRaises(Conflict): review.save(self.path, self.run, self.change)
        self.assertEqual(review.read(self.path, self.run)['revision'], 0)

    def test_note_preserved_when_status_changes_and_conflicts_do_not_overwrite(self):
        note = '<script>문장 그대로</script>\n핵심 장면 확인'
        value = review.save(self.path, self.run, self.change | {'note': note})
        self.assertEqual(value['notes'], {'C1': note})
        value = review.save(self.path, self.run, self.change | {'revision': 1, 'status': 'unreviewed'})
        self.assertEqual(value['items'], {})
        self.assertEqual(value['notes'], {'C1': note})
        with self.assertRaises(Conflict):
            review.save(self.path, self.run, self.change | {'revision': 1, 'note': '다른 창'})
        self.assertEqual(review.read(self.path, self.run)['notes'], {'C1': note})
        value = review.save(self.path, self.run, self.change | {'revision': 2, 'note': ''})
        self.assertEqual(value['notes'], {})
        for file, content in self.originals: self.assertEqual(file.read_bytes(), content)

    def test_invalid_identifiers_values_and_symlinks(self):
        for run in ('../outside', 'A' * 32, 'b' * 32, None):
            with self.subTest(run=run), self.assertRaises(ValueError): review.read(self.path, run)
        for patch in ({'revision': True}, {'revision': -1}, {'item': ''}, {'item': 'x' * 2001},
                      {'item': 'two\nlines'}, {'status': 'deleted'}, {'status': []},
                      {'note': []}, {'note': 'x' * 1001}, {'note': 'bad\x00note'}):
            with self.subTest(patch=patch), self.assertRaises(ValueError): review.save(self.path, self.run, self.change | patch)
        (self.path / 'outside').mkdir()
        (self.path / 'context/reviews').symlink_to(self.path / 'outside', target_is_directory=True)
        with self.assertRaises(ValueError): review.save(self.path, self.run, self.change)
        self.assertEqual(list((self.path / 'outside').iterdir()), [])


if __name__ == '__main__': unittest.main()
