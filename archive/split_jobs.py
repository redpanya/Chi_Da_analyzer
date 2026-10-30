"""독립 영상 분할 작업·기록. 보관함 프로젝트나 모델이 필요하지 않다."""
from . import error_log
import copy
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid
from . import runtime, processes, split_contract as contract, split_media as media, split_render, split_deletion, split_draft, split_audio
from .source import Cancelled, safe_error
from .storage import Conflict, ProjectLock, read_json, save_json, stamp


class Splitter:
    def __init__(self, manager, root=None):
        self.manager = manager
        self.root = Path(root) if root else runtime.SUPPORT/'video-split'
        self.sources = {}
        self.job = None
        self.audio_preview = split_audio.Preview()

    def idle(self):
        if self.job and not self.job.closed:
            raise Conflict('영상 나누기 작업 중입니다. 영상 나누기 메뉴에서 완료하거나 중단하세요')

    def close(self):
        if self.job and not self.job.closed:
            self.job.stop.set(); self.job.thread.join()
        self.audio_preview.close()

    def file(self, id):
        file = self.root/contract.run_id(id)/'manifest.json'
        if self.root.is_symlink() or file.parent.is_symlink() or file.is_symlink():
            raise ValueError('작업 기록에 연결 경로를 사용할 수 없습니다')
        return file

    def state(self, id):
        file = self.file(id)
        if self.job and not self.job.closed and self.job.file == file:
            result = self.job.snapshot()
        else:
            result = read_json(file)
            if result['state'] in ('planning', 'running'):
                result.update(state='paused', message='이전 실행이 종료됐습니다. 완료 파일을 보존하며 다시 시도할 수 있습니다')
        self.sources[result['source_id']] = result['source']
        return result

    def dispatch(self, action, data):
        if action == 'audio-preview':
            source_id = contract.run_id(data.get('source_id'))
            return self.audio_preview.prepare(source_id, self.sources[source_id], data.get('track'), data.get('at'))
        if action == 'draft-get':
            return split_draft.read(self.root)
        if action == 'status':
            return self.state(data['id'])
        if action == 'list':
            result = []
            for file in sorted(self.root.glob('*/manifest.json'), key=lambda f: f.stat().st_mtime, reverse=True):
                try:
                    value = self.state(file.parent.name)
                    result.append({k: value[k] for k in ('id', 'created_at', 'state', 'message', 'source_id')} | {'name': value['source']['name']})
                except (OSError, ValueError, KeyError):
                    continue
            query=str(data.get('query','')).casefold()
            result=[r for r in result if query in (r['name']+' '+r['created_at']).casefold()]
            offset=max(0,int(data.get('offset',0)));limit=min(100,max(1,int(data.get('limit',30))))
            return {'runs':result[offset:offset+limit],'total':len(result),'offset':offset,'limit':limit}
        if action == 'stop':
            with self.manager.guard:
                if self.job and self.job.value['id'] == data.get('id') and not self.job.closed:
                    self.job.stop.set()
            return self.state(data['id'])
        if action == 'pick':
            from .split_picker import choose
            return {'path': choose(data.get('folder') is True)}
        if action == 'open-folder':
            state = self.state(data['id'])
            folder = contract.local_path(state['folder'], directory=True)
            if (folder.stat().st_dev, folder.stat().st_ino) != tuple(state['folder_identity']):
                raise ValueError('출력 폴더가 변경되었습니다')
            if os.name == 'nt': os.startfile(str(folder))
            else: processes.popen(['/usr/bin/open', str(folder)])
            return {'ok': True}
        with self.manager.guard:
            self.manager.speech_idle()
            if action == 'register':
                source = media.inspect(data.get('path'), threading.Event())
                id = uuid.uuid4().hex; self.sources[id] = source
                return {'source_id': id, 'source': source}
            lock = ProjectLock(self.root)
            try:
                if action == 'draft-save':
                    try:return split_draft.save(self.root,data,self.sources)
                    finally:lock.close()
                if action in ('delete-preview', 'delete'):
                    try:
                        file = self.file(data['id'])
                        sources = list(self.sources.values())
                        for record in self.root.glob('*/manifest.json'):
                            try:
                                sources.append(read_json(self.file(record.parent.name))['source'])
                            except (OSError, ValueError, KeyError):
                                continue
                        if action == 'delete-preview':
                            return split_deletion.preview(file, sources)
                        result = split_deletion.delete(file, data.get('token'), sources)
                        if self.job and self.job.file == file:
                            self.job = None
                        return result
                    finally:
                        lock.close()
                elif action == 'plan':
                    source_id = contract.run_id(data.get('source_id'))
                    source = self.sources[source_id]
                    requested = contract.points(data.get('points'), source['duration'])
                    audio = split_audio.selection(source, data.get('audio_selection'))
                    id = uuid.uuid4().hex
                    value = {'id': id, 'created_at': stamp(), 'source_id': source_id, 'source': source,
                             'requested': requested, 'audio_selection': audio, 'plan': None, 'outputs': {}, 'elapsed_seconds': 0, 'state': 'planning'}
                elif action in ('start', 'resume'):
                    value = self.state(data['id'])
                    if value.get('deleted_output_folder'):
                        raise Conflict('삭제 중인 작업입니다. 작업 삭제로 남은 기록을 정리하세요')
                    if value['state'] == 'complete':
                        lock.close(); return value
                    contract.unchanged(value['source'])
                    if not value.get('plan'):
                        value['state'] = 'planning'
                    else:
                        if not value.get('folder'):
                            base = contract.local_path(data.get('folder'), directory=True)
                            folder = Path(tempfile.mkdtemp(prefix=contract.safe_stem(value['source']['name'])+'_분할_', dir=base))
                            value.update(folder=str(folder), folder_identity=[folder.stat().st_dev, folder.stat().st_ino])
                        value['state'] = 'running'
                else:
                    raise ValueError('지원하지 않는 영상 나누기 요청입니다')
                self.job = Work(self.file(value['id']), copy.deepcopy(value), lock)
                self.job.update(message='분할 경계를 확인합니다' if value['state'] == 'planning' else '분할을 준비합니다', progress=0)
                self.job.thread.start()
                return self.job.snapshot()
            except BaseException:
                lock.close(); raise

    def media_file(self, source_id=None, run=None, index=None):
        if source_id:
            return contract.unchanged(self.sources[contract.run_id(source_id)])
        value = self.state(run)
        if not isinstance(index, str) or not index.isdecimal():
            raise ValueError('완료 파일을 선택하세요')
        record = value['outputs'][index]
        file = contract.inside(value['folder'], record['name'])
        if contract.identity(file) != record['identity']:
            raise ValueError('완료 파일이 변경됐습니다')
        return file


class Work:
    def __init__(self, file, value, lock):
        self.file, self.value, self.lock = file, value, lock
        self.stop = threading.Event(); self.closed = False
        self.started = time.monotonic(); self.elapsed = value.get('elapsed_seconds', 0); self.last_save = 0
        self.guard = threading.RLock()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def snapshot(self):
        with self.guard:
            return copy.deepcopy(self.value) | {'elapsed_seconds': round(self.elapsed+time.monotonic()-self.started, 1)}

    def update(self, **values):
        with self.guard:
            self.value.update(values, updated_at=stamp(), elapsed_seconds=round(self.elapsed+time.monotonic()-self.started, 1))
            if set(values) <= {'progress', 'message', 'processed_seconds'} and time.monotonic()-self.last_save < .5:
                return
            save_json(self.file, self.value); self.last_save = time.monotonic()

    def run(self):
        try:
            if self.value['state'] == 'planning':
                plan = media.boundaries(self.value['source'], self.value['requested'], self.stop, self.update)
                self.update(plan=plan, state='ready', progress=0, message='실제 분할 시각을 확인한 뒤 저장을 시작하세요')
            else:
                split_render.render(self)
                self.update(state='complete', progress=1, message='분할 저장과 트랙·길이·시작/끝 검사 완료')
        except Exception as error:
            if not self.stop.is_set() and not isinstance(error,Cancelled): error_log.record('video-split',error)
            try:
                self.update(state='paused' if self.stop.is_set() or isinstance(error, Cancelled) else 'error',
                            message='중단했습니다. 완료 파일을 보존했습니다' if self.stop.is_set() else safe_error(error))
            except OSError:
                pass
        finally:
            self.lock.close(); self.closed = True
