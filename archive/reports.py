"""작업과 독립된 로컬 성능 이력. 원문 로그는 제출 리포트에 포함하지 않는다."""
import copy
import threading
import time
import uuid

from . import report_hardware, report_schema, speech_store, voice_store, context_job, analysis_store, compute
from .storage import project_path, load_project, read_json, save_json, stamp, Conflict


def folder(path):
    target = path / 'diagnostics' / 'reports'
    if any(p.is_symlink() for p in (path / 'diagnostics', target)):
        raise Conflict('리포트 경로에 연결 폴더를 사용할 수 없습니다')
    return target


def options(value=None):
    value = value or {}
    asr = value.get('asr_options') or {}
    return dict(language=value.get('language', 'ko'), vad=asr.get('vad', 'standard'),
                speaker_backend=value.get('backend', 'none') if value.get('speakers_enabled', False) else 'none',
                thinking=value.get('thinking', True), hint_characters=len(asr.get('prompt', '')),
                compute_requested=compute.mode() if __import__('sys').platform == 'win32' else 'platform_default',
                compute_actual='unknown', speech_model='large-v3-turbo-q5_0', summary_model='gemma-4-E4B-it-Q4_K_M')


def state(path, stage):
    if stage == 'download':
        data = load_project(path, path.name[4:])
        tasks = data['tasks']
        statuses = [task['state'] for task in tasks.values()]
        status = 'complete' if all(s in ('complete', 'empty', 'unavailable') for s in statuses) else 'error' if 'error' in statuses else 'paused' if 'paused' in statuses else 'review' if 'review' in statuses else 'running'
        return {'state': status, 'message': ' / '.join(str(t.get('message', '')) for t in tasks.values())}
    return (speech_store.state if stage in ('audio', 'transcribe', 'model') else voice_store.state if stage == 'diarize' else context_job.state)(path)


def counts(path, stage, job=None):
    result = {}
    data = load_project(path, path.name[4:])
    result['video_seconds'] = data['tasks']['video'].get('verification', {}).get('duration') or data['metadata'].get('duration')
    if stage == 'transcribe':
        run = speech_store.manifest(path)
        if run:
            rows = speech_store.segments(path, run)
            result.update(transcript_segments=len(rows), transcript_characters=sum(len(r['text']) for r in rows),
                          transcript_processed_seconds=run['processed_ms'] / 1000)
    if stage in ('download', 'reactions') and data['tasks']['chat'].get('assets', {}).get('jsonl'):
        total = characters = 0
        for row in analysis_store.rows(path, data):
            total += 1
            characters += len(row.get('text') or '')
        result.update(chat_messages=total, chat_characters=characters)
    if stage == 'summary' and job:
        source = (getattr(job, 'input', None) or {}).get('source', {})
        for key, name in [('speech', 'speech'), ('chat', 'chat')]:
            result[f'summary_input_{name}_characters'] = sum(len(r.get('text', '')) for r in source.get(key, []))
        run = context_job.state(path).get('full_run')
        file = context_job.local(path, f'runs/{run}/measurements.json') if run else None
        if file and file.exists():
            saved = read_json(file)
            result.update({key: saved[key] for key in report_schema.COUNTS & saved.keys()})
    return result


class Reports:
    def __init__(self, manager):
        self.manager = manager
        self.guard = threading.RLock()
        self.sessions = {}
        self.active = {}
        self.warning = ''

    def new(self, root, vod, settings=None):
        path = project_path(root, vod)
        report = dict(schema=2, policy=report_schema.POLICY, report_id=uuid.uuid4().hex, vod_id=vod, app_version='0.19.0',
                      hardware=report_hardware.collect(), options=options(settings), stages=[], counts={})
        local = dict(payload=report, created_at=stamp(), updated_at=stamp(), events=[], details=[], revision=0)
        with self.guard:
            save_json(folder(path) / (report['report_id'] + '.json'), local)
        return report['report_id']

    def session(self, path):
        automation = self.manager.automation
        if automation.owns_thread() and automation.report_id:
            return automation.report_id
        key = str(path)
        if key not in self.sessions:
            self.sessions[key] = self.new(path.parent, path.name[4:])
        return self.sessions[key]

    def read(self, root, vod, report_id):
        if not isinstance(report_id, str) or len(report_id) != 32 or any(c not in '0123456789abcdef' for c in report_id):
            raise ValueError('리포트 번호가 올바르지 않습니다')
        return read_json(folder(project_path(root, vod)) / (report_id + '.json'))

    def edit(self, path, report_id, fn):
        with self.guard:
            value = self.read(path.parent, path.name[4:], report_id)
            fn(value)
            value.update(updated_at=stamp(), revision=value['revision'] + 1)
            save_json(folder(path) / (report_id + '.json'), value)

    def begin(self, path, stage, settings=None):
        with self.guard:
            report_id = self.session(path)
            index = []
            def change(value):
                index.append(len(value['payload']['stages']))
                if index[0] >= 300:
                    raise ValueError('이 실행의 리포트가 가득 찼습니다. 앱 재실행 후 새 리포트를 사용하세요')
                if settings:
                    value['payload']['options'].update(settings)
                value['payload']['stages'].append(dict(stage=stage, state='running', seconds=0, error_code='none'))
                value['events'].append(dict(at=stamp(), stage=stage, state='running'))
            self.edit(path, report_id, change)
            started = time.monotonic()
            self.active[(report_id, index[0])] = started
            return report_id, index[0], started

    def finish(self, path, token, stage, status, detail='', job=None):
        report_id, index, started = token
        try:
            measured = counts(path, stage, job)
        except (OSError, ValueError, KeyError, TypeError):
            measured = {}
            detail += ' · 일부 처리량 미계측'
        def change(value):
            value['payload']['stages'][index].update(state=status, seconds=round(time.monotonic() - started, 3),
                error_code={'error': 'task_failed', 'paused': 'interrupted', 'partial': 'needs_review'}.get(status, 'none'))
            value['payload']['counts'].update(measured)
            if job:
                execution = state(path, stage).get('compute') or {}
                backend = execution.get('backend')
                if backend in ('cpu', 'vulkan', 'metal'):
                    value['payload']['options']['compute_actual'] = backend
            value['events'].append(dict(at=stamp(), stage=stage, state=status))
            if detail:
                value['details'].append(dict(stage=stage, message=detail[:2000]))  # 로컬 화면만 사용한다.
        self.edit(path, report_id, change)
        with self.guard:
            self.active.pop((report_id, index), None)

    def safe_finish(self, *args):
        try:
            self.finish(*args)
        except (OSError, ValueError, KeyError, TypeError):
            self.warning = '성능 기록 일부를 저장하지 못했습니다. 분석 결과는 별도로 유지합니다'
        finally:
            with self.guard:
                self.active.pop(args[1][:2], None)

    def watch(self, job, stage, settings=None):
        path = job.project.path if stage == 'download' else job.path
        try:
            token = self.begin(path, stage, settings)
            token = token[:2] + (getattr(job, 'report_started', token[2]),)
            self.active[token[:2]] = token[2]
        except (OSError, ValueError):
            self.warning = '리포트 기록을 시작하지 못했습니다. 처리 결과는 별도로 유지합니다'
            return
        def observe():
            previous = None
            try:
                while True:
                    current = state(path, stage)
                    phase = (current.get('state'), current.get('message'))
                    if phase != previous:
                        def event(value):
                            value['events'].append(dict(at=stamp(), stage=stage, state=phase[0], message=str(phase[1] or '')[:1000]))
                            value['events'] = value['events'][-1500:]
                        self.edit(path, token[0], event)
                        previous = phase
                    if job.closed:
                        break
                    time.sleep(.5)
                result = {'complete': 'complete', 'review': 'partial', 'paused': 'paused'}.get(current['state'], 'error')
                self.finish(path, token, stage, result, current.get('message', ''), job)
            except (OSError, ValueError, KeyError, TypeError):
                self.warning = '일부 성능 기록을 저장하지 못했습니다. 원래 작업 상태를 확인하세요'
                with self.guard:
                    self.active.pop(token[:2], None)
        job.report_thread = threading.Thread(target=observe, daemon=True, name='report-observer')
        job.report_thread.start()

    def skipped(self, path, stage, skipped=False):
        token = self.begin(path, stage)
        self.finish(path, token, stage, 'skipped' if skipped else 'reused')

    def list(self, root, vod):
        result = []
        for file in sorted(folder(project_path(root, vod)).glob('*.json'), reverse=True):
            try:
                value = read_json(file)
                result.append(dict(id=value['payload']['report_id'], created_at=value['created_at'], updated_at=value['updated_at']))
            except (OSError, ValueError, KeyError):
                continue
        return sorted(result, key=lambda r: r['created_at'], reverse=True)

    def snapshot(self, root, vod, report_id):
        with self.guard:
            value = self.read(root, vod, report_id)
            payload = copy.deepcopy(value['payload'])
            # 이전 리포트는 디스크에 덮어쓰지 않고 내보내는 사본만 현재 형식으로 보완한다.
            if payload.get('schema') == 1 and payload.get('policy') == '2026-10-18.1':
                if 'vod_id' in payload:
                    raise ValueError('이전 리포트의 형식이 올바르지 않습니다')
                payload.update(schema=2, policy=report_schema.POLICY, vod_id=vod)
            if payload.get('vod_id') != vod:
                raise ValueError('리포트의 VOD 번호가 선택한 VOD와 일치하지 않습니다')
            # 종료 시각을 모르는 중단된 실행은 시간을 추정하지 않는다.
            for index, stage in enumerate(payload['stages']):
                if stage['state'] == 'running':
                    started = self.active.get((report_id, index))
                    if started is None:
                        stage.update(state='paused', seconds=None, error_code='interrupted')
                    else:
                        stage['seconds'] = round(time.monotonic() - started, 3)
            report_schema.validate(payload)
            return value | {'payload': payload, 'warning': self.warning}
