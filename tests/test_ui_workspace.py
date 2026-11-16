"""새 보관함 요약은 일부 손상 자료와 원본을 분리하고 읽기만 수행한다."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
from archive import ui_workspace, error_log, runtime


class WorkspaceCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def project(self, vod='1', **extra):
        path = self.root / ('vod-' + vod)
        path.mkdir()
        value = dict(schema=2, vod_id=vod, metadata={'title': '독립 검증', 'channel': '검증', 'duration': 10},
                     tasks={kind: {'state': 'complete', 'progress': {}} for kind in ('video', 'chat')},
                     updated_at='2026-11-11T00:00:00Z') | extra
        (path / 'project.json').write_text(json.dumps(value), encoding='utf-8')
        return path

    def test_missing_and_empty_are_distinct_without_creating_files(self):
        missing = self.root / 'unplugged'
        self.assertEqual(ui_workspace.catalog(str(missing))['status'], 'missing')
        self.assertFalse(missing.exists())
        self.assertEqual(ui_workspace.catalog(str(self.root))['status'], 'empty')

    def test_catalog_is_read_only_and_summary_does_not_include_transcript(self):
        path = self.project()
        (path / 'speech').mkdir()
        state = {'state': 'complete', 'run': 'a', 'transcript': '원문 본문은 요약 목록에 필요 없음'}
        (path / 'speech/state.json').write_text(json.dumps(state), encoding='utf-8')
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        value = ui_workspace.catalog(str(self.root))
        self.assertEqual(value['projects'][0]['summaries']['speech']['state'], 'complete')
        self.assertNotIn('transcript', value['projects'][0]['summaries']['speech'])
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()})

    def test_corrupt_json_does_not_hide_other_projects(self):
        self.project()
        bad = self.root / 'vod-2'; bad.mkdir(); (bad / 'project.json').write_text('{')
        value = ui_workspace.catalog(str(self.root))
        self.assertEqual(value['status'], 'partial')
        self.assertEqual([p['vod_id'] for p in value['projects']], ['1'])
        self.assertTrue(value['warnings'])

    def test_audio_completion_and_saved_transcript_are_separate(self):
        path = self.project(); folder = path / 'speech'; folder.mkdir()
        state = {'state': 'complete', 'action': 'audio', 'raw_audio': {'file': 'source.wav'}}
        (folder / 'state.json').write_text(json.dumps(state))
        summary = ui_workspace.catalog(str(self.root))['projects'][0]['summaries']['speech']
        self.assertEqual((summary['action'], summary['audio_ready'], summary['transcript_state']), ('audio', True, 'idle'))
        run = 'a' * 32; target = folder / 'runs' / run; target.mkdir(parents=True)
        (target / 'manifest.json').write_text(json.dumps({'complete': True, 'segment_count': 2}))
        (folder / 'state.json').write_text(json.dumps(state | {'run': run}))
        summary = ui_workspace.catalog(str(self.root))['projects'][0]['summaries']['speech']
        self.assertEqual(summary['transcript_state'], 'complete')
        self.assertNotIn('raw_audio', summary)
        self.assertNotIn('transcript', summary)

    def test_external_results_are_separate_latest_metadata_and_read_only(self):
        path = self.project()
        context = path / 'context'; context.mkdir()
        export, other = 'd' * 32, 'e' * 32
        runs = []
        for run, package, complete in [('a' * 32, export, False), ('b' * 32, export, True), ('c' * 32, other, False)]:
            target = context / 'runs' / run; target.mkdir(parents=True)
            (target / 'result.json').write_text(json.dumps({'id': run, 'export_id': package, 'scope': 'external', 'mode': 'clips', 'complete': complete}))
            runs.append({'id': run, 'scope': 'external'})
        # 손상된 개별 결과와 잘못된 식별자가 다른 외부 결과를 숨기지 않는다.
        runs += [{'id': 'f' * 32, 'scope': 'external'}, {'id': '../outside', 'scope': 'external'}]
        (context / 'state.json').write_text(json.dumps({'state': 'paused', 'message': '이전 로컬 작업', 'runs': runs}))
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        row = ui_workspace.catalog(str(self.root))['projects'][0]
        self.assertEqual(row['summaries']['context']['state'], 'paused')
        self.assertEqual([(r['export_id'], r['run'], r['state']) for r in row['external_results']],
                         [(other, 'c' * 32, 'partial'), (export, 'b' * 32, 'complete')])
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()})

    def test_external_result_symlink_cannot_be_read(self):
        path = self.project(); context = path / 'context'; context.mkdir()
        run = 'a' * 32
        (context / 'state.json').write_text(json.dumps({'runs': [{'id': run, 'scope': 'external'}]}))
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside); (target / run).mkdir()
            (target / run / 'result.json').write_text(json.dumps({'id': run, 'scope': 'external', 'export_id': 'b' * 32, 'mode': 'detail', 'complete': True}))
            (context / 'runs').symlink_to(target, target_is_directory=True)
            self.assertEqual(ui_workspace.catalog(str(self.root))['projects'][0]['external_results'], [])

    def test_context_usable_results_and_failure_flags_are_read_only_and_cache_refreshes(self):
        path = self.project(); run = 'a' * 32
        folder = path / 'context/runs' / run; folder.mkdir(parents=True)
        state = {'state': 'review', 'run': run, 'runs': [{'id': run, 'scope': 'timestamps'}]}
        (path / 'context/state.json').write_text(json.dumps(state))
        (folder / 'result.json').write_text(json.dumps({'complete': True}))
        work = folder / 'work.json'
        work.write_text(json.dumps({'chunks': [{'error': '중단'}], 'replies': {'1': {'topics': [{'title': '저장된 주제'}]}}}))
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in path.rglob('*') if p.is_file()}
        with patch('archive.context_job.result', side_effect=AssertionError('보관함은 전체 결과 재구성을 호출하지 않음')):
            result = ui_workspace.catalog(str(self.root))['projects'][0]['summaries']['context']['results']
        self.assertEqual(result, {'usable': True, 'previous': False, 'issues': True, 'complete': True, 'origin': 'local'})
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in path.rglob('*') if p.is_file()})
        # 같은 경로의 결과 변경 시 이전의 사용 가능 판정을 재사용하지 않는다.
        work.write_text(json.dumps({'chunks': [{'error': '중단'}], 'replies': {}}))
        self.assertFalse(ui_workspace.catalog(str(self.root))['projects'][0]['summaries']['context']['results']['usable'])

    def test_context_previous_external_results_survive_current_failure(self):
        path = self.project(); current, previous = 'a' * 32, 'b' * 32
        for run in (current, previous):
            folder = path / 'context/runs' / run; folder.mkdir(parents=True)
            (folder / 'result.json').write_text(json.dumps({'complete': run == previous}))
        (path / f'context/runs/{current}/dialogue-state.json').write_text(json.dumps({'items': [
            {'title': '요약 실패', 'failed': True}, {'title': '전사 없음', 'gap': True}]}))
        (path / f'context/runs/{previous}/work.json').write_text(json.dumps({'replies': {'1': {'clips': [{'title': '이전 후보'}]}}}))
        state = {'state': 'error', 'run': current, 'runs': [{'id': previous, 'scope': 'external'}, {'id': current, 'scope': 'full'}]}
        state_file = path / 'context/state.json'; state_file.write_text(json.dumps(state))
        result = ui_workspace.catalog(str(self.root))['projects'][0]['summaries']['context']['results']
        self.assertTrue(result['usable']); self.assertTrue(result['previous']); self.assertTrue(result['issues'])
        self.assertEqual(result['origin'], 'external')
        # 현재 버전이 없는 옛 상태 파일도 최신 사용 가능 버전의 완료 여부를 표시한다.
        state.pop('run'); state_file.write_text(json.dumps(state))
        result = ui_workspace.catalog(str(self.root))['projects'][0]['summaries']['context']['results']
        self.assertTrue(result['complete']); self.assertFalse(result['previous'])
        (path / f'context/runs/{previous}/work.json').write_text('{')
        result = ui_workspace.catalog(str(self.root))['projects'][0]['summaries']['context']['results']
        self.assertFalse(result['usable'])

    def test_wrong_shape_is_reported_per_project(self):
        self.project()
        for vod, value in [('2', []), ('3', {'schema': 2, 'vod_id': '3', 'tasks': {'video': None, 'chat': {}}, 'metadata': []})]:
            bad = self.root / ('vod-' + vod); bad.mkdir(); (bad / 'project.json').write_text(json.dumps(value))
        value = ui_workspace.catalog(str(self.root))
        self.assertEqual(value['status'], 'partial')
        self.assertEqual([p['vod_id'] for p in value['projects']], ['1'])
        self.assertEqual(len(value['warnings']), 2)

    def test_replacement_task_remains_visible_while_current_video_is_complete(self):
        self.project(video_replacement={'task': {'state': 'downloading', 'message': '다른 화질 받기', 'progress': {'percent': 20}}})
        row = ui_workspace.catalog(str(self.root))['projects'][0]
        self.assertEqual(row['tasks']['video']['state'], 'complete')
        self.assertEqual(row['video_replacement']['task']['state'], 'downloading')

    def test_invalid_sort_time_cannot_break_the_whole_catalog(self):
        self.project()
        self.project('2', updated_at=None)
        value = ui_workspace.catalog(str(self.root))
        self.assertIn('1', [p['vod_id'] for p in value['projects']])
        self.assertIn(value['status'], ('ready', 'partial'))

    def test_symlinks_do_not_expose_other_folders_in_catalog_or_storage(self):
        self.project()
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside); (target / 'secret').write_bytes(b'x' * 100)
            (self.root / 'linked').symlink_to(target, target_is_directory=True)
            (self.root / 'vod-2').symlink_to(target, target_is_directory=True)
            (self.root / 'linked-file').symlink_to(target / 'secret')
            self.assertEqual(len(ui_workspace.catalog(str(self.root))['projects']), 1)
            size = (self.root / 'vod-1/project.json').stat().st_size
            self.assertEqual(sum(ui_workspace.storage_info(str(self.root))['sizes'].values()), size)

    def test_preflight_checks_only_requested_pending_steps_without_writing(self):
        self.project()
        data = {'items': [
            {'title': '다운로드만', 'state': 'queued', 'options': {'steps': ['download']}},
            {'title': '이미 끝난 전사', 'state': 'complete', 'options': {'steps': ['transcribe', 'context', 'diarize']}},
        ]}
        original = deepcopy(data)
        manager = SimpleNamespace(automation=SimpleNamespace(read=Mock(return_value=data)))
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        with patch('archive.ui_workspace.shutil.which', return_value='/existing/tool') as which, \
             patch('archive.speech_model.status') as speech, patch('archive.context_model.status') as context, \
             patch('archive.speaker_tools.supported') as speaker:
            value = ui_workspace.preflight(manager, str(self.root))
        self.assertEqual([item['title'] for item in value['items']], ['다운로드만'])
        self.assertTrue(all(check['ready'] for check in value['checks']))
        self.assertEqual({call.args[0] for call in which.call_args_list}, {'ffmpeg', 'ffprobe'})
        speech.assert_not_called(); context.assert_not_called(); speaker.assert_not_called()
        self.assertEqual(data, original)
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()})

    def test_preflight_reports_missing_tools_without_changing_options_or_results(self):
        data = {'items': [{'title': '분석 대기', 'state': 'paused', 'preview': '완료 전사 재사용',
                           'options': {'steps': ['transcribe', 'diarize', 'context'], 'backend': 'pyannote'}}]}
        original = deepcopy(data)
        manager = SimpleNamespace(automation=SimpleNamespace(read=Mock(return_value=data)))
        with patch('archive.ui_workspace.shutil.which', return_value=None), \
             patch('archive.speech_model.status', return_value={'ready': True, 'engine': False}) as speech, \
             patch('archive.context_model.status', return_value={'ready': False, 'engine': True}) as context, \
             patch('archive.speaker_tools.supported', return_value=True):
            value = ui_workspace.preflight(manager, str(self.root))
        checks = {check['label']: check['ready'] for check in value['checks']}
        for label in ('영상·음성 도구', '전사 모델·도구', 'Gemma 모델·도구'):
            self.assertFalse(checks[label])
        self.assertTrue(checks['화자 도구: pyannote'])
        self.assertEqual(value['items'][0]['preview'], '완료 전사 재사용')
        speech.assert_called_once(); context.assert_called_once()
        self.assertEqual(data, original)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_packaged_tools_are_found_without_system_installation(self):
        manager = SimpleNamespace(automation=SimpleNamespace(read=Mock(return_value={'items': [
            {'title': '다운로드', 'state': 'queued', 'options': {'steps': ['download']}}
        ]})))
        for layout in ('native/ffmpeg', 'bin'):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as package:
                tools = Path(package) / layout
                tools.mkdir(parents=True)
                suffix = '.exe' if os.name == 'nt' else ''
                for name in ('ffmpeg', 'ffprobe'):
                    executable = tools / (name + suffix)
                    executable.write_bytes(b'not executed')
                    executable.chmod(0o755)
                with patch.object(runtime, 'FROZEN', True), \
                     patch.object(runtime.sys, '_MEIPASS', package, create=True), \
                     patch.object(runtime, 'MODEL_ROOT', runtime.MODEL_ROOT), \
                     patch.object(runtime, 'settings', return_value={}), patch.dict(os.environ, {'PATH': ''}):
                    runtime.configure()
                    value = ui_workspace.preflight(manager, str(self.root))
                    media = next(check for check in value['checks'] if check['label'] == '영상·음성 도구')
                    self.assertTrue(media['ready'])
                    for name in ('ffmpeg', 'ffprobe'):
                        self.assertEqual(Path(ui_workspace.shutil.which(name)), tools / (name + suffix))

    def test_error_export_uses_only_selected_ids_and_omits_messages(self):
        with patch.object(runtime, 'SUPPORT', self.root):
            error_log.record('selected', ValueError('방송 본문과 C:\\개인\\자료'), vod='1')
            error_log.record('other', ValueError('다른 방송 원문'), vod='2')
            local = error_log.snapshot()['events']
            selected = local[0]['event_id']
            before = error_log.location().read_bytes()
            exported = error_log.dispatch('export', {'ids': [selected]})
            self.assertEqual([event['event_id'] for event in exported['events']], [selected])
            self.assertNotIn('message', exported['events'][0])
            self.assertNotIn('방송 본문', json.dumps(exported, ensure_ascii=False))
            self.assertEqual(error_log.dispatch('export', {'ids': []})['events'], [])
            for ids in (['0' * 24], ['../outside'], 'not-list'):
                with self.assertRaises(ValueError):
                    error_log.dispatch('export', {'ids': ids})
            self.assertEqual(error_log.location().read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
