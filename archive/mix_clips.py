"""보관함 단위 믹스 초안과 여러 원본의 순서 지정 출력."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import re
import threading
import uuid

from . import clip_captions, clip_contract, clip_render, download_scope, processes, speech_media, studio_decorations, studio_profiles
from .source import check_cancel, safe_error
from .storage import Conflict, ProjectLock, library, load_project, project_path, read_json, save_json
from .studio_jobs import local


def workspace(root):
    base = library(root)
    if base.parent.name == '.download-ranges' and re.fullmatch('[0-9a-f]{32}', base.name):
        base = base.parent.parent
    folder = base / '믹스클립'
    if not base.is_dir() or folder.is_symlink():
        raise ValueError('믹스클립을 저장할 보관함 경로를 확인하세요')
    return folder


def draft(folder):
    file = folder / '초안.json'
    return read_json(file) if file.exists() else {'revision': 0, 'items': [], 'version': ''}


def source_path(folder, scope, vod):
    root = download_scope.checked_root(folder.parent, folder.parent / scope)
    return project_path(root, vod)


def fingerprint(path, vod):
    data = load_project(path, vod)
    file = speech_media.source(path, data)
    return speech_media.identity(file, path), data.get('input', {}).get('start_vod_ms', 0), file


def same_source(item, source):
    ident, origin, _ = source
    if ident != item['source'] or origin != item['origin']:
        raise Conflict('원본이 교체되었습니다. 이 구간을 제거한 뒤 다시 보내세요')


def add(folder, value, data):
    vod = data['vod_id']
    root = download_scope.checked_root(folder.parent, data['root'])
    scope = str(root.relative_to(folder.parent))
    path = project_path(root, vod)
    load_project(path, vod)
    with ProjectLock(path, read=['media', 'studio-draft']):
        src = clip_contract.media(path, vod)
        saved = read_json(local(path, 'draft.json'))
        if saved['revision'] != data.get('revision'):
            raise Conflict('담은 클립이 변경되었습니다. 다시 불러온 뒤 보내세요')
        request = clip_contract.validate(saved['request'], src, draft=True)
        keys = set()
        for item in value['items']:
            clip = item.get('source_clip', item['clip'])
            keys.add((item['scope'], item['vod_id'], clip['id'], clip['start_ms'], clip['end_ms']))
        added = []
        rows = None
        for clip in request['clips']:
            key = (scope, vod, clip['id'], clip['start_ms'], clip['end_ms'])
            if key in keys:
                continue
            keys.add(key)
            options = studio_profiles.effective(request, clip)
            options.update(speed='exact', sidecar=False, mode='joined', transition='cut')
            captions = []
            if options['caption']:
                if rows is None:
                    with ProjectLock(path, read=['speech','voices']):
                        rows = clip_captions.snapshot(path, vod, request['selection'], request['caption_edits'])
                    if not rows:
                        raise ValueError('자막에 사용할 완료된 전사를 선택하세요')
                from .caption_fonts import frozen_options
                options = frozen_options(options)
                captions, _ = clip_captions.cues(rows, [clip])
            added.append(dict(key=uuid.uuid4().hex, scope=scope, vod_id=vod, broadcast=src['data']['metadata']['title'],
                              origin=src['origin'], source=src['identity'], clip={k:v for k,v in clip.items() if k!='options'},
                              options=options, captions=captions))
        if added:
            value['items'].extend(added)
            persist(folder, value)
        return {'added':len(added), 'duplicates':len(request['clips'])-len(added)}


def persist(folder, value):
    value.update(revision=value['revision'] + 1, version=uuid.uuid4().hex)
    save_json(folder / '초안.json', value)


def dissolves(value):
    return value.get('transition') == 'fade' and len(value['items']) > 1


def render_version(value):
    # 기존 디졸브 결과의 파일과 다운로드 주소를 보존한다.
    if dissolves(value):
        return uuid.uuid5(uuid.UUID(value['version']), 'dissolve-pcm-f32-v1').hex
    return value['version']


def info(folder, value):
    sources = {}
    preview_keys = {}
    items = []
    for item in value['items']:
        vod, scope = item['vod_id'], item['scope']
        key = (vod, scope)
        message = ''
        preview_key = None
        try:
            if key not in sources:
                try:
                    sources[key] = fingerprint(source_path(folder, scope, vod), vod)
                except (ValueError, OSError, KeyError):
                    sources[key] = None
            if sources[key] is None:
                raise ValueError('원본 영상을 찾을 수 없습니다')
            same_source(item, sources[key])
            preview_key = preview_keys.setdefault(key, item['key'])
        except ValueError as error:
            message = str(error)
        items.append({k:item[k] for k in ('key','vod_id','broadcast','origin')} | item['clip']
                     | {'problem':message, 'preview_key':preview_key})
    return {'revision':value['revision'], 'version':render_version(value), 'items':items, 'editor_page':'mix-studio.html'}


def output(folder, version):
    if not isinstance(version, str) or not re.fullmatch('[0-9a-f]{32}', version):
        raise ValueError('저장할 믹스클립을 선택하세요')
    file = folder / f'믹스클립-{version}.mp4'
    if file.is_symlink():
        raise ValueError('믹스클립 파일 경로를 확인하세요')
    return file


def render(folder, value, stop, report):
    items = value['items']
    lossless_audio = dissolves(value)
    suffix = '.mov' if lossless_audio else '.mp4'
    with ExitStack() as stack:
        sources = {}
        for item in items:
            vod = item['vod_id']
            path = source_path(folder, item['scope'], vod)
            if path not in sources:
                load_project(path, vod)
                lock = stack.enter_context(ProjectLock(path, read=['media','studio-images']))
                src = clip_contract.media(path, vod)
                sources[path] = (lock, src)
            src = sources[path][1]
            same_source(item, (src['identity'], src['origin'], src['file']))
        temp = Path(stack.enter_context(TemporaryDirectory(dir=folder, prefix='렌더-')))
        clips, parts = [], []
        canvas = None
        def silent(**_):
            pass

        for index, item in enumerate(items):
            report(f'{index+1}/{len(items)} 구간 처리 중')
            path = source_path(folder, item['scope'], item['vod_id'])
            lock, src = sources[path]
            request = clip_contract.validate({'clips':[item['clip']], 'options':item['options']}, src)
            clip, opts = request['clips'][0], request['options']
            if 'size' in value:
                opts = opts | {'size':value['size']}
            size = clip_contract.dimensions(src, opts)
            canvas = canvas or size
            length = (clip['end_ms']-clip['start_ms'])/1000
            part = temp / f'part-{index}{suffix}'
            clip_render.encode(src, clip, opts, part, stop, lock, silent, lossless_audio=lossless_audio)
            if item['captions'] or opts['image']:
                decorated = temp / f'decorated-{index}{suffix}'
                overlay = studio_decorations.prepare(path, opts)
                clip_render.burn(part, item['captions'], size, opts, decorated, length, stop, lock, silent, overlay)
                part.unlink()
                part = decorated
            if size != canvas:
                fitted = temp / f'canvas-{index}{suffix}'
                graph = clip_render.fit('0:v:0','v',*canvas,'contain')
                clip_render.command(['-i',str(part),'-filter_complex',graph,'-map','[v]','-map','0:a:0',
                                     '-c:v','libx264','-preset','veryfast','-crf','20','-c:a','copy',str(fitted)],
                                    temp, fitted.stem, stop, lock, silent, length)
                part.unlink()
                part = fitted
            clips.append(clip)
            parts.append(part)
        report('구간 연결 및 영상 검사 중')
        result = temp / 'mix.mp4'
        total = clip_render.join(parts, clips, {'transition':value.get('transition','cut')}, result, stop, lock, silent,
                                 lossless_audio=lossless_audio)
        clip_render.verify(result, total, stop, lock, silent)
        signatures = {path:fingerprint(path, src['data']['vod_id']) for path, (_,src) in sources.items()}
        for item in items:
            same_source(item, signatures[source_path(folder, item['scope'], item['vod_id'])])
        check_cancel(stop)
        result.replace(output(folder, render_version(value)))


class MixClips:
    def __init__(self):
        self.guard = threading.RLock()
        self.jobs = {}

    def state(self, folder, version):
        if version and output(folder, version).is_file():
            return {'state':'complete','file':str(output(folder, version))}
        job = self.jobs.get(folder)
        if job and job['version'] == version and job['state'] != 'complete':
            return {k:job[k] for k in ('state','message')}
        return {'state':'idle'}

    def dispatch(self, action, data):
        folder = workspace(data['library_root'])
        with self.guard:
            if action == 'open-folder':
                file = output(folder, data.get('version'))
                if not file.is_file():
                    raise FileNotFoundError('저장한 믹스클립을 찾을 수 없습니다')
                return processes.open_folder(file.parent)
            if action == 'status':
                return self.state(folder, data['version'])
            if action == 'editor':
                from . import mix_editor
                return mix_editor.dispatch(folder, draft(folder), action, data)
            if action == 'info':
                value = draft(folder)
                result = info(folder, value)
                return result | {'job':self.state(folder, result['version'])}
            with ProjectLock(folder, write=['mix-draft']):
                value = draft(folder)
                if action == 'send':
                    return add(folder, value, data)
                if value['revision'] != data.get('revision'):
                    raise Conflict('다른 창에서 믹스 목록이 변경되었습니다. 다시 확인하세요')
                if action == 'edit':
                    from . import mix_editor
                    return mix_editor.dispatch(folder, value, action, data)
                if action == 'clear':
                    if value['items']:
                        value['items'].clear()
                        persist(folder, value)
                    return info(folder, value)
                if action in ('move','remove'):
                    rows = value['items']
                    index = next((i for i,r in enumerate(rows) if r['key']==data.get('key')), None)
                    if index is None:
                        raise ValueError('믹스 목록에서 구간을 선택하세요')
                    if action == 'move':
                        if 'to_index' in data:
                            target = data['to_index']
                        else:
                            delta = data.get('direction')
                            if type(delta) is not int or delta not in (-1,1):
                                raise ValueError('이 방향으로 이동할 수 없습니다')
                            target = index + delta
                        if type(target) is not int or not 0 <= target < len(rows):
                            raise ValueError('이 방향으로 이동할 수 없습니다')
                        if target == index:
                            return info(folder, value)
                        rows.insert(target, rows.pop(index))
                    else:
                        rows.pop(index)
                    persist(folder, value)
                    return info(folder, value)
                if action != 'render' or not value['items']:
                    raise ValueError('저장할 믹스 구간을 선택하세요')
                version = render_version(value)
                if any(r['problem'] for r in info(folder, value)['items']):
                    raise Conflict('원본을 확인할 수 없는 구간이 있습니다. 믹스 목록을 확인하세요')
                state = self.state(folder, version)
                if state['state'] in ('complete','running'):
                    return state
                prior = self.jobs.get(folder)
                if prior and prior['thread'].is_alive():
                    raise Conflict('이 보관함의 믹스클립을 저장 중입니다')
                job = {'state':'running','message':'구간 확인 중','version':version,'stop':threading.Event()}
                lock = ProjectLock(folder, write=['mix-render'])
                def run():
                    try:
                        with lock:
                            if not output(folder, version).exists():
                                render(folder, value, job['stop'], lambda msg: job.update(message=msg))
                        job.update(state='complete')
                    except Exception as error:
                        job.update(state='error',message=safe_error(error))
                job['thread'] = threading.Thread(target=run, daemon=True)
                self.jobs[folder] = job
                try:
                    job['thread'].start()
                except RuntimeError:
                    lock.close()
                    del self.jobs[folder]
                    raise
                return {'state':'running','message':job['message']}

    def close(self):
        with self.guard:
            jobs = list(self.jobs.values())
            for job in jobs:
                job['stop'].set()
        for job in jobs:
            job['thread'].join()


def preview_file(folder, key):
    item = next((i for i in draft(folder)['items'] if i['key'] == key), None)
    if not item:
        raise ValueError('믹스 목록에서 구간을 선택하세요')
    current = fingerprint(source_path(folder, item['scope'], item['vod_id']), item['vod_id'])
    same_source(item, current)
    return current[2]
