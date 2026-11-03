"""중단된 영상의 실제 제공 화질을 바꾼다. 채팅과 기존 수신 파일은 계속 보관한다."""
import re
import uuid

from . import download_scope, source, video_replacement
from .storage import Conflict, Project, ProjectLock, load_project, project_path, save_json, stamp


def media_directory(project):
    folder = project.path/'media'
    generation = project.data.get('video_generation')
    if folder.is_symlink():
        raise Conflict('영상 폴더에 연결 경로를 사용할 수 없습니다')
    if generation is not None:
        if not isinstance(generation, str) or not re.fullmatch('[a-f0-9]{32}', generation):
            raise Conflict('영상 저장 위치를 확인하세요')
        folder = folder/generation
        if folder.is_symlink():
            raise Conflict('영상 폴더에 연결 경로를 사용할 수 없습니다')
    return folder


def sync_item(item, data):
    if data.get('video_generation') and item['format'] != data['format_id']:
        choice = next(f for f in data['metadata']['formats'] if f['id'] == data['format_id'])
        item.update(format=choice['id'], quality=choice['label'], title=data['metadata']['title'])
        if choice['height'] in (480, 720, 1080):
            item['options']['height'] = choice['height']


def change(manager, root, vod, expected, selected, existing=None):
    path = project_path(root, vod)
    base = download_scope.base_root(root)
    def eligible(data):
        complete = data['tasks']['video']['state'] == 'complete'
        if complete and existing not in ('keep','delete'):
            raise Conflict('기존 영상 파일의 보존 또는 삭제를 선택하세요')
        if not complete and existing is not None:
            raise Conflict('완료된 영상의 상태가 바뀌었습니다. 다시 확인하세요')
        if data.get('video_replacement') and data['video_replacement']['task']['state'] in ('queued','running','downloading','verifying','stopping'):
            raise Conflict('새 화질 다운로드를 먼저 중단하세요')
        if not complete and data['tasks']['video']['state'] not in ('paused', 'error', 'idle'):
            raise Conflict('영상 다운로드를 중단하고 중단 처리가 끝난 뒤 화질을 변경하세요')
        if data.get('input') and not download_scope.remote(data):
            raise Conflict('치지직에서 다운로드하는 영상만 화질을 변경할 수 있습니다')
        if expected != data['format_id'] or expected == selected:
            raise Conflict('현재 화질을 다시 확인하고 다른 화질을 선택하세요')

    eligible(load_project(path, vod))
    info = source.inspect(f'https://chzzk.naver.com/video/{vod}')
    choice = next((f for f in info['formats'] if f['id'] == selected and 0 < (f.get('height') or 0) <= 1080), None)
    if not choice:
        raise ValueError('선택한 화질은 현재 제공되지 않습니다. 화질 목록을 다시 열어주세요')

    def apply(project):
        with project.mutex:
            data = project.snapshot()
            eligible(data)
            scope = download_scope.bounds(data)
            title = data['metadata']['title']
            if scope:
                download_scope.validate(scope, info.get('duration'))
                other = download_scope.range_root(base, vod, scope, selected)
                if other != path.parent and (project_path(other, vod)/'project.json').exists():
                    raise Conflict('같은 구간·화질의 VOD가 이미 있습니다. 저장한 VOD 목록에서 해당 항목을 여세요')
                title = data['metadata'].get('source_title') or info['title']
                title = f'{title} · 구간 {download_scope.timecode(scope["start_ms"])}–{download_scope.timecode(scope["end_ms"])} · {choice["height"]}p'
            if existing is not None:
                video_replacement.stage(path, data, choice, info['formats'], existing, title)
            else:
                data['metadata'].update(title=title, formats=info['formats'])
                data.update(format_id=selected, video_generation=uuid.uuid4().hex)
                data['tasks']['video'] = dict(state='idle', assets={}, progress={},
                    message=f'{choice["label"]} 선택 · 시작하면 영상을 처음부터 받습니다')
            data['updated_at'] = stamp()
            save_json(path/'project.json', data)
            project.data = data
            return data

    def update_queue(queue):
        job = manager.job
        if job and not job.closed and job.project.path == path:
            if existing is not None:
                raise Conflict('현재 진행 중인 작업이 끝난 뒤 완료 영상의 화질을 변경하세요')
            worker = job.workers.get('video')
            if worker and worker.is_alive():
                raise Conflict('영상 중단 처리가 끝난 뒤 다시 시도하세요')
            data = apply(job.project)
        else:
            manager.speech_idle()
            with ProjectLock(path) as lock:
                data = apply(Project(path, load_project(path, vod), lock))
        for item in queue['items']:
            if item['vod'] == vod and item['state'] != 'complete' and download_scope.entry_root(str(base), item) == str(path.parent):
                sync_item(item, data)

    with manager.guard:
        manager.automation.idle()
        manager.automation.change(str(base), update_queue)
        if existing is not None:
            return manager.start(root, vod, expected, 'video')
    return manager.view(root, vod)
