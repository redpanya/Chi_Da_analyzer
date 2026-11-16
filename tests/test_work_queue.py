"""독립 작업 병행, 충돌 대기, 취소와 오류 복구, 원본 보존."""
import copy
import hashlib
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from archive.jobs import Manager
from archive.storage import Conflict, ResourceBusy, ProjectLock, create_or_load, load_project, save_json
from archive import work_queue


def until(check, timeout=10):
    end = time.monotonic() + timeout
    while not check():
        if time.monotonic() >= end:
            raise AssertionError('대기 작업이 제한 시간 안에 진행되지 않았습니다')
        time.sleep(.02)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root/'vod-1'
        with ProjectLock(self.path):
            create_or_load(self.path, {'id':'1','title':'대기열 검사','channel':'검사','duration':4,'formats':[{'id':'test'}]}, 'test')
        self.manager = Manager(self.root)
        self.queue = self.manager.tasks
        self.args = {'root':str(self.root), 'vod_id':'1', 'action':'whole', 'options':{'thinking':True}}

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def test_independent_jobs_snapshot_duplicate_cancel_and_error_continuation(self):
        calls = []
        release = threading.Event()
        def execute(manager, action, data):
            calls.append(copy.deepcopy(data))
            if data['options']['thinking']:
                release.wait(5)
                raise ValueError('독립 실패')
            return {}
        try:
            with patch.object(work_queue, 'execute', side_effect=execute), patch.object(work_queue.error_log, 'record'):
                with self.manager.guard:
                    first = self.queue.submit('context-start', self.args)['queued']
                    self.assertEqual(first['id'], self.queue.submit('context-start', self.args)['queued']['id'])
                    self.args['options']['thinking'] = False
                    cancelled = self.queue.submit('context-start', self.args)['queued']
                    self.queue.cancel(cancelled['id'])
                    last = self.queue.submit('context-start', self.args)['queued']
                until(lambda: self.queue.items[-1]['state'] == 'complete')
                until(lambda: len(calls) == 2)
                self.assertCountEqual([call['options']['thinking'] for call in calls], [True, False])
                with self.assertRaises(Conflict): self.manager.deletion_preview(str(self.root), '1')
                with self.assertRaises(Conflict): self.manager.compute_settings({'mode':'cpu'})
                release.set()
                until(lambda: self.queue.items[0]['state'] == 'error')
                states = {i['id']:i['state'] for i in self.queue.status()['items']}
                self.assertEqual(states[first['id']], 'error')
                self.assertEqual(states[cancelled['id']], 'cancelled')
                self.assertEqual(states[last['id']], 'complete')
        finally:
            release.set()

    def test_changed_project_rejected_without_mutation(self):
        with patch.object(work_queue, 'execute') as execute, patch.object(work_queue.error_log, 'record'):
            with self.manager.guard:
                self.queue.submit('context-start', self.args)
                data = load_project(self.path, '1'); data['video_generation'] = 'changed'
                save_json(self.path/'project.json', data)
                before = (self.path/'project.json').read_bytes()
            until(lambda: self.queue.items[0]['state'] == 'error')
            execute.assert_not_called()
            self.assertEqual((self.path/'project.json').read_bytes(), before)

    def test_conflicting_job_waits_then_resumes(self):
        def execute(manager, action, data):
            with ProjectLock(self.path, write=['speech']): return {}
        with ProjectLock(self.path, read=['speech']) as held, patch.object(work_queue, 'execute', side_effect=execute):
            self.queue.submit('speech-start', self.args)
            until(lambda: '끝나면' in self.queue.items[0]['message'])
            self.assertEqual(self.queue.items[0]['state'], 'queued')
            held.close()
            until(lambda: self.queue.items[0]['state'] == 'complete')

    def test_split_queue_retains_session_source_and_current_job(self):
        from archive import split_contract
        file = self.root/'로컬 원본.mp4'
        file.write_bytes(b'original')
        source_id = 'c'*32
        split = self.manager.splitter
        split.sources[source_id] = {'path':str(file), 'name':file.name, 'duration':6,
                                    'streams':[], 'identity':split_contract.identity(file)}
        with patch('archive.split_jobs.media.boundaries', return_value={'parts':[{}, {}]}):
            queued = self.queue.submit('split-plan', {'source_id':source_id, 'points':[2]})['queued']
            self.assertEqual(queued['state'], 'queued')
            self.assertEqual(queued['source_id'], source_id)
            until(lambda: self.queue.items[0]['state'] in ('complete','error'))
        row = self.queue.items[0]
        self.assertEqual(row['state'], 'complete', row['message'])
        current = split.dispatch('current', {})['run']
        self.assertEqual(current['id'], row['run'])
        self.assertEqual(current['state'], 'ready')
        self.assertEqual(current['source']['path'], str(file))
        self.assertEqual(file.read_bytes(), b'original')
        with self.manager.guard:
            queued = self.queue.submit('split-start', {'id':current['id'], 'folder':str(self.root)})['queued']
            self.assertEqual(queued['source_id'], source_id)
            self.assertNotIn('run', queued)
            self.queue.cancel(queued['id'])

    def test_queued_automation_keeps_owner_and_order(self):
        from archive.automation import options
        queue = self.manager.automation
        entry = queue.entry(load_project(self.path, '1'), options({'steps':['audio','transcribe']}), 'saved')
        queue.change(str(self.root), lambda data: data['items'].append(entry))
        seen = []
        def step(owner, item, stage):
            seen.append(stage)
            return 'reused'
        with patch('archive.automation.steps.execute', side_effect=step), patch('archive.report_hardware.collect', return_value={}):
            self.queue.submit('queue-start', {'root':str(self.root)})
            until(lambda: self.queue.items[0]['state'] in ('complete','error'))
            self.assertEqual(self.queue.items[0]['state'], 'complete', self.queue.items[0]['message'])
            self.assertEqual(seen, ['audio','transcribe'])

    def test_http_queue_security_and_nonblocking_acceptance(self):
        import json
        from http.client import HTTPConnection
        from urllib.parse import urlsplit
        from archive.server import make_server
        server, url = make_server(self.manager)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        parsed = urlsplit(url)
        client = HTTPConnection(parsed.hostname, parsed.port, timeout=3)
        def call(action, data, origin=None):
            headers = {'Content-Type':'application/json'}
            if origin: headers['Origin'] = origin
            client.request('POST', parsed.path+'api/'+action, json.dumps(data), headers)
            response = client.getresponse()
            return response.status, json.loads(response.read())
        hold = patch.object(work_queue, 'execute', side_effect=ResourceBusy('대기 중'))
        hold.start()
        try:
            status, response = call('context-start', self.args)
            self.assertEqual(status, 200)
            self.assertEqual(response['queued']['state'], 'queued')
            self.assertNotIn('data', response['queued'])
            self.assertEqual(call('work-cancel', {'id':response['queued']['id']}, 'https://example.org')[0], 403)
            self.assertEqual(call('work-queue', {})[1]['items'][0]['state'], 'queued')
            self.assertEqual(call('work-cancel', {'id':response['queued']['id']})[1]['items'][0]['state'], 'cancelled')
        finally:
            client.close(); server.shutdown(); server.server_close(); thread.join(); hold.stop()

    def test_new_request_after_queue_drains_and_shutdown_cancels(self):
        with patch.object(work_queue, 'execute', return_value={}):
            self.queue.submit('context-start', self.args)
            until(lambda: self.queue.items[0]['state'] == 'complete')
            self.queue.submit('context-start', self.args)
            until(lambda: self.queue.items[-1]['state'] == 'complete')
            with self.manager.guard:
                self.queue.submit('context-start', self.args)
                self.queue.stopping.set()
            self.queue.close()
            self.assertEqual(self.queue.items[-1]['state'], 'cancelled')
            with self.assertRaises(Conflict): self.queue.submit('context-start', self.args)


class ConcurrentEditingTests(unittest.TestCase):
    def setUp(self):
        import test_studio_jobs
        test_studio_jobs.StudioJobs.setUp(self)
        self.other = self.root/'vod-2'
        shutil.copytree(self.path, self.other)
        data = load_project(self.path, '1'); data['vod_id'] = '2'; data['metadata']['id'] = '2'
        save_json(self.other/'project.json', data)
        self.other_args = {'root':str(self.root), 'vod_id':'2'}

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def test_other_vod_draft_and_media_while_locked_then_queued_render(self):
        from archive import clip_contract
        before = hashlib.sha256(self.file.read_bytes()).hexdigest()
        request = {'clips':[{'title':'보존 검사','start_ms':0,'end_ms':1000}]}
        with ProjectLock(self.path):
            saved = self.manager.studio.dispatch('draft', self.other_args|{'request':request,'revision':0})
            self.assertEqual(saved['revision'], 1)
            self.assertEqual(clip_contract.media(self.other, '2')['duration'], 4000)
            with self.assertRaises(Conflict):
                self.manager.studio.dispatch('draft', self.args|{'request':request,'revision':0})
            with self.assertRaises(Conflict): self.manager.deletion_preview(str(self.root), '1')
            item = self.manager.tasks.submit('studio-start', self.other_args|{'request':request})['queued']
            self.assertEqual(item['state'], 'queued')
            self.manager.studio.dispatch('draft', self.other_args|{'request':{'clips':[{'title':'나중 편집','start_ms':1000,'end_ms':2000}]},'revision':1})
            until(lambda: self.manager.tasks.items[0]['state'] in ('running','complete','error'))
        until(lambda: self.manager.tasks.items[0]['state'] in ('complete','error'), 45)
        row = self.manager.tasks.items[0]
        self.assertEqual(row['state'], 'complete', row['message'])
        self.assertEqual(self.manager.studio.job.value['request']['clips'][0]['title'], '보존 검사')
        self.assertEqual(hashlib.sha256(self.file.read_bytes()).hexdigest(), before)
        self.assertEqual(self.manager.studio.dispatch('info', self.other_args)['draft']['request']['clips'][0]['title'], '나중 편집')

    def test_split_source_in_vod_shares_project_lock(self):
        from archive.split_jobs import Splitter, source_project
        self.manager.splitter = Splitter(self.manager, self.root/'split-jobs')
        splitter = self.manager.splitter
        registered = splitter.dispatch('register', {'path':str(self.file)})
        self.assertEqual(source_project(registered['source']), self.path)
        release = threading.Event()
        original = (self.path/'project.json').read_bytes()
        try:
            with patch('archive.split_jobs.media.boundaries', side_effect=lambda *args: (release.wait(5), {})[1]):
                splitter.dispatch('plan', {'source_id':registered['source_id'], 'points':[1]})
                with self.assertRaises(Conflict): self.manager.deletion_preview(str(self.root), '1')
                release.set(); splitter.job.thread.join(5)
        finally:
            release.set()
        self.assertEqual((self.path/'project.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
