"""상세 재개가 저장된 요청만 사용하고 완료 자료와 잠금을 보존하는지 검사한다."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests import test_job_detail as fixtures
from archive.job_detail import resume
from archive.storage import Conflict


class JobResumeTests(unittest.TestCase):
    tearDown = fixtures.JobDetailTests.tearDown
    save = fixtures.JobDetailTests.save
    query = fixtures.JobDetailTests.query
    snapshot = fixtures.JobDetailTests.snapshot

    def setUp(self):
        fixtures.JobDetailTests.setUp(self)
        self.manager.tasks.submit = Mock(return_value={})
        self.manager.automation.remove_or_retry = Mock()
        self.request = {'root': str(self.root), 'vod_id': '1'}

    def submit(self, kind, **values):
        return resume(self.manager, self.request | {'kind': kind} | values)

    def test_download_reuses_saved_quality_and_rechecks_live_state(self):
        self.project['format_id'] = 'saved-480'
        self.project['tasks']['video']['state'] = 'paused'
        self.save('project.json', self.project)
        before = self.snapshot()
        action = self.query('video')['actions'][-1]
        self.assertEqual(action['action'], 'job-resume')
        self.submit('video', format_id='untrusted-1080')
        self.manager.tasks.submit.assert_called_once_with('start', self.request | {'kind': 'video', 'format_id': 'saved-480'})
        self.assertEqual(before, self.snapshot())
        self.manager.tasks.items = [{'state': 'queued', 'paths': [str(self.path)]}]
        with self.assertRaises(Conflict):
            self.submit('video')
        self.assertFalse(self.query('video')['actions'])
        self.manager.tasks.items = []
        self.project['tasks']['video']['state'] = 'complete'
        self.save('project.json', self.project)
        with self.assertRaises(Conflict):
            self.submit('video')

    def test_speech_preserves_manifest_settings_and_rejects_changed_audio(self):
        run = 'a' * 32
        state = {'state': 'error', 'action': 'transcribe', 'pending_run': run,
                 'raw_audio': {'sha256': 'audio-sha'}}
        self.save('speech/state.json', state)
        self.save(f'speech/runs/{run}/manifest.json', {'id': run, 'complete': False, 'language': 'ja',
            'source_audio_sha256': 'audio-sha', 'asr_options': {'vad': 'sensitive', 'prompt': '발음 힌트'}})
        before = self.snapshot()
        self.submit('speech', run=run, language='en')
        self.manager.tasks.submit.assert_called_once_with('speech-start', self.request | {
            'action': 'transcribe', 'language': 'ja', 'input_kind': 'original',
            'asr_options': {'vad': 'sensitive', 'prompt': '발음 힌트'}})
        self.assertEqual(before, self.snapshot())
        state['raw_audio']['sha256'] = 'changed'
        self.save('speech/state.json', state)
        with self.assertRaises(Conflict):
            self.submit('speech', run=run)

    def test_audio_resume_does_not_select_old_completed_transcript(self):
        old = 'a' * 32
        self.save(f'speech/runs/{old}/manifest.json', {'id': old, 'complete': True})
        self.save('speech/state.json', {'state': 'paused', 'action': 'audio', 'run': old,
            'resume_request': {'action': 'audio', 'options': {'track': 3, 'language': 'ko', 'input_kind': 'original',
                                                         'asr_options': {'vad': 'standard', 'prompt': ''}}}})
        self.assertIsNone(self.query('speech')['run'])
        self.submit('speech')
        self.assertEqual(self.manager.tasks.submit.call_args.args[1]['track'], 3)
        self.assertEqual(self.manager.tasks.submit.call_args.args[1]['action'], 'audio')
        self.assertNotIn('run', self.manager.tasks.submit.call_args.args[1])

    def test_context_exact_partial_run_and_no_external_gemma_resume(self):
        old, current = 'a' * 32, 'b' * 32
        self.save('context/state.json', {'state': 'paused', 'action': 'timestamps', 'run': current,
            'runs': [{'id': old, 'scope': 'clips-local'}, {'id': current, 'scope': 'timestamps'}]})
        self.save(f'context/runs/{old}/result.json', {'id': old, 'scope': 'clips-local', 'complete': False, 'origin': 'local'})
        self.save(f'context/runs/{current}/result.json', {'id': current, 'scope': 'timestamps', 'complete': False})
        self.submit('context', run=old)
        self.manager.tasks.submit.assert_called_once_with('context-start', self.request | {'action': 'clips-resume', 'options': {'run': old}})
        self.save(f'context/runs/{old}/result.json', {'id': old, 'scope': 'external', 'origin': 'external', 'complete': False})
        with self.assertRaises(Conflict):
            self.submit('context', run=old)

    def test_voice_resume_uses_pending_signature_and_checks_inputs(self):
        run, transcript = 'a' * 32, 'b' * 32
        self.save('speech/state.json', {'run': transcript, 'audio': {'sha256': 'audio'}})
        self.save('voices/state.json', {'state': 'error', 'action': 'diarize', 'pending_diarization': {'id': run,
            'signature': {'transcript_run': transcript, 'audio_sha256': 'audio', 'backend': 'fluid', 'speakers': 3}}})
        self.submit('voices')
        self.manager.tasks.submit.assert_called_once_with('voices-start', self.request | {
            'action': 'diarize', 'options': {'backend': 'fluid', 'speakers': 3}})
        self.save('speech/state.json', {'run': 'c' * 32, 'audio': {'sha256': 'audio'}})
        with self.assertRaises(Conflict):
            self.submit('voices')

    def test_queue_retry_keeps_saved_options_and_stale_running_can_resume(self):
        entry = {'id': 'a' * 32, 'vod': '1', 'state': 'partial', 'options': {'steps': ['transcribe']}}
        self.manager.automation.read.return_value = {'items': [entry]}
        self.manager.tasks.submit.return_value = {'queued': {'id': 'b' * 32, 'state': 'queued'}}
        result = self.submit('queue', id=entry['id'])
        self.assertEqual(result['queued']['state'], 'queued')
        self.manager.automation.remove_or_retry.assert_called_once_with(str(self.root), entry['id'], retry=True)
        self.manager.tasks.submit.assert_called_once_with('queue-start', {'root': str(self.root)})
        self.assertEqual(entry['options'], {'steps': ['transcribe']})
        self.manager.automation.remove_or_retry.reset_mock()
        entry['state'] = 'running'
        self.submit('queue', id=entry['id'])
        self.manager.automation.remove_or_retry.assert_not_called()

    def test_other_vod_busy_is_queued_without_blocking(self):
        self.project['format_id'] = '480'
        self.project['tasks']['chat']['state'] = 'error'
        self.save('project.json', self.project)
        self.manager.context_job = SimpleNamespace(path=self.root / 'vod-2', closed=False)
        self.manager.tasks.submit.return_value = {'queued': {'id': 'b' * 32, 'state': 'queued'}}
        self.assertIn('대기열', self.submit('chat')['message'])

    def test_heavy_context_without_exact_run_never_resumes_an_unrelated_current_run(self):
        self.manager.tasks.items = [{'id': 'a' * 32, 'action': 'context-start', 'state': 'error',
            'root': str(self.root), 'vod_id': '1', 'data': self.request | {'action': 'whole', 'options': {}}, 'paths': [str(self.path)]}]
        with self.assertRaises(Conflict):
            self.submit('heavy', id='a' * 32)
        self.manager.tasks.submit.assert_not_called()

    def test_changed_request_never_reuses_an_old_pending_speech_or_voice_run(self):
        run = 'a' * 32
        self.save('speech/state.json', {'state': 'error', 'action': 'transcribe', 'pending_run': run,
            'raw_audio': {'sha256': 'audio'}, 'resume_request': {'action': 'transcribe',
                'options': {'language': 'en', 'input_kind': 'original', 'asr_options': {'vad': 'standard', 'prompt': ''}}}})
        self.save(f'speech/runs/{run}/manifest.json', {'id': run, 'complete': False, 'language': 'ko',
            'source_audio_sha256': 'audio', 'asr_options': {'vad': 'standard', 'prompt': ''}})
        with self.assertRaises(Conflict):
            self.submit('speech')
        self.save('speech/state.json', {'run': run, 'audio': {'sha256': 'audio'}})
        self.save('voices/state.json', {'state': 'paused', 'action': 'diarize', 'pending_diarization': {'id': run,
            'signature': {'transcript_run': run, 'audio_sha256': 'audio', 'backend': 'fluid', 'speakers': 2}},
            'resume_request': {'action': 'diarize', 'options': {'backend': 'sherpa', 'speakers': 2}}})
        with self.assertRaises(Conflict):
            self.submit('voices')
        self.manager.tasks.submit.assert_not_called()

    def test_selected_external_result_never_inherits_local_failure_or_timing(self):
        run, export = 'a' * 32, 'b' * 32
        self.save('context/state.json', {'state': 'paused', 'action': 'timestamps', 'run': run,
            'message': '다른 로컬 실행 중단', 'timing': {'elapsed_ms': 4321},
            'runs': [{'id': run, 'scope': 'external', 'mode': 'timestamps'}]})
        self.save(f'context/runs/{run}/result.json', {'id': run, 'scope': 'external', 'origin': 'external',
            'export_id': export, 'mode': 'timestamps', 'complete': False})
        before = self.snapshot()
        view = self.query('context')
        self.assertEqual(view['state'], 'partial')
        self.assertEqual(view['records'], [])
        self.assertIsNone(view['timing'])
        self.assertEqual(view['actions'], [])
        self.assertEqual(view['result']['run'], run)
        self.assertEqual(view['workspace']['export_id'], export)
        self.assertEqual(before, self.snapshot())

    def test_http_resume_rechecks_identity_without_running_a_media_task(self):
        import json
        import threading
        from http.client import HTTPConnection
        from urllib.parse import urlsplit
        from archive.server import make_server
        self.project['format_id'] = 'saved-480'
        self.project['tasks']['video']['state'] = 'paused'
        self.save('project.json', self.project)
        before = self.snapshot()
        self.manager.tasks.submit.return_value = {'queued': {'id': 'a' * 32, 'state': 'queued'}}
        server, url = make_server(self.manager)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        parsed = urlsplit(url)
        client = HTTPConnection(parsed.hostname, parsed.port, timeout=3)
        payload = self.request | {'kind': 'video', 'format_id': 'untrusted-1080'}

        def call(origin=None):
            headers = {'Content-Type': 'application/json'}
            if origin:
                headers['Origin'] = origin
            client.request('POST', parsed.path + 'api/job-resume', json.dumps(payload), headers)
            response = client.getresponse()
            return response.status, json.loads(response.read())

        try:
            with patch('archive.server.error_log.record'):
                status, result = call()
                self.assertEqual(status, 200)
                self.assertEqual(result['queued']['state'], 'queued')
                self.manager.tasks.submit.assert_called_once_with('start', self.request | {'kind': 'video', 'format_id': 'saved-480'})
                self.assertEqual(call('https://example.org')[0], 403)
                self.manager.tasks.items = [{'state': 'queued', 'paths': [str(self.path)]}]
                self.assertEqual(call()[0], 409)
                self.assertEqual(self.manager.tasks.submit.call_count, 1)
                self.assertEqual(before, self.snapshot())
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join()
