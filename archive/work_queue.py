"""앱 안의 무거운 요청을 직렬 실행한다. 대기 요청은 종료 시 취소한다."""
import copy
import threading
import uuid

from . import error_log
from .source import safe_error
from .storage import Conflict, load_project, project_path, stamp


HEAVY = {
    'start': '영상·채팅 다운로드', 'speech-start': '음성 처리',
    'voices-start': '화자 처리', 'context-start': 'AI 문맥', 'analyze': '채팅 반응 분석',
    'studio-start': '클립 영상 저장', 'studio-resume': '클립 작업 이어하기',
    'studio-scope': '부분 분석', 'studio-remote': '구간 다운로드',
    'split-plan': '분할 경계 검사', 'split-start': '영상 나누기', 'split-resume': '영상 나누기 이어하기',
    'queue-start': 'VOD 목록 자동화', 'video-quality': '영상 화질 변경',
}
LIVE = {'queued', 'starting', 'running'}


def execute(manager, action, data):
    if action.startswith('studio-'):
        return manager.studio.dispatch(action[7:], data)
    if action.startswith('split-'):
        return manager.splitter.dispatch(action[6:], data)
    if action == 'queue-start':
        return manager.automation.start(data['root'])
    root, vod = data['root'], data['vod_id']
    if action == 'start':
        return manager.start(root, vod, data['format_id'], data['kind'])
    if action == 'speech-start':
        return manager.speech_start(root, vod, data['action'], data.get('track'), data.get('language', 'ko'),
                                    data.get('input_kind', 'original'), data.get('sam_profile'), data.get('asr_options'))
    if action == 'voices-start':
        return manager.voices_start(root, vod, data['action'], data.get('options', {}))
    if action == 'context-start':
        return manager.context_start(root, vod, data['action'], data.get('options'))
    if action == 'analyze':
        return manager.analyze(root, vod, data.get('settings', {}), data.get('allow_partial', False))
    if action == 'video-quality':
        from .video_quality import change
        return change(manager, root, vod, data['expected'], data['format_id'], data.get('existing'))
    raise ValueError('지원하지 않는 대기 작업입니다')


class WorkQueue:
    def __init__(self, manager):
        self.manager = manager
        # shortcut: 미실행 대기는 메모리에만 보관한다. 앱 재실행 후 자동 재개가 필요할 때 영속화한다.
        self.items = []
        self.active = None
        self.thread = None
        self.stopping = threading.Event()

    def owns_thread(self):
        return self.thread is threading.current_thread()

    def busy(self):
        m = self.manager
        return (m.automation.running or m.analysis_path is not None or any(
            job and not job.closed for job in
            (m.job, m.speech_job, m.voice_job, m.context_job, m.import_job, m.studio.job, m.splitter.job)))

    def idle(self):
        if not self.owns_thread() and not self.manager.automation.owns_thread() and any(i['state'] in LIVE for i in self.items):
            raise Conflict('대기·실행 중인 작업이 있습니다. 작업 대기열을 먼저 완료하거나 취소하세요')

    def project_idle(self, path):
        if self.owns_thread() or self.manager.automation.owns_thread():
            return
        if any(i['state'] in LIVE and str(path) in i['paths'] for i in self.items):
            raise Conflict('이 VOD의 대기·실행 작업이 있습니다. 작업을 완료하거나 대기열에서 취소한 뒤 변경하세요')

    def split_idle(self):
        if not self.owns_thread() and any(i['state'] in LIVE and i['action'].startswith('split-') for i in self.items):
            raise Conflict('영상 나누기의 대기 작업을 먼저 취소하세요')

    def public(self, item):
        return copy.deepcopy({k: v for k, v in item.items() if k not in ('data', 'paths', 'identity')})

    def status(self):
        with self.manager.guard:
            return {'items': [self.public(i) for i in self.items], 'busy': bool(self.busy())}

    @staticmethod
    def identity(path):
        data = load_project(path, path.name.removeprefix('vod-'))
        stat = path.stat()
        return [stat.st_dev, stat.st_ino, data.get('created_at'), data.get('video_generation'), data.get('format_id')]

    def submit(self, action, data):
        with self.manager.guard:
            if self.stopping.is_set():
                raise Conflict('실행기를 종료하는 중입니다')
            for item in self.items:
                if item['state'] in LIVE and item['action'] == action and item['data'] == data:
                    return {'queued': self.public(item)}
            if sum(i['state'] in LIVE for i in self.items) >= 100:
                raise Conflict('대기 작업은 최대 100개입니다. 완료 후 추가하세요')
            paths, identity, title, split_source_id = [], None, '', None
            if 'vod_id' in data:
                path = project_path(data['root'], data['vod_id'])
                paths = [str(path)]
                if (path/'project.json').exists() or action != 'start':
                    project = load_project(path, data['vod_id'])
                    identity = self.identity(path)
                    title = project['metadata'].get('title', '')
            elif action == 'queue-start':
                from .download_scope import entry_root
                queue = self.manager.automation.read(data['root'])
                paths = [str(project_path(entry_root(data['root'], i), i['vod'])) for i in queue['items']
                         if i['state'] in ('queued', 'paused', 'running')]
            elif action.startswith('split-'):
                from .split_jobs import source_project
                if action == 'split-plan':
                    split_source_id = data['source_id']
                    source = self.manager.splitter.sources[split_source_id]
                else:
                    split_state = self.manager.splitter.state(data['id'])
                    split_source_id, source = split_state['source_id'], split_state['source']
                owner = source_project(source)
                title = source.get('name', '')
                if owner:
                    paths, identity = [str(owner)], self.identity(owner)
            # 빈 슬롯은 기존 응답을 유지한다. 오래 걸리는 채팅 분석만 별도 스레드로 시작한다.
            if action != 'analyze' and not self.busy() and not any(i['state'] in LIVE for i in self.items):
                return execute(self.manager, action, data)
            item = dict(id=uuid.uuid4().hex, action=action, label=HEAVY[action], title=title,
                        root=data.get('root'), vod_id=data.get('vod_id'), state='queued',
                        created_at=stamp(), message='앞 작업이 끝나면 자동으로 시작합니다',
                        paths=paths, identity=identity, data=copy.deepcopy(data))
            if split_source_id:
                item['source_id'] = split_source_id
            self.items = [i for i in self.items if i['state'] in LIVE] + [i for i in self.items if i['state'] not in LIVE][-30:]
            self.items.append(item)
            if not self.thread or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.run, name='heavy-work-queue', daemon=True)
                self.thread.start()
            return {'queued': self.public(item)}

    def cancel(self, id):
        with self.manager.guard:
            item = next((i for i in self.items if i['id'] == id), None)
            if not item or item['state'] != 'queued':
                raise Conflict('대기 중인 작업만 취소할 수 있습니다. 실행된 작업은 해당 화면에서 중단하세요')
            item.update(state='cancelled', message='시작 전에 취소했습니다')
            return self.status()

    def worker(self, action):
        m = self.manager
        if action.startswith('studio-'): return m.studio.job
        if action.startswith('split-'): return m.splitter.job
        return {'start': m.job, 'video-quality': m.job, 'speech-start': m.speech_job,
                'voices-start': m.voice_job, 'context-start': m.context_job}.get(action)

    def run(self):
        while not self.stopping.is_set():
            with self.manager.guard:
                item = next((i for i in self.items if i['state'] == 'queued'), None)
                if item is not None and not self.busy():
                    self.active = item
                    item.update(state='starting', message='작업 준비 중')
                else:
                    item = None
            if item is None:
                self.stopping.wait(.2)
                continue
            try:
                if item['identity'] is not None:
                    from pathlib import Path
                    if self.identity(Path(item['paths'][0])) != item['identity']:
                        raise Conflict('대기 중 영상 또는 프로젝트가 변경됐습니다. 현재 자료를 확인해 다시 요청하세요')
                result = execute(self.manager, item['action'], item['data'])
                worker = self.worker(item['action'])
                path = getattr(worker, 'path', getattr(getattr(worker, 'project', None), 'path', None))
                if path and str(path) not in item['paths']:
                    worker = None
                if item['action'] == 'video-quality' and item['data'].get('existing') is None:
                    worker = None
                with self.manager.guard:
                    item.update(state='running', message='실행 중 · 해당 작업 화면에서 진행을 확인하세요')
                    if item['action'].startswith(('studio-', 'split-')) and result.get('id'):
                        item['run'] = result['id']
                while self.busy() and not self.stopping.wait(.2):
                    pass
                if self.stopping.is_set():
                    return
                observer = getattr(worker, 'report_thread', None)
                if observer:
                    observer.join()
                state = getattr(worker, 'value', {}) or {}
                if worker and item['action'] in ('speech-start', 'voices-start'):
                    from . import speech_store, voice_store
                    state = (speech_store if item['action'] == 'speech-start' else voice_store).state(worker.path)
                if item['action'] == 'queue-start':
                    state = self.manager.automation.read(item['data']['root'])
                    if any(i['state'] in ('error', 'partial', 'paused') for i in state['items']):
                        state = dict(state, state='review')
                if worker and hasattr(worker, 'project'):
                    tasks = worker.work.snapshot()['tasks'].values()
                    state = next((v for v in tasks if v['state'] in ('error', 'paused', 'review')), {})
                with self.manager.guard:
                    item.update(state='error' if state.get('state') in ('error', 'paused', 'review') else 'complete',
                                message=state.get('message') or '처리가 끝났습니다. 결과 화면을 확인하세요')
            except Exception as error:
                error_log.record('work-queue-'+item['action'], error, vod=item.get('vod_id'))
                with self.manager.guard:
                    item.update(state='error', message=safe_error(error))
            finally:
                with self.manager.guard:
                    self.active = None

    def close(self):
        self.stopping.set()
        with self.manager.guard:
            for item in self.items:
                if item['state'] == 'queued':
                    item.update(state='cancelled', message='앱 종료로 대기를 취소했습니다')
        # 실행 중인 작업의 종료와 합류는 기존 Manager.close가 맡는다.
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join()
