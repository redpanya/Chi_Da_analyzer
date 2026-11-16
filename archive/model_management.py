"""설정에서 현재 모델 저장 폴더의 고정 배포 파일만 관리한다."""
import base64
import hashlib
import os
import re
import stat
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

from . import context_catalog, context_model, diarization_backends as backends, diarization_run
from . import model_paths, source, speaker_tool_integrity, speaker_tools, speaker_tools_install, speech_model, speech_vad, voice_models
from .storage import Conflict, ProjectLock, ResourceBusy, read_json

LABELS = {
    'whisper': 'Whisper large-v3-turbo-q5_0', 'vad': 'Silero VAD', 'gemma': 'Gemma 4 E4B',
    'sherpa': 'sherpa-onnx 화자 구분', 'pyannote': 'pyannote Community-1', 'fluid': 'FluidAudio 화자 구분',
    'tool-sherpa': 'sherpa-onnx와 ONNX Runtime', 'tool-pyannote': 'pyannote 실행 도구',
    'tool-fluid': 'FluidAudio 실행 도구',
}
CONTEXT = {'gemma': context_model.DEFAULT_NAME}
for name in (context_model.NAME, *context_catalog.MODELS):
    if name != context_model.DEFAULT_NAME:
        CONTEXT['legacy-' + name.lower()] = name


def work_resources(kind, action, options):
    """실제 모델을 쓰는 동안 설정에서 해당 모델을 바꾸지 못하게 한다."""
    if action == 'suggest':
        return ['model-gemma', 'model-sherpa', 'model-tool-sherpa']
    if action in ('transcribe', 'retranscribe-original') or kind == 'speech' and action == 'model':
        resources = ['model-whisper']
        if action == 'transcribe' and options.get('vad', 'standard') != 'off':
            resources += ['model-vad', 'model-tool-sherpa']
        return resources
    if kind == 'voices':
        backend = options.get('backend', 'sherpa')
        return ['model-tool-' + backend] + (['model-' + backend] if action in ('prepare', 'diarize') else [])
    return []


def model_resource(key):
    return 'model-' + key.replace('.', '-')


def context_resource(name):
    return model_resource(next(key for key, model in CONTEXT.items() if model == name))


def checked(root, path):
    if path == root or not path.is_relative_to(root) or '..' in path.relative_to(root).parts:
        raise ValueError('모델 저장 폴더 안의 파일만 사용할 수 있습니다')
    for entry in (path, *path.parents):
        try:
            info = entry.lstat()
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError('모델 저장 경로에 연결 파일이나 연결 폴더가 있습니다')
        if entry == root:
            break
    return path


def matching_parts(part):
    # 해시 검사 실패 후 기존 다운로드 코드가 보관한 사본.
    return [item for item in part.parent.glob(part.name + '.invalid-*')
            if item.name.removeprefix(part.name + '.invalid-').isdecimal()]


def model_files(root, key):
    if key in CONTEXT:
        name = CONTEXT[key]
        target = checked(root, context_model.model_path(name))
        part = target.with_suffix('.part')
        return [target, part, context_model.verified_path(name), *matching_parts(part)]
    if key == 'whisper':
        target = checked(root, speech_model.model_path())
        part = target.with_suffix('.part')
        files = [target, part, *matching_parts(part)]
        marker = checked(root, root/'verified.json')
        if marker.is_file() and marker_matches(marker, 'sha256', speech_model.SHA256):
            files.append(marker)
        return files
    if key == 'vad':
        return [root/'silero-vad.onnx', root/'silero-vad.download']
    home = checked(root, backends.home(key))
    if key == 'sherpa':
        files = [home/name for name in voice_models.FILES]
        files += [file.with_name(file.name + '.part') for file in files]
        files += [home/name for name in ('segmentation.onnx', 'segmentation-LICENSE', 'segmentation-README.md',
                                         'diarization-verified.json')]
        # 이전 화자 검증 파일에는 다른 모델의 정보가 함께 저장된 경우가 있다.
        marker = checked(root, home/'verified.json')
        if marker.is_file():
            try:
                if set(read_json(marker)) == {*voice_models.FILES, 'segmentation.onnx'}:
                    files.append(marker)
            except (ValueError, TypeError):
                pass
        return files
    files = [home/'verified.json']
    if key == 'fluid':
        files.append(home/'.fluidaudio-revision')
    for spec in backends.catalog(key)['files']:
        name = spec['name']
        files.extend((home/name, home/(name + '.part')))
        if key == 'pyannote':
            # snapshot_download(local_dir=...)의 고정 파일별 캐시와 미완성 파일.
            metadata = home/'.cache/huggingface/download'/(name + '.metadata')
            digest = base64.urlsafe_b64encode(hashlib.sha1(metadata.name.encode()).digest()).decode()
            files.extend((metadata, metadata.with_suffix('.lock'),
                          metadata.with_name(f"{digest}.{spec['sha256'] or spec['git_sha1']}.incomplete")))
    return files


def marker_matches(path, key, expected):
    try:
        return read_json(path).get(key) == expected
    except (OSError, ValueError, AttributeError):
        return False


def tool_assets(root, backend):
    home = checked(root, speaker_tools.home(backend))
    versions = checked(root, home/'versions')
    folders = []
    if versions.is_dir():
        for item in versions.iterdir():
            if re.fullmatch(r'\.removing-[0-9a-f]{32}', item.name) and checked(root, item).is_dir():
                folders.append(item)
            elif re.fullmatch(r'[0-9a-f]{32}', item.name):
                manifest = checked(root, item/'tool.json')
                try:
                    data = read_json(manifest)
                except (OSError, ValueError):
                    continue
                if isinstance(data, dict) and (data.get('backend'), data.get('platform'), data.get('entry')) == (
                        backend, speaker_tools.platform_id(), speaker_tools.entry_name(backend)):
                    folders.append(item)
    if home.is_dir():
        folders.extend(item for item in home.glob('.removing-.install-*')
                       if re.fullmatch(r'\.removing-\.install-[a-z0-9_]{8}', item.name) and checked(root, item).is_dir())
        for item in home.glob('.install-*'):
            if (re.fullmatch(r'\.install-[a-z0-9_]{8}', item.name) and checked(root, item).is_dir()
                    and all(file.name in ('download.zip', 'package', 'check.log') for file in item.iterdir())):
                folders.append(item)
    return [home/'active.json', home/'last-install.log'], folders


@lru_cache(maxsize=32)
def version_size(folder, mtime):
    # 설치 버전 폴더는 게시 후 불변이다. 1초마다 런타임 전체를 순회하지 않는다.
    total = 0
    for parent, dirs, files in os.walk(folder, followlinks=False):
        if os.name == 'nt':
            dirs[:] = [name for name in dirs if not (Path(parent)/name).lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT]
        for name in files:
            info = (Path(parent)/name).lstat()
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
    return total


@lru_cache(maxsize=8)
def vad_verified(path, size, mtime):
    return size == speech_vad.SIZE and speech_model.digest(path) == speech_vad.SHA256


def assets(root, key):
    if key.startswith('tool-'):
        files, dirs = tool_assets(root, key[5:])
    else:
        files, dirs = model_files(root, key), []
    present_files = []
    for file in files:
        checked(root, file)
        if file.exists():
            if not file.is_file():
                raise ValueError('모델 파일 위치에 폴더가 있습니다')
            present_files.append(file)
    return present_files, dirs


def item(root, key):
    tool = key.startswith('tool-')
    backend = key[5:] if tool else key
    supported = speaker_tools.supported(backend) if backend in backends.BACKENDS else True
    result = {'id': key, 'label': LABELS.get(key) or CONTEXT[key], 'type': 'tool' if tool else 'model',
              'supported': supported, 'ready': False, 'present': False, 'bytes': 0, 'expected_bytes': None,
              'can_delete': False, 'can_install': False}
    try:
        files, dirs = assets(root, key)
        size = sum(file.stat().st_size for file in files)
        for folder in dirs:
            if folder.name.removeprefix('.removing-').startswith('.install-'):
                part = checked(root, folder/'download.zip')
                if part.is_file():
                    size += part.stat().st_size
            else:
                size += version_size(folder, folder.stat().st_mtime_ns)
        if tool:
            ready = bool(speaker_tools.managed(backend))
        elif key == 'vad':
            file = root/'silero-vad.onnx'
            ready = file in files and vad_verified(file, file.stat().st_size, file.stat().st_mtime_ns)
            result['expected_bytes'] = speech_vad.SIZE
        else:
            if key in CONTEXT:
                status = context_model.status(CONTEXT[key])
            elif key == 'whisper':
                status = speech_model.status()
            else:
                status = backends.status(key)
            ready = status['ready']
            result['expected_bytes'] = status['bytes']
        present = bool(files or dirs)
        result.update(ready=ready, present=present, bytes=size, can_delete=present,
                      can_install=supported and not ready and key in LABELS)
    except (ValueError, OSError) as error:
        result['problem'] = source.safe_error(error)
    return result


def install(key, stop, lock, update):
    if key == 'whisper':
        marker = model_paths.root()/'verified.json'
        if marker.is_file() and not marker_matches(marker, 'sha256', speech_model.SHA256):
            raise ValueError('같은 위치에 다른 검증 파일이 있습니다. 모델 전용 폴더를 선택하세요')
        speech_model.prepare(stop, update)
    elif key == 'vad':
        speech_vad.prepare(stop, update)
    elif key == 'gemma':
        context_model.prepare(stop, update)
    elif key.startswith('tool-'):
        speaker_tools_install.ensure(key[5:], stop, lock, update)
    else:
        with tempfile.TemporaryDirectory() as folder:
            diarization_run.prepare(key, Path(folder), stop, lock, update)


def delete(root, key):
    if key.startswith('tool-'):
        guard = ProjectLock(speaker_tools.home(key[5:]))
    elif key in CONTEXT:
        guard = ProjectLock(context_model.home())
    elif key in ('whisper', 'vad'):
        guard = ProjectLock(root, write=['speech-models' if key == 'whisper' else 'speech-vad'])
    else:
        guard = ProjectLock(backends.home(key))
    with guard:
        files, dirs = assets(root, key)
        # 소유권이 확인된 폴더를 먼저 같은 위치에서 표시한다. 파일이 잠겨 일부만
        # 지워져도 다음 실행에서 tool.json 없이 남은 폴더를 찾아 다시 지울 수 있다.
        for folder in sorted(dirs, key=lambda path: not path.name.startswith('.removing-')):
            if not folder.name.startswith('.removing-'):
                pending = checked(root, folder.with_name('.removing-' + folder.name))
                if pending.exists():
                    raise Conflict('이전 도구 삭제가 진행 중입니다. 다시 시도하세요')
                folder.rename(pending)
                folder = pending
            try:
                speaker_tool_integrity.remove_tree(folder)
            finally:
                version_size.cache_clear()
        for file in files:
            file.unlink(missing_ok=True)


class ModelLibrary:
    def __init__(self, guard):
        self.guard = guard
        self.reset()
        self.thread = None
        self.stop = threading.Event()

    def reset(self):
        self.job = {'state': 'idle', 'id': '', 'action': '', 'message': '', 'progress': {}}

    def busy(self):
        return self.job['state'] in ('running', 'stopping')

    def view(self, root):
        rows = [item(root, key) for key in (*LABELS, *(key for key in CONTEXT if key != 'gemma'))]
        return {'root': str(root), 'items': [row for row in rows if row['id'] in LABELS or row['present']],
                'job': dict(self.job)}

    def request(self, data):
        with self.guard:
            model_paths.available()
            root = model_paths.root()
            if not data:
                return self.view(root)
            if set(data) != {'action', 'id', 'root'} or data['root'] != str(root):
                raise Conflict('모델 저장 폴더가 바뀌었습니다. 목록을 다시 확인하세요')
            key, action = data['id'], data['action']
            if not isinstance(key, str) or key not in LABELS and key not in CONTEXT:
                raise ValueError('지원하는 모델을 선택하세요')
            if action == 'cancel':
                if self.busy() and self.job['action'] == 'install' and self.job['id'] == key:
                    self.stop.set()
                    self.job.update(state='stopping', message='설치를 중단하고 있습니다')
                return self.view(root)
            if action not in ('install', 'delete'):
                raise ValueError('지원하지 않는 모델 작업입니다')
            if self.busy():
                raise Conflict('모델 관리 작업이 진행 중입니다')
            entry = item(root, key)
            if not entry['can_' + action]:
                raise Conflict(entry.get('problem') or '설치 상태가 바뀌었습니다. 목록을 다시 확인하세요')
            resource = model_resource(key)
            try:
                lock = ProjectLock(root, write=[resource], read=['model-tool-pyannote'] if key == 'pyannote' and action == 'install' else [])
            except ResourceBusy:
                raise Conflict('이 모델을 사용하는 작업이 진행 중입니다. 작업이 끝난 후 다시 시도하세요') from None
            self.stop = threading.Event()
            self.job = {'id': key, 'action': action, 'state': 'running', 'message': '설치 중' if action == 'install' else '삭제 중', 'progress': {}}
            self.thread = threading.Thread(target=self.run, args=(root, key, action, lock), name='model-management', daemon=True)
            try:
                self.thread.start()
            except BaseException:
                lock.close()
                self.job.update(state='error', message='모델 관리 작업을 시작할 수 없습니다')
                raise
            return self.view(root)

    def update(self, **values):
        with self.guard:
            if not self.stop.is_set():
                self.job.update({k: v for k, v in values.items() if k in ('message', 'progress')})

    def run(self, root, key, action, lock):
        try:
            with lock:
                if action == 'install':
                    install(key, self.stop, lock, self.update)
                else:
                    delete(root, key)
            state, message = 'complete', '설치를 완료했습니다' if action == 'install' else '삭제했습니다'
        except Exception as error:
            state = 'stopped' if isinstance(error, source.Cancelled) or self.stop.is_set() else 'error'
            message = source.safe_error(error)
        with self.guard:
            self.job.update(state=state, message=message, progress={})

    def close(self):
        with self.guard:
            self.stop.set()
            thread = self.thread
        if thread:
            thread.join()
