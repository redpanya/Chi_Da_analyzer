"""영속 순차 목록. 앱 재시작 시 자동 실행하지 않으며 기존 작업 잠금을 공유한다."""
import copy
import threading
import uuid

from . import automation_steps as steps, speech_options
from .storage import library, project_path, ProjectLock, Conflict, load_project, create_or_load, save_json, read_json, stamp


def options(value):
    if not isinstance(value, dict) or set(value) - {'mode', 'height', 'language', 'asr_options', 'speakers_enabled', 'backend', 'thinking', 'allow_partial_chat', 'continue_voice_error', 'background'}:
        raise ValueError('자동화 설정을 확인하세요')
    result = dict(mode='download', height=0, language='ko', asr_options=speech_options.validate(),
                  speakers_enabled=False, backend='sherpa', thinking=True, allow_partial_chat=False, continue_voice_error=True) | value
    if result['mode'] not in ('download', 'analysis') or type(result['height']) is not int or result['height'] not in (0, 1080, 720, 480):
        raise ValueError('작업 범위와 화질을 확인하세요')
    if result['language'] not in ('ko', 'auto', 'ja', 'en') or result['backend'] not in ('sherpa', 'pyannote', 'fluid'):
        raise ValueError('언어·화자 모델 설정을 확인하세요')
    for key in ('speakers_enabled', 'thinking', 'allow_partial_chat', 'continue_voice_error'):
        if type(result[key]) is not bool:
            raise ValueError('자동화 선택 값을 확인하세요')
    if 'background' in result:
        from .context_background import validate
        result['background'] = validate(result['background'])
    result['asr_options'] = speech_options.validate(result['asr_options'])
    return result


class Automation:
    def __init__(self, manager):
        self.manager = manager
        self.guard = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.running = False
        self.root = None
        self.lock = None
        self.report_id = None

    def owns_thread(self):
        return self.thread is threading.current_thread()

    def dispatch(self, action, data):
        root = data['root']
        if action == 'status':
            return self.status(root)
        if action == 'add':
            return self.add(root, data['url'], data.get('options', {}))
        if action == 'add-saved':
            return self.add_saved(root, data['vod_ids'], data.get('options', {}))
        if action == 'settings':
            return self.update_settings(root, data['ids'], data.get('options', {}))
        if action == 'start':
            return self.start(root)
        if action in ('remove', 'retry'):
            return self.remove_or_retry(root, data['id'], retry=action == 'retry')
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
        if data.get('version') != 1 or not isinstance(data.get('items'), list):
            raise ValueError('작업 목록 파일을 확인하세요. 기존 파일은 보존했습니다')
        return data

    def change(self, root, fn):
        with self.guard:
            owned = self.running and self.root == str(library(root)) and self.lock is not None
            lock = None if owned else ProjectLock(self.directory(root))
            try:
                data = self.read(root)
                fn(data)
                save_json(self.directory(root) / 'queue.json', data | {'updated_at': stamp()})
                return data
            finally:
                if lock:
                    lock.close()

    def status(self, root):
        with self.guard:
            data = self.read(root)
            active = self.running and self.root == str(library(root))
            foreign = False
            if not active and data['state'] in ('running', 'stopping'):
                try:
                    def recover(value):
                        value.update(state='paused', message='이전 실행이 종료되었습니다. 이어가기를 눌러 재개하세요')
                        for item in value['items']:
                            if item['state'] == 'running':
                                item.update(state='paused', message='중단된 작업 · 완료 자료 확인 후 이어받기')
                    data = self.change(root, recover)
                except Conflict:
                    foreign = True
            return copy.deepcopy(data) | {'active': active or foreign, 'owned': active, 'root': str(library(root))}

    def add(self, root, url, settings):
        settings = options(settings)
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError('VOD 주소를 확인하세요')
        meta = self.manager.inspect(url)
        vod = meta['id']
        def append(data):
            self.check_add(data, vod)
            path = project_path(root, vod)
            with ProjectLock(path):
                if (path / 'project.json').exists():
                    project = load_project(path, vod)
                else:
                    candidates = [f for f in meta['formats'] if not settings['height'] or (f.get('height') or 0) <= settings['height']]
                    if not candidates:
                        raise ValueError('선택한 최대 해상도에 맞는 영상이 없습니다')
                    format_id = candidates[0]['id']
                    project = create_or_load(path, meta, format_id)
                data['items'].append(self.entry(project, settings, 'url'))
                self.waiting(data)
        self.change(root, append)
        return self.status(root)

    @staticmethod
    def waiting(data):
        if data['state'] not in ('running', 'stopping'):
            data.update(state='idle', message='대기 항목이 있습니다. 순차 작업 시작·이어가기를 누르세요')

    @staticmethod
    def check_add(data, vod):
        if len(data['items']) >= 100:
            raise ValueError('작업 목록은 최대 100개입니다. 완료 항목을 목록에서 제거하세요')
        if any(item['vod'] == vod and item['state'] != 'complete' for item in data['items']):
            raise Conflict('이미 미완료 목록에 있는 VOD입니다. 기존 항목의 설정 적용·이어가기 또는 목록 제거 후 다시 등록하세요')

    @staticmethod
    def entry(project, settings, source):
        tasks = project['tasks']
        video_done = tasks['video']['state'] == 'complete'
        chat_done = tasks['chat']['state'] in ('complete', 'empty', 'unavailable')
        preview = ('영상·채팅 확인 후 원음부터 필요한 단계 처리' if settings['mode'] == 'analysis' else '영상·채팅 확인 후 기존 자료 사용') if video_done and chat_done else '미완료 영상·채팅부터 준비'
        if project.get('input') and not video_done:
            preview = '내 비디오 미완료 · 같은 파일을 먼저 다시 첨부하세요'
        selected = next((f for f in project['metadata'].get('formats', []) if f['id'] == project['format_id']), {})
        quality = '내 비디오' if project.get('input') else selected.get('label') or (str(selected['height'])+'p' if selected.get('height') else '기존 등록 화질')
        return dict(id=uuid.uuid4().hex, vod=project['vod_id'], title=project['metadata']['title'],
                    format=project['format_id'], quality=quality, options=copy.deepcopy(settings), source=source,
                    preview=preview, state='queued', stage='', message='등록 순서대로 대기 중 · 실행 직전 자료 재확인', stages={}, report=None)

    def add_saved(self, root, vods, settings):
        settings = options(settings)
        if not isinstance(vods, list) or not 1 <= len(vods) <= 100:
            raise ValueError('등록할 저장 VOD를 1~100개 선택하세요')
        added, errors = [], []
        # 각 성공을 저장해 뒤 항목의 실패로 앞 등록이 사라지지 않게 한다.
        for vod in vods:
            def append(data):
                path = project_path(root, vod)
                self.check_add(data, vod)
                if not (path / 'project.json').is_file():
                    raise ValueError('이 보관함에 등록된 VOD가 없습니다')
                with ProjectLock(path):
                    data['items'].append(self.entry(load_project(path, vod), settings, 'saved'))
                    self.waiting(data)
            try:
                self.change(root, append)
                added.append(vod)
            except ValueError as error:
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
                project = load_project(project_path(root, item['vod']), item['vod'])
                updated = copy.deepcopy(settings)
                if 'background' not in settings and 'background' in item['options']:
                    updated['background'] = item['options']['background']
                item.update(options=updated, preview=self.entry(project, updated, 'saved')['preview'],
                            message='선택한 설정 적용 완료 · 기존 영상·이어받기 화질 유지')
            self.waiting(data)
        self.change(root, change)
        return self.status(root)

    def remove_or_retry(self, root, item_id, retry=False):
        def change(data):
            item = next((v for v in data['items'] if v['id'] == item_id), None)
            if not item:
                raise ValueError('목록 항목을 찾지 못했습니다')
            if item['state'] == 'running':
                raise Conflict('실행 중인 항목은 일시정지 완료 후 변경하세요')
            if retry:
                if item['state'] not in ('error', 'partial', 'paused'):
                    raise Conflict('중단·오류 항목만 다시 대기에 넣을 수 있습니다. 완료한 VOD는 새 작업으로 등록하세요')
                item.update(state='queued', message='완료 자료 확인 후 다시 진행합니다')
                self.waiting(data)
            else:
                data['items'].remove(item)
        self.change(root, change)
        return self.status(root)

    def start(self, root):
        with self.manager.guard, self.guard:
            self.manager.speech_idle()
            self.root = str(library(root))
            self.lock = ProjectLock(self.directory(root))
            try:
                data = self.read(root)
                if not any(i['state'] in ('queued', 'paused', 'running') for i in data['items']):
                    raise ValueError('대기 중인 항목이 없습니다. 오류 항목은 다시 대기에 넣어주세요')
                self.stop.clear()
                self.running = True
                self.thread = threading.Thread(target=self.run, name='sequential-vods', daemon=True)
                self.thread.start()
            except Exception:
                self.running = False
                self.lock.close()
                self.lock = None
                raise
        return self.status(root)

    def pause(self):
        self.stop.set()
        if self.running:
            self.change(self.root, lambda data: data.update(state='stopping', message='현재 단계의 중단·파일 정리를 기다립니다'))

    def close(self):
        self.pause()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join()

    def update_item(self, item_id, **values):
        def change(data):
            next(item for item in data['items'] if item['id'] == item_id).update(values)
        self.change(self.root, change)

    def run(self):
        entry = None
        try:
            self.change(self.root, lambda data: data.update(state='running', message='순차 작업 진행 중'))
            while not self.stop.is_set():
                claimed = []
                def claim(data):
                    item = next((i for i in data['items'] if i['state'] in ('queued', 'paused', 'running')), None)
                    if item:
                        item.update(state='running', message='기존 완료 자료부터 확인합니다')
                        claimed.append(copy.deepcopy(item))
                self.change(self.root, claim)
                if not claimed:
                    break
                entry = claimed[0]
                path = project_path(self.root, entry['vod'])
                self.report_id = entry.get('report') or self.manager.reports.new(self.root, entry['vod'], entry['options'])
                self.update_item(entry['id'], state='running', report=self.report_id, message='기존 완료 자료부터 확인합니다')
                stages = ['download']
                if entry['options']['mode'] == 'analysis':
                    stages += ['audio', 'transcribe'] + (['diarize'] if entry['options']['speakers_enabled'] else []) + ['reactions', 'summary']
                outcomes = {}
                try:
                    for stage in stages:
                        if self.stop.is_set():
                            raise steps.Paused()
                        self.update_item(entry['id'], stage=stage, stages=outcomes)
                        try:
                            outcomes[stage] = steps.execute(self, entry, stage)
                        except (steps.Paused, steps.Prerequisite, OSError):
                            raise
                        except Exception as error:
                            if stage != 'diarize' or not entry['options']['continue_voice_error']:
                                raise
                            outcomes[stage] = 'partial'
                            self.update_item(entry['id'], message='화자 구분 오류 · 화자 불명 상태로 요약을 계속합니다')
                        self.update_item(entry['id'], stages=dict(outcomes))
                    self.update_item(entry['id'], state='partial' if 'partial' in outcomes.values() else 'complete', message='처리 종료 · 일부 확인 필요' if 'partial' in outcomes.values() else '선택한 단계 완료')
                except (steps.Paused, steps.Prerequisite, OSError):
                    raise
                except Exception as error:
                    from .source import safe_error
                    self.update_item(entry['id'], state='error', message=safe_error(error))
                    # 사전 조건·검증 오류처럼 작업자가 생성되기 전의 실패도 기록한다.
                    token = self.manager.reports.begin(path, stage)
                    self.manager.reports.finish(path, token, stage, 'error', str(error))
                self.report_id = None
            self.change(self.root, lambda data: data.update(state='paused' if self.stop.is_set() else 'complete', message='일시정지했습니다' if self.stop.is_set() else '목록 처리 종료 · 오류·일부 완료 항목은 개별 확인하세요'))
        except (steps.Paused, steps.Prerequisite, OSError) as error:
            if entry:
                self.update_item(entry['id'], state='paused', message=str(error) or '중단했습니다. 완료 자료는 유지합니다')
                try:
                    token = self.manager.reports.begin(path, entry.get('stage') or stage)
                    self.manager.reports.safe_finish(path, token, entry.get('stage') or stage, 'paused', str(error))
                except (OSError, ValueError, UnboundLocalError):
                    pass
            self.change(self.root, lambda data: data.update(state='paused', message=str(error) or '일시정지했습니다'))
        except Exception:
            # 예상하지 못한 오류도 실행 중 상태로 방치하지 않는다.
            try:
                if entry:
                    self.update_item(entry['id'], state='paused', message='목록 기록을 확인한 뒤 이어가세요')
                self.change(self.root, lambda data: data.update(state='paused', message='목록 처리가 중단되었습니다. 저장 공간·리포트를 확인하세요'))
            except (OSError, ValueError):
                pass
        finally:
            with self.guard:
                self.lock.close()
                self.lock = None
                self.running = False
                self.report_id = None
