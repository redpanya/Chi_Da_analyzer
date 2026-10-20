"""목록의 영상·채팅 재사용 검사. 원본과 기존 검사 결과를 덮어쓰지 않는다."""
import hashlib

from . import media_timeline, video
from .source import check_cancel
from .storage import asset_path, read_json, save_json, Project, ProjectLock, load_project, recover


def video_ready(project, stop):
    task, path = project.data['tasks']['video'], project.path
    if task['state'] != 'complete':
        return False
    proof = task.get('verification') or {}
    if not proof.get('duration') or not (proof.get('decode_exit_code') == 0 or proof.get('source') == 'local'):
        return False
    try:
        files = {key: asset_path(path, task['assets'][key]) for key in ('original', 'playback')}
        identities = {key: media_timeline.identity(file) for key, file in files.items()}
    except (KeyError, FileNotFoundError):
        return False
    if proof.get('files') == identities:
        return True
    # 구버전 완료 기록은 기존 해시와 대조해 한 번만 확인한다. 등록 화면에서는 실행하지 않는다.
    cache = path / 'diagnostics' / 'automation-media.json'
    saved = read_json(cache) if cache.exists() else {}
    signature = {'verification': proof, 'files': identities}
    if saved == signature:
        return True
    expected = proof.get('original_sha256') or proof.get('sha256')
    if not expected:
        return False
    digest = hashlib.sha256()
    with files['original'].open('rb') as stream:
        while block := stream.read(4 * 1024**2):
            check_cancel(stop)
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError('완료 기록과 원본 영상이 다릅니다. 기존 파일을 보존했습니다. 원본을 복구한 뒤 다시 확인하세요')
    if files['original'] != files['playback']:
        original_info, playback_info = video.probe(files['original']), video.probe(files['playback'])
        video.validate_playback(project, files['original'], original_info, files['playback'], playback_info,
                                proof.get('timeline', {}).get('copied', False), stop)
        video.run_media(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(files['playback']),
                         '-f', 'null', '-'], project, stop, 'automation-playback-check.log')
    check_cancel(stop)
    if identities != {key: media_timeline.identity(file) for key, file in files.items()}:
        raise ValueError('확인 중 영상 파일이 변경됐습니다. 기존 파일을 보존했습니다')
    save_json(cache, signature)
    return True


def chat_ready(path, task, allow_partial):
    if task['state'] not in ('complete', 'empty', 'unavailable') and not (allow_partial and task['state'] == 'review'):
        return False
    if not task.get('assets', {}).get('jsonl'):
        return False
    try:
        for relative in task['assets'].values():
            asset_path(path, relative)
    except FileNotFoundError:
        return False
    return True


def prepare(path, vod, allow_partial, stop):
    with ProjectLock(path) as lock:
        data = recover(path, load_project(path, vod))
        project = Project(path, data, lock)
        ready = {'video': video_ready(project, stop), 'chat': chat_ready(path, data['tasks']['chat'], allow_partial)}
        if data.get('input') and not ready['video']:
            raise ValueError('내 비디오가 미완료이거나 검사 기록과 다릅니다. 가져오기에서 같은 파일을 다시 첨부해 확인하세요')
        for kind, valid in ready.items():
            if not valid and data['tasks'][kind]['state'] in ('complete', 'empty', 'unavailable'):
                project.update(kind, state='paused', message='저장 자료를 다시 검사해야 합니다. 기존 원본·결과를 유지하고 이어받습니다')
        return ready
