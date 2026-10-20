"""자료별 예외 없이 시간 이동·잘림·경계 반복·응답 변경·오프라인 복구를 검사한다."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from archive import chat, chat_workdb, media_timeline, video
from archive.storage import Project, ProjectLock, create_or_load, save_json, read_json
from test_archive import metadata, message, page


class TimelineTests(unittest.TestCase):
    def streams(self, offset=0, duration=72000):
        return {kind: {'first': offset+delay, 'end': offset+duration, 'count': 100, 'sha256': kind}
                for kind, delay in (('video', .04), ('audio', 0))}

    def test_constant_shift_positive_negative_and_long_duration(self):
        for start in (-5, 0, 2.095646, 123):
            result = media_timeline.compare(self.streams(start), self.streams(), copied=True)
            self.assertAlmostEqual(result['differences']['video']['end_delta_seconds'], 0)

    def test_loss_changed_content_and_av_shift_are_rejected(self):
        for changed in ({'count': 99}, {'sha256': 'other'}, {'end': 71998}, {'first': 3}):
            target = self.streams(); target['audio'].update(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                media_timeline.compare(self.streams(), target, copied=True)
        with self.assertRaises(ValueError):
            media_timeline.compare(self.streams(), {'video': self.streams()['video']}, copied=True)

    def test_transcode_allows_changed_packets_but_not_time_loss(self):
        target = self.streams(); target['video'].update(count=500, sha256='new codec')
        media_timeline.compare(self.streams(2), target, copied=False)
        target['audio']['end'] -= 2
        with self.assertRaises(ValueError): media_timeline.compare(self.streams(2), target, copied=False)


class ChatRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.path = Path(self.temp.name)/'vod-1'
        self.lock = ProjectLock(self.path)
        self.project = Project(self.path, create_or_load(self.path, metadata(), '360p'), self.lock)
        self.addCleanup(self.temp.cleanup); self.addCleanup(self.lock.close)

    def msg(self, at, text='반복', who='person'):
        return message(at, text) | {'userIdHash': who, 'messageTypeCode': 1}

    def saved(self, boundary_messages, audit_messages):
        a = self.msg(1, '앞'); z = self.msg(2000, '뒤')
        values = [page([a, *boundary_messages], 1000), page([z], None)]
        for n, payload in enumerate(values):
            save_json(self.path/f'chat-pages/{n:06}.json', {'vod_id': '1', 'cursor': 0 if n == 0 else 1000, 'response': payload})
        save_json(self.path/'diagnostics/chat-audit/0.json', values[0])
        save_json(self.path/'diagnostics/chat-audit/999.json', page([*audit_messages, z], None))
        save_json(self.path/'diagnostics/chat-audit.json', {'old': '보존'})
        old = self.path/'exports/old/chat.jsonl'; old.parent.mkdir(parents=True, exist_ok=True); old.write_bytes(b'old-results')
        self.before = {p: p.read_bytes() for p in self.path.rglob('*.json')}
        self.before[old] = old.read_bytes()

    def collect(self):
        with patch('archive.chat.fetch', side_effect=AssertionError('저장 자료만으로 복구해야 함')):
            chat.collect(self.project, threading.Event())
        for file, content in self.before.items():
            if file.name != 'project.json': self.assertEqual(file.read_bytes(), content)
        task = self.project.snapshot()['tasks']['chat']
        rows = read_json(self.path/task['assets']['json'])['messages']
        return task, rows

    def test_recovers_missing_boundary_and_preserves_identical_real_repeats(self):
        repeated = self.msg(1000)
        self.saved([repeated], [repeated, repeated])
        first, rows = self.collect()
        self.assertEqual(first['state'], 'complete'); self.assertEqual(first['verification']['recovered'], 1)
        self.assertEqual([r['offset_ms'] for r in rows], [1, 1000, 1000, 2000])
        second, again = self.collect()
        self.assertEqual(rows, again); self.assertNotEqual(first['assets'], second['assets'])
        self.assertTrue((self.path/first['assets']['json']).exists())

    def test_profile_change_and_nonboundary_missing_remain_review(self):
        original = self.msg(1000)
        for observed in (original | {'profile': '{"nickname":"새 이름"}'}, self.msg(1001, '경계 밖')):
            with self.subTest(observed=observed):
                self.saved([original], [observed])
                task, rows = self.collect()
                self.assertEqual(task['state'], 'review'); self.assertEqual(task['verification']['recovered'], 0)
                self.assertEqual(len(rows), 3)

    def test_saturated_timestamp_does_not_claim_completion(self):
        item = self.msg(1000)
        self.saved([item], [item])
        save_json(self.path/'diagnostics/chat-audit/999.json', page([item]*200, None))
        self.before[self.path/'diagnostics/chat-audit/999.json'] = (self.path/'diagnostics/chat-audit/999.json').read_bytes()
        task, rows = self.collect()
        self.assertEqual(task['state'], 'review'); self.assertEqual(len(rows), 3)

    def test_corrupt_cached_audit_does_not_change_selected_exports(self):
        item = self.msg(1000); self.saved([item], [item])
        self.project.update('chat', state='review', assets={'jsonl': 'exports/old/chat.jsonl'})
        (self.path/'diagnostics/chat-audit/999.json').write_text('{', encoding='utf-8')
        with self.assertRaises(ValueError): chat.collect(self.project, threading.Event())
        self.assertEqual(self.project.snapshot()['tasks']['chat']['assets'], {'jsonl': 'exports/old/chat.jsonl'})

    def test_index_stays_outside_library_and_is_closed_and_removed(self):
        item = self.msg(1000); self.saved([item], [item, item])
        scratch = Path(self.temp.name)/'내장 임시'; opened = []
        connect = sqlite3.connect
        def tracked(file):
            self.assertTrue(Path(file).is_relative_to(scratch))
            self.assertFalse(Path(file).is_relative_to(self.path))
            db = connect(file); opened.append(db); return db
        old_db = self.path/'exports/old/counts.sqlite'; old_db.write_bytes('기존 DB 보존'.encode())
        with patch.object(chat_workdb, 'temporary_root', return_value=scratch), \
                patch.object(chat_workdb.sqlite3, 'connect', side_effect=tracked):
            task, rows = self.collect()
        self.assertEqual(task['state'], 'complete'); self.assertEqual(len(rows), 4)
        self.assertEqual(len(opened), 1)
        with self.assertRaises(sqlite3.ProgrammingError): opened[0].execute('SELECT 1')
        self.assertEqual(list(scratch.iterdir()), [])
        self.assertEqual(list((self.path/'exports').rglob('*.sqlite')), [old_db])
        self.assertEqual(old_db.read_bytes(), '기존 DB 보존'.encode())

    def test_full_scratch_preserves_selected_exports_and_retry_uses_pages(self):
        item = self.msg(1000); self.saved([item], [item, item])
        selected = {'jsonl': 'exports/old/chat.jsonl'}
        self.project.update('chat', state='review', assets=selected)
        scratch = Path(self.temp.name)/'내장 임시'
        error = sqlite3.OperationalError('database or disk is full')
        error.sqlite_errorcode = sqlite3.SQLITE_FULL
        with patch.object(chat_workdb, 'temporary_root', return_value=scratch):
            with patch.object(chat.chat_boundary, 'reconcile', side_effect=error):
                with self.assertRaisesRegex(ValueError, '내장 임시 공간'):
                    self.collect()
            self.assertEqual(self.project.snapshot()['tasks']['chat']['assets'], selected)
            self.assertEqual(list(scratch.iterdir()), [])
            task, rows = self.collect()
        self.assertEqual(task['state'], 'complete'); self.assertEqual(len(rows), 4)
        self.assertEqual(list(scratch.iterdir()), [])

    def test_cancel_during_audit_removes_scratch_and_preserves_results(self):
        item = self.msg(1000); self.saved([item], [item, item])
        selected = {'jsonl': 'exports/old/chat.jsonl'}
        self.project.update('chat', state='review', assets=selected)
        scratch = Path(self.temp.name)/'내장 임시'; stop = threading.Event()
        reconcile = chat.chat_boundary.reconcile
        def cancel(*args):
            result = reconcile(*args); stop.set(); return result
        with patch.object(chat_workdb, 'temporary_root', return_value=scratch), \
                patch.object(chat.chat_boundary, 'reconcile', side_effect=cancel), \
                patch.object(chat, 'fetch', side_effect=AssertionError('네트워크 요청 금지')):
            with self.assertRaises(chat.Cancelled): chat.collect(self.project, stop)
        self.assertEqual(list(scratch.iterdir()), [])
        self.assertEqual(self.project.snapshot()['tasks']['chat']['assets'], selected)
        task, _ = self.collect(); self.assertEqual(task['state'], 'complete')

    def test_macos_uses_system_temp_instead_of_external_tmpdir(self):
        with patch.object(chat_workdb.sys, 'platform', 'darwin'), \
                patch.dict(os.environ, {'TMPDIR': '/Volumes/external'}):
            self.assertEqual(chat_workdb.temporary_root(), Path('/private/tmp'))


if __name__ == '__main__': unittest.main()
