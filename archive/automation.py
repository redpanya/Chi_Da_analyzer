from .storage import ResourceBusy
"""영속 순차 목록. 앱 재시작 시 자동 실행하지 않으며 기존 작업 잠금을 공유한다."""
import copy
from . import error_log
import threading
import uuid
from types import SimpleNamespace

from . import automation_steps as steps, speech_options, automation_summary, automation_plan, download_scope
from .source import Cancelled, fragment_concurrency
from .storage import library, project_path, ProjectLock, Conflict, load_project, create_or_load, save_json, read_json, stamp


def options(value):
    if not isinstance(value, dict) or set(value) - {'mode', 'steps', 'height', 'download_range', 'concurrent_fragments', 'language', 'asr_options', 'speakers_enabled', 'backend', 'thinking', 'allow_partial_chat', 'continue_voice_error', 'background', 'summary_modes'}:
        raise ValueError('작업 설정을 확인하세요')
    result = dict(mode='download', height=480, concurrent_fragments=1, language='ko', asr_options=speech_options.validate(),
                  speakers_enabled=False, backend='sherpa', thinking=True, allow_partial_chat=False, continue_voice_error=True) | value
    result['concurrent_fragments'] = fragment_concurrency(result['concurrent_fragments'])
    if result['mode'] not in ('download', 'analysis') or type(result['height']) is not int or result['height'] not in (0, 1080, 720, 480):
        raise ValueError('작업 범위와 화질을 확인하세요')
    # 구버전의 '제공 최고 화질' 요청도 신규 등록에서는 1080p를 넘지 않는다.
    if result['height'] == 0:
        result['height'] = 1080
    if result['language'] not in ('ko', 'auto', 'ja', 'en') or result['backend'] not in ('sherpa', 'pyannote', 'fluid'):
        raise ValueError('언어·화자 모델 설정을 확인하세요')
    for key in ('speakers_enabled', 'thinking', 'allow_partial_chat', 'continue_voice_error'):
        if type(result[key]) is not bool:
            raise ValueError('자동화 선택 값을 확인하세요')
    if 'background' in result:
        from .context_background import validate
        result['background'] = validate(result['background'])
    result['asr_options'] = speech_options.validate(result['asr_options'])
    result['steps'] = automation_plan.selected(result)
    result['download_range'] = download_scope.validate(result.get('download_range'))
    if result['download_range'] and 'download' not in result['steps']:
        raise ValueError('구간 다운로드를 사용하려면 영상·채팅 다운로드를 선택하세요')
    result['speakers_enabled'] = 'diarize' in result['steps']
    result['mode'] = 'download' if result['steps'] == ['download'] else 'analysis'
    result['summary_modes'] = automation_summary.validate(result.get('summary_modes', ['detail']), 'context' in result['steps'])
    return result


def completion_message(items,paused=False):
    labels={'complete':'완료','partial':'일부 완료','error':'오류','paused':'중단','queued':'대기'}
    counts={key:sum(r.get('state')==key for r in items) for key in labels}
    detail=' · '.join(f'{label} {counts[key]}개' for key,label in labels.items() if counts[key])
    return ('일시정지' if paused else '목록 처리 종료')+' · '+(detail or '처리 항목 없음')


class Automation:
    def __init__(self, manager):
        self.manager = manager
        self.guard = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.running = False
        self.root = None
        self.lock = None
        self.changed = threading.Condition(self.guard)
        self.local = threading.local()
        self.active = {}
        self.entry_stops = {}
        self.held = set()
        self.download_owner = None
        self.stop_reason = ''

    @property
    def report_id(self):
        return getattr(self.local, 'report_id', None)

    def owns_thread(self):
        return getattr(self.local, 'worker', False)

    def is_processing(self, path):
        with self.guard:
            return path in self.active.values()

    def dispatch(self, action, data):
        root = data['root']
        if action == 'status':
            return self.status(root)
        if action == 'add':
            return self.add(root, data['url'], data.get('options', {}))
        if action == 'add-saved':
            return self.add_saved(root, data['vod_ids'], data.get('options', {}), data.get('source_root'))
        if action == 'settings':
            return self.update_settings(root, data['ids'], data.get('options', {}))
        if action == 'start':
            return self.start(root)
        if action in ('remove', 'retry'):
            return self.remove_or_retry(root, data['id'], retry=action == 'retry')
        if action == 'pause-item':
            with self.changed:
                event = self.entry_stops.get(data['id'])
                if str(library(root)) != self.root or event is None:
                    raise Conflict('현재 실행 중인 목록 항목이 아닙니다')
                event.set()
                self.changed.notify_all()
            return self.status(root)
        if action == 'pause':
            if str(library(root)) != self.root or not self.running:
                raise Conflict('이 실행기에서 진행 중인 목록이 아닙니다')
            self.pause()
            return self.status(root)
        raise ValueError('알 수 없는 순차 작업 요청입니다')

    def idle(self):
        if self.running and not self.owns_thread():
            raise Conflict('순차 작업이 진행 중입니다. 목록에서 일시정지한 뒤 개별 작업을 시작하세요')

    def directory(self, root):
        target = library(root) / '.automation'
        if target.is_symlink():
            raise Conflict('작업 목록에 연결 폴더를 사용할 수 없습니다')
        return target

    def read(self, root):
        file = self.directory(root) / 'queue.json'
        data = read_json(file) if file.exists() else {'version': 1, 'state': 'idle', 'message': '', 'items': []}
        if data.get('version') != 1 or not isinstance(data.get('items'), list) or not isinstance(data.get('results', []), list):
            raise ValueError('작업 목록 파일을 확인하세요. 기존 파일은 보존했습니다')
        return data

    def organize(self, root, data, *, check_projects=False):
        pending, results, present = [], {}, {}
        base = str(library(root))
        for item in [*data.get('results', []), *data['items']]:
            key = (item.get('project_root') or base, item['vod'])
            if check_projects and item['id'] not in self.active:
                if key not in present:
                    try:
                        manifest = project_path(download_scope.entry_root(root, item), item['vod']) / 'project.json'
                        manifest.stat()
                    except FileNotFoundError:
                        present[key] = False
                    except (ValueError, OSError):
                        present[key] = True  # 권한 또는 경로 검사 실패는 삭제로 간주하지 않는다.
                    else:
                        present[key] = True
                if not present[key]:
                    continue
            if item['state'] == 'complete':
                results[key] = item
            else:
                pending.append(item)
        return data | {'items':pending, 'results':list(results.values())}

    def change(self, root, fn, *, check_projects=False):
        with self.guard:
            owned = self.running and self.root == str(library(root)) and self.lock is not None
            lock = None if owned else ProjectLock(self.directory(root))
            try:
                data = self.organize(root, self.read(root), check_projects=check_projects)
                fn(data)
                data = self.organize(root, data)
                save_json(self.directory(root) / 'queue.json', data | {'updated_at': stamp()})
                if owned:
                    self.changed.notify_all()
                return data
            finally:
                if lock:
                    lock.close()

    def status(self, root):
        with self.guard:
            data = self.read(root)
            organized = self.organize(root, data, check_projects=True)
            if data['items'] != organized['items'] or data.get('results', []) != organized['results']:
                try:
                    data = self.change(root, lambda _: None, check_projects=True)
                except ResourceBusy:
                    data = organized
            else:
                data = organized
            active = self.running and self.root == str(library(root))
            foreign = False
            if not active and data['state'] in ('running', 'stopping'):
                try:
                    def recover(value):
                        if value['state'] not in ('running', 'stopping'):
                            return
                        value.update(state='paused', message='이전 실행이 종료되었습니다. 이어가기를 눌러 재개하세요')
                        for item in value['items']:
                            if item['state'] == 'running':
                                item.update(state='paused', message='중단된 작업 · 완료 자료 확인 후 이어받기')
                    data = self.change(root, recover)
                except Conflict:
                    foreign = True
            view=copy.deepcopy(data)
            if data['state']=='complete':view['message']=completion_message(data['items'] + data['results'])
            return view | {'active': active or foreign, 'owned': active, 'root': str(library(root))}

    def add(self, root, url, settings):
        settings = options(settings)
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError('VOD 주소를 확인하세요')
        meta = self.manager.inspect(url)
        vod = meta['id']
        def append(data):
            target, project = download_scope.prepare(root, meta, settings)
            self.check_add(data, vod, target, str(library(root)))
            data['items'].append(self.entry(project, settings, 'url') | {'project_root':target, 'source_root':str(library(root))})
            self.waiting(data)
        self.change(root, append, check_projects=True)
        return self.status(root)

    @staticmethod
    def waiting(data):
        if data['state'] not in ('running', 'stopping'):
            data.update(state='idle', message='대기 항목이 있습니다. 순차 작업 시작·이어가기를 누르세요')

    @staticmethod
    def check_add(data, vod, target=None, base=None):
        if sum(item['state'] != 'complete' for item in data['items']) >= 100:
            raise ValueError('미완료 작업 목록은 최대 100개입니다. 항목을 처리하거나 목록에서 제거하세요')
        if any(item['vod'] == vod and (item.get('project_root') or base) == (target or base) and item['state'] != 'complete' for item in data['items']):
            raise Conflict('이미 미완료 목록에 있는 VOD입니다. 기존 항목의 설정 적용·이어가기 또는 목록 제거 후 다시 등록하세요')

    @staticmethod
    def entry(project, settings, source):
        tasks = project['tasks']
        video_done = tasks['video']['state'] == 'complete'
        chat_done = tasks['chat']['state'] in ('complete', 'empty', 'unavailable')
        preview = '선택한 단계만 처리 · 일치하는 완료 자료는 재사용'
        if 'download' not in automation_plan.selected(settings):
            preview += ' · 미선택 단계의 자료가 없으면 해당 항목에 안내'
        elif not (video_done and chat_done):
            preview += ' · 미완료 영상·채팅부터 준비'
        if project.get('input') and not download_scope.remote(project) and not video_done:
            preview = '내 비디오 미완료 · 같은 파일을 먼저 다시 첨부하세요'
        selected = next((f for f in project['metadata'].get('formats', []) if f['id'] == project['format_id']), {})
        quality = '내 비디오' if project.get('input') and not download_scope.remote(project) else selected.get('label') or (str(selected['height'])+'p' if selected.get('height') else '기존 등록 화질')
        return dict(id=uuid.uuid4().hex, vod=project['vod_id'], title=project['metadata']['title'],
                    format=project['format_id'], quality=quality, options=copy.deepcopy(settings), source=source,
                    preview=preview, state='queued', stage='', message='등록 순서대로 대기 중 · 실행 직전 자료 재확인', stages={}, report=None)

    def add_saved(self, root, vods, settings, source_root=None):
        settings = options(settings)
        source_root = str(download_scope.checked_root(root, source_root))
        if not isinstance(vods, list) or not 1 <= len(vods) <= 100:
            raise ValueError('등록할 저장 VOD를 1~100개 선택하세요')
        added, errors = [], []
        # 각 성공을 저장해 뒤 항목의 실패로 앞 등록이 사라지지 않게 한다.
        for vod in vods:
            def append(data):
                path = project_path(source_root, vod)
                if not (path / 'project.json').is_file():
                    raise ValueError('이 보관함에 등록된 VOD가 없습니다')
                with ProjectLock(path):
                    source = load_project(path, vod)
                target, project = download_scope.prepare(root, source['metadata'], settings, source_root)
                self.check_add(data, vod, target, str(library(root)))
                data['items'].append(self.entry(project, settings, 'saved') | {'project_root':target, 'source_root':source_root})
                self.waiting(data)
            try:
                self.change(root, append, check_projects=True)
                added.append(vod)
            except ValueError as error:
                error_log.record('queue-register', error, vod=vod)
                errors.append({'vod': vod, 'message': str(error)})
        return self.status(root) | {'added': added, 'errors': errors}

    def update_settings(self, root, ids, settings):
        settings = options(settings)
        if not isinstance(ids, list) or not ids or len(ids) > 100 or any(not isinstance(i, str) for i in ids):
            raise ValueError('설정을 적용할 대기 항목을 선택하세요')
        def change(data):
            selected = [i for i in data['items'] if i['id'] in ids]
            if self.running or data['state'] in ('running', 'stopping') or len(selected) != len(set(ids)) or any(
                    i['state'] != 'queued' or i.get('report') or i.get('stages') or i.get('stage') for i in selected):
                raise Conflict('실행 이력이 없는 대기 항목만 설정을 바꿀 수 있습니다. 순차 작업을 먼저 일시정지하세요')
            for item in selected:
                project = load_project(project_path(download_scope.entry_root(root,item), item['vod']), item['vod'])
                updated = copy.deepcopy(settings)
                if 'background' not in settings and 'background' in item['options']:
                    updated['background'] = item['options']['background']
                target, project = download_scope.prepare(root, project['metadata'], updated, item.get('source_root',root))
                others = {'items':[v for v in data['items'] if v['id']!=item['id']]}
                self.check_add(others,item['vod'],target,str(library(root)))
                replacement = self.entry(project, updated, item['source'])
                item.update({k:replacement[k] for k in ('title','format','quality','options','preview')}, project_root=target,
                            message='선택한 작업 설정 적용 완료 · 기존 자료 보존')
            self.waiting(data)
        self.change(root, change)
        return self.status(root)

    def remove_or_retry(self, root, item_id, retry=False):
        def change(data):
            item = next((v for v in data['items'] if v['id'] == item_id), None)
            if not item:
                if retry:
                    raise Conflict('이어갈 등록 항목이 없습니다. 완료한 VOD는 새 작업으로 등록하세요')
                raise ValueError('목록 항목을 찾지 못했습니다')
            if item['state'] == 'running' or item_id in self.active:
                raise Conflict('실행 중인 항목은 일시정지 완료 후 변경하세요')
            if retry:
                if item['state'] not in ('error', 'partial', 'paused'):
                    raise Conflict('중단·오류 항목만 다시 대기에 넣을 수 있습니다. 완료한 VOD는 새 작업으로 등록하세요')
                item.update(state='queued', message='완료 자료 확인 후 다시 진행합니다')
                self.waiting(data)
            else:
                data['items'].remove(item)
        with self.guard:
            self.change(root, change)
            if self.root == str(library(root)):
                self.held.discard(item_id)
        return self.status(root)

    def start(self, root):
        with self.manager.guard, self.guard:
            if self.running: raise ResourceBusy('VOD 순차 작업이 끝나면 실행합니다')
            self.root = str(library(root))
            self.lock = ProjectLock(self.directory(root))
            try:
                data = self.organize(root, self.read(root), check_projects=True)
                if not any(i['state'] in ('queued', 'paused', 'running') for i in data['items']):
                    raise ValueError('대기 중인 항목이 없습니다. 오류 항목은 다시 대기에 넣어주세요')
                self.stop_reason = ''
                self.stop.clear()
                self.held.clear()
                self.running = True
                self.thread = threading.Thread(target=self.run, name='automation-queue', daemon=True)
                self.thread.start()
            except Exception:
                self.running = False
                self.lock.close()
                self.lock = None
                raise
        return self.status(root)

    def stop_all(self):
        self.stop.set()
        for event in self.entry_stops.values():
            event.set()
        self.changed.notify_all()

    def pause(self):
        with self.changed:
            if self.running and not self.stop.is_set():
                self.stop_all()
                self.change(self.root, lambda data: data.update(state='stopping', message='진행 중인 작업을 정리하고 있습니다'))

    def close(self):
        self.pause()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join()

    def update_item(self, item_id, **values):
        def change(data):
            next(item for item in data['items'] if item['id'] == item_id).update(values)
        self.change(self.root, change)

    def release_download(self, item_id):
        with self.changed:
            if self.download_owner == item_id:
                self.download_owner = None
                self.changed.notify_all()

    def run(self):
        with self.changed:
            try:
                self.change(self.root, lambda data: data.update(state='running', message='등록한 작업을 처리하고 있습니다'), check_projects=True)
                while True:
                    for entry in self.read(self.root)['items']:
                        if self.stop.is_set():
                            break
                        item_id = entry['id']
                        if item_id in self.active or item_id in self.held or entry['state'] not in ('queued', 'paused', 'running'):
                            continue
                        needs_download = 'download' in automation_plan.selected(entry['options'])
                        if needs_download and self.download_owner is not None:
                            continue
                        root = download_scope.entry_root(self.root, entry)
                        path = project_path(root, entry['vod'])
                        if path in self.active.values():
                            continue
                        self.update_item(item_id, state='running', message='기존 완료 자료부터 확인합니다')
                        self.active[item_id] = path
                        self.entry_stops[item_id] = threading.Event()
                        if needs_download:
                            self.download_owner = item_id
                        try:
                            threading.Thread(target=self.run_entry, args=(entry, root, path),
                                             name='automation-'+item_id, daemon=True).start()
                        except Exception:
                            del self.active[item_id]
                            del self.entry_stops[item_id]
                            self.release_download(item_id)
                            self.update_item(item_id, state='paused', message='작업을 시작하지 못했습니다')
                            raise
                    if not self.active:
                        break
                    self.changed.wait()
            except Exception as error:
                error_log.record('queue-worker', error)
                self.stop_reason = '목록 기록과 저장 공간을 확인한 뒤 이어가세요'
                self.stop_all()
            finally:
                self.changed.wait_for(lambda: not self.active)
                try:
                    self.change(self.root, lambda data: data.update(
                        state='paused' if self.stop.is_set() else 'complete',
                        message=self.stop_reason or completion_message(data['items'] + data['results'], self.stop.is_set())))
                finally:
                    self.lock.close()
                    self.lock = None
                    self.running = False

    def run_entry(self, entry, root, path):
        self.local.worker = True
        execution = SimpleNamespace(manager=self.manager, root=self.root, stop=self.entry_stops[entry['id']])
        stage = ''
        try:
            self.local.report_id = entry.get('report') or self.manager.reports.new(root, entry['vod'], entry['options'])
            self.update_item(entry['id'], report=self.report_id)
            outcomes = {}
            try:
                from .video_quality import sync_item
                # 프로젝트 저장 직후 종료된 경우에도 예전 화질로 다시 시작하지 않는다.
                sync_item(entry, load_project(path, entry['vod']))
                stages = automation_plan.sequence(entry['options'])
                for stage in stages:
                    if execution.stop.is_set():
                        raise steps.Paused()
                    self.update_item(entry['id'], stage=stage, stages=outcomes)
                    try:
                        waiting_for = None
                        while True:
                            if execution.stop.is_set(): raise steps.Paused()
                            try:
                                outcomes[stage] = steps.execute(execution, entry, stage)
                                if execution.stop.is_set(): raise steps.Paused()
                                break
                            except Cancelled as error:
                                raise steps.Paused() from error
                            except ResourceBusy as busy:
                                if waiting_for != str(busy):
                                    waiting_for = str(busy)
                                    self.update_item(entry['id'], message=waiting_for)
                                execution.stop.wait(.25)
                    except (steps.Paused, steps.Prerequisite, steps.MissingInput, OSError):
                        raise
                    except Exception as error:
                        if stage != 'diarize' or not entry['options']['continue_voice_error']:
                            raise
                        error_log.record('queue-'+stage,error,path=path)
                        outcomes[stage] = 'partial'
                        self.update_item(entry['id'], message='화자 구분 오류 · 화자 불명 상태로 요약을 계속합니다')
                    self.update_item(entry['id'], stages=dict(outcomes))
                    if outcomes[stage] == 'complete':
                        label = {'download':'영상과 채팅 다운로드', 'audio':'원음 추출', 'transcribe':'전사', 'diarize':'화자 구분', 'reactions':'채팅 반응 분석', 'summary':'상세 문맥', 'timestamps':'타임스탬프', 'clips':'클립 후보'}[stage]
                        self.manager.tasks.notify_complete(entry.get('title') or entry['vod'], label)
                    if stage == 'download':
                        self.release_download(entry['id'])
                self.update_item(entry['id'], state='partial' if 'partial' in outcomes.values() else 'complete', finished_at=stamp(), message='처리 종료 / 일부 확인 필요' if 'partial' in outcomes.values() else '선택한 단계 완료')
            except (steps.Paused, steps.Prerequisite, OSError):
                raise
            except Exception as error:
                error_log.record('queue-stage',error,path=path)
                from .source import safe_error
                self.update_item(entry['id'], state='error', message=safe_error(error))
                # 사전 조건·검증 오류처럼 작업자가 생성되기 전의 실패도 기록한다.
                report_stage, report_settings = automation_summary.report(stage)
                token = self.manager.reports.begin(path, report_stage, report_settings)
                self.manager.reports.finish(path, token, report_stage, 'error', str(error))
        except (steps.Paused, steps.Prerequisite, OSError) as error:
            with self.changed:
                self.held.add(entry['id'])
                if not isinstance(error, steps.Paused):
                    self.stop_all()
                    if str(error) and not self.stop_reason:
                        self.stop_reason = str(error)
            if not isinstance(error, steps.Paused):
                error_log.record('queue-prerequisite', error, path=path)
            self.update_item(entry['id'], state='paused', message=str(error) or '중단했습니다. 완료 자료는 유지합니다')
            if self.report_id and stage:
                try:
                    report_stage, report_settings = automation_summary.report(stage)
                    token = self.manager.reports.begin(path, report_stage, report_settings)
                    self.manager.reports.safe_finish(path, token, report_stage, 'paused', str(error))
                except (OSError, ValueError):
                    pass
        except Exception as error:
            error_log.record('queue-worker', error, path=path)
            with self.changed:
                self.stop_all()
            self.update_item(entry['id'], state='paused', message='목록 기록을 확인한 뒤 이어가세요')
        finally:
            with self.changed:
                self.release_download(entry['id'])
                del self.active[entry['id']]
                del self.entry_stops[entry['id']]
                self.changed.notify_all()
