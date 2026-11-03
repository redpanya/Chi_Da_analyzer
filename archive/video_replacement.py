"""검증이 끝난 영상만 교체하고, 분석이 참조하는 방송 시간축을 보존한다."""
from pathlib import Path
import re
import threading
import uuid

from . import task_timing, media_timeline, replacement_timeline
from .source import check_cancel
from .storage import Conflict, asset_path, read_json, save_json, stamp


def transfer_tasks(data):
    pending = data.get('video_replacement')
    return data['tasks'] | {'video': pending['task']} if pending else data['tasks']


def analysis_duration(data):
    return data.get('analysis_video', {}).get('duration', data['tasks']['video'].get(
        'verification', {}).get('duration', data['metadata'].get('duration', 0)))


def logical_source(data, actual):
    binding = data.get('analysis_video') or {}
    return binding['source'] if binding.get('playback') == actual else actual


def _file_info(path, relative):
    file = asset_path(path, relative)
    stat = file.stat()
    return {'file': str(file.relative_to(path)), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def _owned_media(path, relative):
    parts = Path(relative).parts
    if (len(parts) not in (2, 3) or parts[0] != 'media'
            or (len(parts) == 3 and not re.fullmatch('[a-f0-9]{32}', parts[1]))
            or not re.fullmatch(r'original\.mp4|range\.mp4|playback(?:\.tmp|-[0-9a-f]{32})?\.mp4', parts[-1])):
        raise Conflict('기존 영상의 파일 경로를 확인하세요')
    file = path.joinpath(*parts)
    if any((path.joinpath(*parts[:i])).is_symlink() for i in range(1, len(parts)+1)):
        raise Conflict('연결 파일은 삭제할 수 없습니다')
    return file


def stage(path, data, choice, formats, policy, title):
    task = data['tasks']['video']
    assets = {key:task['assets'][key] for key in ('original','playback')}
    for relative in assets.values():
        _owned_media(path, relative)
    old_files = {key:_file_info(path, relative) for key,relative in assets.items()}
    data['video_replacement'] = {
        'generation':uuid.uuid4().hex, 'format_id':choice['id'], 'label':choice['label'],
        'formats':formats, 'title':title, 'policy':policy, 'old_files':old_files,
        'task':{'state':'idle','assets':{},'progress':{},'message':'새 영상 다운로드 준비'}
    }


def cleanup(path, data):
    """교체 커밋 후에만 실행한다. 파일이 열려 있으면 다음 복구 때 다시 시도한다."""
    pending = data.get('video_cleanup')
    if not pending:
        return False
    active = data['tasks']['video']
    if active['state'] != 'complete':
        return False
    try:
        for key in ('original','playback'):
            actual = _file_info(path, active['assets'][key])
            proven = active['verification']['files'][key]
            if any(actual[k] != proven[k] for k in ('bytes','mtime_ns')):
                return False
    except (KeyError, OSError, ValueError):
        return False
    # 과거 JSON의 '/'와 Windows의 '\'도 같은 재생 파일을 가리킨다.
    reserved = {path / relative for relative in active['assets'].values()}
    for version in data.get('saved_video_versions', []):
        reserved.update(path / relative for relative in version['assets'].values())
    remaining = []
    for info in pending:
        try:
            relative = info['file']
            file = _owned_media(path, relative)
            if not file.exists():
                continue
            if file in reserved or _file_info(path, relative) != info:
                raise Conflict('파일이 변경되어 삭제를 보류합니다')
            file.unlink()
        except (OSError, ValueError):
            remaining.append(info)
    if remaining == pending:
        return False
    if remaining:
        data['video_cleanup'] = remaining
    else:
        data.pop('video_cleanup')
    return True


def verified_download(path, data):
    """같은 교체 시도에서 전체 검사를 마친 파일만 최종 판정에 다시 쓴다."""
    pending = data['video_replacement']
    generation = pending['generation']
    if not re.fullmatch('[a-f0-9]{32}', generation):
        raise Conflict('영상 저장 위치를 확인하세요')
    scope = data.get('download_range')
    name = 'range.mp4' if scope else 'original.mp4'
    original = _owned_media(path, str(Path('media',generation,name)))
    folder = original.parent
    try:
        proof = read_json(folder/('range-verification.json' if scope else 'verification.json'))
        if proof['decode_exit_code'] != 0 or not re.fullmatch('[a-f0-9]{64}',proof['original_sha256']):
            return None
        if scope:
            if proof['range_ms'] != [scope['start_ms'],scope['end_ms']]:
                return None
        else:
            source = read_json(folder/'source.json')
            if (source['id'],source['format_id']) != (data['vod_id'],pending['format_id']) or any(folder.glob('original.mp4.part*')):
                return None
        assets = {}
        for key in ('original','playback'):
            info = proof['files'][key]
            relative = str(Path(info['path']).relative_to(path))
            file = _owned_media(path, relative)
            if (file.parent != folder or ((key=='original' or scope) and file!=original)
                    or not file.is_file() or info['bytes']<=0 or media_timeline.identity(file)!=info):
                return None
            assets[key] = relative
        return dict(verification=proof, assets=assets, progress={'downloaded_bytes':proof['files']['original']['bytes'],
                    'total_bytes':proof['files']['original']['bytes']})
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        return None


class ReplacementProject:
    """수신 작업에만 새 세대의 상태를 보여 주고 재생·분석에는 완료본을 제공한다."""
    def __init__(self, project):
        self.project = project
        self.path, self.lock = project.path, project.lock
        self.stop = threading.Event()

    def download(self, receive, stop):
        self.stop = stop
        completed = verified_download(self.path,self.project.snapshot())
        if completed is None:
            return receive(self,stop)
        check_cancel(stop)
        self.update('video',state='verifying',message='이미 받은 새 영상의 검증 기록과 음성 시각을 확인하고 있습니다')
        self.update('video',state='complete',message='저장된 검증 결과로 영상 교체 완료',**completed)

    @property
    def data(self):
        return self.snapshot()

    def snapshot(self):
        data = self.project.snapshot()
        pending = data.get('video_replacement')
        if pending:
            data.update(format_id=pending['format_id'], video_generation=pending['generation'],
                        tasks=transfer_tasks(data), metadata=data['metadata'] | {'formats':pending['formats']})
        return data

    def update(self, kind, **values):
        if kind != 'video':
            return self.project.update(kind, **values)
        if values.get('state') == 'complete':
            data = self.project.snapshot()
            pending = data['video_replacement']
            old = data['tasks']['video']
            proof = values['verification']
            relative = values['assets']['playback']
            new = _owned_media(self.path,relative)
            if new.parent != self.path/'media'/pending['generation'] or proof.get('decode_exit_code') != 0:
                raise Conflict('새 영상의 저장 위치와 전체 검사 기록을 확인하세요')
            old_file = _owned_media(self.path,old['assets']['playback'])
            timing = replacement_timeline.compare(old_file,new,old.get('verification',{}).get('duration') or analysis_duration(data),
                                                  proof['duration'],analysis_duration(data),self.stop)
            if timing:
                shift = timing['new_minus_old_seconds']
                direction = '앞으로' if shift<0 else '뒤로'
                values['message'] += f' · 영상 길이 차이 {abs(timing["length_delta_seconds"]):.3f}초'
                if abs(shift)>=.1:
                    values['message'] += f' · 새 음성이 직전 영상보다 {abs(shift):.2f}초 {direction} 이동했습니다'
                values['verification'] = proof | {'replacement_timeline':timing}
        with self.project.mutex:
            data = self.project.snapshot()
            pending = data.get('video_replacement')
            if not pending:
                return
            task = task_timing.update(pending['task'], values)
            pending['task'] = task
            if task['state'] == 'complete':
                check_cancel(self.stop)
                self.commit(data, pending, task)
            data['updated_at'] = stamp()
            save_json(self.path/'project.json', data)
            self.project.data = data

    def commit(self, data, pending, task):
        old = data['tasks']['video']
        baseline = analysis_duration(data)
        files = pending['old_files']
        for info in files.values():
            if _file_info(self.path, info['file']) != info:
                raise Conflict('다운로드 중 기존 영상 파일이 변경됐습니다. 교체를 보류합니다')
        for key,relative in task['assets'].items():
            if _owned_media(self.path, relative).parent != self.path/'media'/pending['generation']:
                raise Conflict('새 영상 저장 위치가 다릅니다')
            file = asset_path(self.path, relative)
            if media_timeline.identity(file) != task['verification']['files'][key]:
                raise Conflict('시각 확인 중 새 영상이 변경됐습니다. 다시 검사하세요')
        data['analysis_video'] = {
            'source':logical_source(data, files['playback']),
            'playback':_file_info(self.path, task['assets']['playback']),
            'duration':baseline}
        if pending['policy'] == 'keep':
            fmt = next((f for f in data['metadata']['formats'] if f['id']==data['format_id']), {})
            data.setdefault('saved_video_versions', []).append({
                'id':uuid.uuid4().hex,'label':fmt.get('label') or data['format_id'],
                'assets':old['assets'],'saved_at':stamp()})
        else:
            targets = data.setdefault('video_cleanup', [])
            for info in files.values():
                if info not in targets:
                    targets.append(info)
        data['tasks']['video'] = task
        data.update(video_generation=pending['generation'], format_id=pending['format_id'])
        data['metadata'].update(formats=pending['formats'], title=pending['title'])
        del data['video_replacement']
