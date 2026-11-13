"""작업 상세 조회의 실행 귀속과 읽기 전용 동작을 검사한다."""
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from archive.job_detail import detail
from archive.storage import Conflict


class JobDetailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / 'vod-1'
        self.project = dict(schema=2, vod_id='1', metadata={'title': '검사 영상', 'duration': 20},
                            tasks={kind: {'state': 'complete', 'message': '저장 완료', 'progress': {}} for kind in ('video', 'chat')})
        self.save('project.json', self.project)
        self.manager = SimpleNamespace(guard=threading.RLock(), job=None, speech_job=None, voice_job=None,
            context_job=None, reports=SimpleNamespace(read=Mock(), list=Mock()),
            tasks=SimpleNamespace(items=[]), automation=SimpleNamespace(guard=threading.RLock(), running=False,
                current_path=None, root=None, read=Mock(return_value={'items': []}), status=Mock()))

    def tearDown(self):
        self.temp.cleanup()

    def save(self, relative, value):
        file = self.path / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def query(self, kind, **extra):
        return detail(self.manager, {'root': str(self.root), 'vod_id': '1', 'kind': kind} | extra)

    def snapshot(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}

    def test_stale_running_does_not_recover_or_read_unrelated_reports(self):
        self.save('speech/state.json', {'state': 'running', 'message': '이전 실행 기록', 'updated_at': '2026-01-01T00:00:00Z',
                                      'timing': {'elapsed_ms': 10, 'since_ms': 123}})
        before = self.snapshot()
        result = self.query('speech')
        self.assertEqual(result['state'], 'paused')
        self.assertFalse(result['owned'])
        self.assertIsNone(result['timing']['since_ms'])
        self.assertEqual(result['records'][0]['message'], '이전 실행 기록')
        self.assertEqual(result['actions'], [])
        self.manager.reports.read.assert_not_called()
        self.manager.reports.list.assert_not_called()
        self.assertEqual(before, self.snapshot())

    def test_stop_action_only_for_owned_exact_project(self):
        self.project['tasks']['video'] = {'state': 'downloading', 'message': '영상 받는 중',
            'progress': {'downloaded_bytes': 5, 'total_bytes': 10}}
        self.save('project.json', self.project)
        self.manager.job = SimpleNamespace(project=SimpleNamespace(path=self.root / 'vod-2'), closed=False)
        self.assertEqual(self.query('video')['actions'], [])
        self.manager.job.project.path = self.path
        result = self.query('video')
        self.assertEqual(result['progress']['fraction'], .5)
        self.assertEqual(result['actions'], [{'label': '작업 중단', 'action': 'stop',
            'data': {'root': str(self.root), 'vod_id': '1', 'kind': 'video'}}])
        self.assertEqual(result['result'], {'root': str(self.root), 'vod_id': '1', 'step': 2})
        self.assertIn({'label': 'VOD 번호', 'value': '1'}, result['fields'])

    def test_pending_transcript_does_not_show_previous_run_as_current(self):
        old, new = 'a' * 32, 'b' * 32
        self.save('speech/state.json', {'state': 'running', 'message': '새 전사 처리 중', 'run': old, 'pending_run': new})
        self.save(f'speech/runs/{old}/manifest.json', {'id': old, 'complete': True, 'segment_count': 22})
        self.save(f'speech/runs/{new}/manifest.json', {'id': new, 'complete': False, 'segment_count': 2, 'processed_ms': 1000, 'duration_ms': 20000})
        self.manager.speech_job = SimpleNamespace(path=self.path, closed=False)
        result = self.query('speech')
        self.assertEqual(result['run'], new)
        self.assertIsNone(result['result'])
        self.assertEqual(result['workspace']['step'], 3)
        self.assertEqual(result['progress']['fraction'], .05)
        previous = self.query('speech', run=old)
        self.assertEqual(previous['result']['run'], old)
        self.assertEqual(previous['state'], 'complete')
        self.assertEqual(previous['records'], [])
        self.assertEqual(previous['actions'], [])
        self.assertFalse(previous['owned'])

    def test_owned_voice_job_only_links_already_selected_result(self):
        old, pending, historical = 'a' * 32, 'b' * 32, 'c' * 32
        self.save('voices/state.json', {'state': 'running', 'run': old, 'runs': [historical, old],
            'pending_diarization': {'id': pending}, 'message': '새 화자 구분 중'})
        for run in (old, pending, historical):
            self.save(f'voices/runs/{run}/result.json', {'id': run, 'speakers': {}, 'assignments': {}})
        self.manager.voice_job = SimpleNamespace(path=self.path, closed=False)
        before = self.snapshot()
        current = self.query('voices')
        self.assertEqual(current['run'], pending)
        self.assertIsNone(current['result'])
        self.assertEqual(current['workspace']['step'], 4)
        self.assertEqual(self.query('voices', run=old)['result']['run'], old)
        self.assertIsNone(self.query('voices', run=historical)['result'])
        self.assertEqual(before, self.snapshot())
        self.manager.voice_job.closed = True
        self.assertIsNone(self.query('voices')['result'])
        self.assertEqual(self.query('voices', run=historical)['result']['run'], historical)

    def test_clips_uses_clip_run_and_not_unrelated_timestamp_run(self):
        older, clip = 'a' * 32, 'b' * 32
        self.save('context/state.json', {'state': 'paused', 'action': 'clips', 'run': older, 'clip_run': clip,
            'message': '클립 작업 중단', 'runs': [{'id': older, 'scope': 'timestamps'}, {'id': clip, 'scope': 'clips-local'}]})
        self.save(f'context/runs/{clip}/result.json', {'id': clip, 'mode': 'clips', 'complete': False, 'model': 'Gemma'})
        result = self.query('context')
        self.assertEqual(result['run'], clip)
        self.assertEqual(result['mode'], 'clips')
        self.assertEqual(result['result']['step'], 6)
        self.assertEqual(result['records'][0]['message'], '클립 작업 중단')

    def test_queue_uses_exact_report_and_resolves_range_project(self):
        item_id, report_id = 'a' * 32, 'b' * 32
        ranged = self.root / '.download-ranges' / ('c' * 32)
        self.path = ranged / 'vod-1'
        self.save('project.json', self.project)
        item = {'id': item_id, 'vod': '1', 'project_root': str(ranged), 'state': 'complete', 'report': report_id,
                'title': '범위 영상', 'options': {'height': 480}, 'stages': {'download': 'reused'}}
        self.manager.automation.read.return_value = {'items': [item]}
        self.manager.reports.read.return_value = {'payload': {'vod_id': '1'}, 'events': [
            {'at': str(n), 'stage': 'download', 'state': 'running', 'message': f'정확한 기록 {n}'} for n in range(8)]}
        before = self.snapshot()
        result = detail(self.manager, {'root': str(self.root), 'kind': 'queue', 'id': item_id})
        self.assertEqual(result['result']['root'], str(ranged))
        self.assertEqual(result['result']['vod_id'], '1')
        self.assertIn({'label': 'VOD 번호', 'value': '1'}, result['fields'])
        self.assertEqual([row['at'] for row in result['records']], ['3', '4', '5', '6', '7'])
        self.manager.reports.read.assert_called_once_with(str(ranged), '1', report_id)
        self.manager.automation.status.assert_not_called()
        self.assertEqual(before, self.snapshot())
        with self.assertRaises(Conflict):
            detail(self.manager, {'root': str(self.root / '.download-ranges' / ('d' * 32)), 'kind': 'queue', 'id': item_id})

    def test_heavy_uses_server_snapshot_without_exposing_request_text(self):
        item_id = 'e' * 32
        self.manager.tasks.items = [{'id': item_id, 'root': str(self.root), 'vod_id': '1', 'state': 'queued',
            'action': 'context-start', 'label': 'AI 문맥', 'title': '검사 영상', 'message': '대기 중',
            'data': {'options': {'thinking': True, 'custom_request': '비공개 요청'}, 'path': '/secret'}, 'paths': ['/secret']}]
        before = self.snapshot()
        result = detail(self.manager, {'kind': 'heavy', 'id': item_id})
        self.assertEqual(result['workspace'], {'root': str(self.root), 'vod_id': '1', 'step': 6})
        self.assertEqual(result['actions'][0]['action'], 'work-cancel')
        self.assertIn({'label': 'VOD 번호', 'value': '1'}, result['fields'])
        self.assertNotIn('비공개 요청', json.dumps(result, ensure_ascii=False))
        self.assertNotIn('/secret', json.dumps(result))
        self.assertIsNone(result['records'][0]['at'])
        self.assertEqual(before, self.snapshot())
        with self.assertRaises(Conflict):
            self.query('heavy', id=item_id, vod_id='2')

    def test_queue_only_shows_settings_for_selected_steps(self):
        item_id = 'f' * 32
        options = {'steps': ['download', 'audio', 'transcribe'], 'height': 480, 'language': 'ko',
            'asr_options': {'vad': 'standard'}, 'backend': 'sherpa', 'thinking': True, 'summary_modes': ['detail']}
        self.manager.automation.read.return_value = {'items': [
            {'id': item_id, 'vod': '1', 'state': 'queued', 'options': options}]}
        result = self.query('queue', id=item_id)
        fields = {r['label']: r['value'] for r in result['fields']}
        self.assertEqual(fields['언어'], '한국어')
        self.assertEqual(fields['발화 검출'], '표준')
        self.assertEqual(fields['최대 화질'], '480p')
        for label in ('화자 엔진', '사고 모드', 'AI 분석 모드'):
            self.assertNotIn(label, fields)
        options['steps'] = ['diarize', 'context']
        fields = {r['label']: r['value'] for r in self.query('queue', id=item_id)['fields']}
        self.assertEqual(fields['화자 엔진'], 'sherpa-onnx')
        self.assertEqual(fields['사고 모드'], '켜기')
        self.assertEqual(fields['AI 분석 모드'], '상세 문맥')
        for label in ('언어', '발화 검출', '최대 화질'):
            self.assertNotIn(label, fields)

    def test_invalid_run_and_linked_result_are_rejected(self):
        self.save('speech/state.json', {'state': 'complete', 'run': 'a' * 32})
        with self.assertRaises(ValueError):
            self.query('speech', run='../../private')
        with tempfile.TemporaryDirectory() as outside:
            folder = self.path / 'speech/runs'
            folder.mkdir()
            (folder / ('a' * 32)).symlink_to(outside, target_is_directory=True)
            with self.assertRaises(Conflict):
                self.query('speech')

    def test_deleted_and_missing_older_results_do_not_fall_back(self):
        self.save('speech/state.json', {'state': 'complete', 'run': 'a' * 32, 'deleted_runs': ['b' * 32]})
        with self.assertRaises(ValueError):
            self.query('speech', run='b' * 32)
        with self.assertRaises(ValueError):
            self.query('speech', run='c' * 32)


if __name__ == '__main__':
    unittest.main()
