"""충돌하는 요청만 기다리고 독립 작업은 함께 실행한다. 대기 요청은 종료 시 취소한다."""
from collections import deque
import copy
import time
import threading
import uuid

from . import error_log
from .source import safe_error
from .storage import ResourceBusy, Conflict, load_project, project_path, stamp


HEAVY = {
    'start': '영상·채팅 다운로드', 'speech-start': '음성 처리',
    'voices-start': '화자 처리', 'context-start': 'AI 문맥', 'analyze': '채팅 반응 분석',
    'studio-start': '클립 영상 저장', 'studio-resume': '클립 작업 이어하기',
    'studio-scope': '부분 분석', 'studio-remote': '구간 다운로드',
    'split-plan': '분할 경계 검사', 'split-start': '영상 나누기', 'split-resume': '영상 나누기 이어하기',
    'queue-start': 'VOD 목록 자동화', 'video-quality': '영상 화질 변경',
}
LIVE = {'queued', 'starting', 'running'}


def check_download_folder(manager, action, data):
    if action == 'queue-start':
        from .automation_plan import selected
        pending = manager.automation.read(data['root'])['items']
        needs_folder = any(i['state'] in ('queued', 'running', 'paused') and
                           'download' in selected(i['options']) for i in pending)
    elif action == 'studio-resume':
        from .studio_jobs import run_file
        from .storage import read_json
        saved = read_json(run_file(project_path(data['root'], data['vod_id']), data['run']))
        needs_folder = saved.get('kind') == 'remote' and saved['state'] != 'complete'
    else:
        needs_folder = action in ('start', 'studio-remote') or (action == 'video-quality' and data.get('existing') is not None)
    if needs_folder:
        manager.require_download_library(data['root'])


def execute(manager, action, data):
    check_download_folder(manager, action, data)
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
        return change(manager, root, vod, data['expected'], data['format_id'], data.get('existing'),
                      data.get('concurrent_fragments'))
    raise ValueError('지원하지 않는 대기 작업입니다')


class WorkQueue:
    def __init__(self, manager):
        self.manager = manager
        # shortcut: 미실행 대기는 메모리에만 보관한다. 앱 재실행 후 자동 재개가 필요할 때 영속화한다.
        self.items = []
        self.active = None
        self.thread = None
        self.stopping = threading.Event()
        self.local = threading.local()
        self.runners = set()
        self.workers = []
        self.completions = deque(maxlen=512)

    def notify_complete(self, title, label):
        with self.manager.guard:
            self.completions.append(dict(id=uuid.uuid4().hex, time=int(time.time()*1000), title=title, label=label))

    def owns_thread(self):
        return bool(getattr(self.local, "owner", False))

    def track(self, kind, worker):
        self.workers = [(k, w) for k, w in self.workers if not w.closed or getattr(w, 'report_thread', None) and w.report_thread.is_alive()]
        self.workers.append((kind, worker))
        self.local.worker = worker
        return worker

    def find(self, kind, path=None, file=None):
        for k, worker in reversed(self.workers):
            owner = getattr(worker, 'path', getattr(getattr(worker, 'project', None), 'path', None))
            if k == kind and not worker.closed and (path is None or owner == path) and (file is None or getattr(worker, 'file', None) == file):
                return worker
        return None

    def busy(self):
        m = self.manager
        return bool(m.automation.running or bool(m.analysis_paths) or any(not w.closed for _, w in self.workers) or any(
            job and not job.closed for job in
            (m.job, m.speech_job, m.voice_job, m.context_job, m.import_job, m.studio.job, m.splitter.job)))

    def idle(self):
        if not self.owns_thread() and not self.manager.automation.owns_thread() and any(i['state'] in LIVE for i in self.items):
            raise Conflict('대기·실행 중인 작업이 있습니다. 작업 대기열을 먼저 완료하거나 취소하세요')

    def project_idle(self, path, *, include_queued=False):
        if self.owns_thread() or self.manager.automation.owns_thread():
            return
        states = LIVE if include_queued else ('starting', 'running')
        if any(i['state'] in states and str(path) in i['paths'] for i in self.items):
            raise Conflict('이 VOD의 대기·실행 작업이 있습니다. 작업을 완료하거나 대기열에서 취소한 뒤 변경하세요')

    def split_idle(self):
        if not self.owns_thread() and any(i['state'] in LIVE and i['action'].startswith('split-') for i in self.items):
            raise Conflict('영상 나누기의 대기 작업을 먼저 취소하세요')

    def public(self, item):
        return copy.deepcopy({k: v for k, v in item.items() if k not in ('data', 'paths', 'identity')})

    def status(self):
        with self.manager.guard:
            return {'items': [self.public(i) for i in self.items], 'busy': bool(self.busy()), 'completions': list(self.completions)}

    @staticmethod
    def identity(path):
        data = load_project(path, path.name.removeprefix('vod-'))
        stat = path.stat()
        return [stat.st_dev, stat.st_ino, data.get('created_at'), data.get('video_generation'), data.get('format_id')]

    def submit(self, action, data):
        with self.manager.guard:
            check_download_folder(self.manager, action, data)
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
            item = dict(id=uuid.uuid4().hex, action=action, label=HEAVY[action], title=title,
                        root=data.get('root'), vod_id=data.get('vod_id'), state='queued',
                        created_at=stamp(), message='사용할 자료와 실행 자리를 확인합니다',
                        paths=paths, identity=identity, data=copy.deepcopy(data))
            if action == 'speech-start':
                item['stage'] = data.get('action')
                item['label'] = {'audio': '음성 처리', 'transcribe': '전사', 'model': '전사 모델 준비'}.get(item['stage'], item['label'])
            elif action == 'start':
                item['stage'] = data.get('kind','all')
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

    def run(self):
        while not self.stopping.is_set():
            with self.manager.guard:
                for item in self.items:
                    if item['state'] != 'queued':
                        continue
                    item.update(state='starting', message='사용할 자료를 확인합니다')
                    runner = threading.Thread(target=self.run_item, args=(item,), name='work-'+item['id'], daemon=True)
                    self.runners.add(runner)
                    runner.start()
            self.stopping.wait(.2)

    def run_item(self, item):
        self.local.owner = True
        self.local.worker = None
        try:
            if self.stopping.is_set():
                return
            if item['identity'] is not None:
                from pathlib import Path
                if self.identity(Path(item['paths'][0])) != item['identity']:
                    raise Conflict('대기 중 영상 또는 프로젝트가 변경됐습니다. 현재 자료를 확인해 다시 요청하세요')
            result = execute(self.manager, item['action'], item['data'])
            worker = self.local.worker
            path = getattr(worker, 'path', getattr(getattr(worker, 'project', None), 'path', None))
            if path and item['paths'] and str(path) not in item['paths']:
                worker = None
            if item['action'] == 'video-quality' and item['data'].get('existing') is None:
                worker = None
            with self.manager.guard:
                item.update(state='running', message='실행 중: 해당 작업 화면에서 진행을 확인하세요')
                if item['action'].startswith(('studio-', 'split-')) and result.get('id'):
                    item['run'] = result['id']
            while (self.manager.automation.running if item['action'] == 'queue-start' else worker and not worker.closed) and not self.stopping.wait(.2):
                pass
            if self.stopping.is_set():
                return
            observer = getattr(worker, 'report_thread', None)
            if observer:
                observer.join()
            state = getattr(worker, 'value', {}) or {}
            if item['action'] == 'queue-start':
                state = self.manager.automation.read(item['data']['root'])
                if any(i['state'] in ('error', 'partial', 'paused') for i in state['items']):
                    state = dict(state, state='review')
            if worker and hasattr(worker, 'project'):
                tasks = worker.work.snapshot()['tasks']
                state = next((tasks[k] for k in worker.workers if tasks[k]['state'] in ('error', 'paused', 'review')), {})
            with self.manager.guard:
                item.update(state='error' if state.get('state') in ('error', 'paused', 'review', 'partial', 'cancelled') else 'complete', finished_at=stamp(),
                            message=state.get('message') or '처리가 끝났습니다. 결과 화면을 확인하세요')
                if item['state'] == 'complete' and item['action'] != 'queue-start':
                    self.notify_complete(item['title'], item['label'])
        except ResourceBusy as error:
            with self.manager.guard:
                item.update(state='cancelled' if self.stopping.is_set() else 'queued', message=str(error))
        except Exception as error:
            error_log.record('work-queue-'+item['action'], error, vod=item.get('vod_id'))
            with self.manager.guard:
                item.update(state='error', message=safe_error(error), finished_at=stamp())
        finally:
            with self.manager.guard:
                self.runners.discard(threading.current_thread())

    def close(self):
        self.stopping.set()
        with self.manager.guard:
            for item in self.items:
                if item['state'] in ('queued', 'starting'):
                    item.update(state='cancelled', message='앱 종료로 대기를 취소했습니다')
        # 실행 중인 작업의 종료와 합류는 기존 Manager.close가 맡는다.
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join()

    def close_workers(self):
        for runner in list(self.runners):
            runner.join()
        workers = [w for _, w in self.workers]
        for worker in workers:
            if not worker.closed:
                if hasattr(worker, 'cancel'):
                    worker.cancel('all') if hasattr(worker, 'project') else worker.cancel()
                else:
                    worker.stop.set()
        for worker in workers:
            if worker.thread and worker.thread.ident is not None:
                worker.thread.join()
            report = getattr(worker, 'report_thread', None)
            if report and report.ident is not None:
                report.join()
        for runner in list(self.runners):
            runner.join()
