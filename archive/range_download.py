"""구간 다운로드의 완료 검사·중단 자료 보존. 전체 VOD 파일에는 쓰지 않는다."""
import hashlib
import uuid
from . import download_scope, remote_media, clip_render, media_timeline
from .source import check_cancel
from .storage import Conflict, save_json


def download(project, stop):
    data = project.snapshot(); scope = download_scope.bounds(data)
    if scope is None:
        raise ValueError('구간 다운로드 설정이 없습니다')
    folder = project.path/'media'
    if folder.is_symlink():
        raise Conflict('영상 폴더에 연결 경로를 사용할 수 없습니다')
    folder.mkdir(exist_ok=True)
    target = folder/'range.mp4'
    if target.is_symlink():
        raise Conflict('기존 연결 파일은 덮어쓰지 않습니다')
    project.update('video', state='running', message='지정 구간의 영상을 받고 있습니다', progress={})
    def update(**values):
        fraction = values.get('progress', 0)
        project.update('video', state='verifying' if fraction >= .85 else 'running',
                       message='지정 구간 영상 전체 검사 중' if fraction >= .85 else '지정 구간 영상 다운로드 중',
                       progress={'percent':round(fraction*100,1)})
    if target.exists():
        proof = clip_render.verify(target, (scope['end_ms']-scope['start_ms'])/1000, stop, project.lock,
                                   lambda **v:update(progress=.85+v.get('progress',0)*.15))
    else:
        # 중단된 인코딩 결과는 덮어쓰지 않는다. 완료된 영상과 채팅 페이지는 재사용한다.
        part = folder/f'range-{uuid.uuid4().hex}.part.mp4'
        proof = remote_media.receive(data['vod_id'], scope['start_ms'], scope['end_ms'], part,
                                     stop, project.lock, update, format_id=data['format_id'])
        check_cancel(stop)
        part.replace(target)
    digest = hashlib.sha256()
    with target.open('rb') as stream:
        while block := stream.read(4*1024**2):
            check_cancel(stop); digest.update(block)
    proof.update(decode_exit_code=0, original_sha256=digest.hexdigest(), range_ms=[scope['start_ms'],scope['end_ms']],
                 files={k:media_timeline.identity(target) for k in ('original','playback')})
    save_json(folder/'probe.json', clip_render.probe(target))
    save_json(folder/'range-verification.json', proof)
    project.update('video', state='complete', message='지정 구간 영상 다운로드·전체 검사 완료', verification=proof,
                   assets={'original':'media/range.mp4','playback':'media/range.mp4'},
                   progress={'percent':100, 'downloaded_bytes':target.stat().st_size, 'total_bytes':target.stat().st_size})
