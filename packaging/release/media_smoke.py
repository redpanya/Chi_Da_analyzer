"""임시 영상으로 수신 후 검사 재개와 패키지의 원음 추출 API를 확인한다."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from unittest.mock import MagicMock, patch
from urllib.request import Request
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from archive import video
from archive.storage import Project, ProjectLock, create_or_load, save_json


def prepare(work, movie, ffmpeg):
    root = work/'보관함'; path = root/'vod-1'
    meta = {'id': '1', 'title': '한글 제목 🤩', 'channel': '검사 자료', 'duration': 1,
            'chat_enabled': True, 'formats': [{'id': 'test', 'estimated_bytes': 1}]}
    identity = {'id': '1', 'format_id': 'test', 'ext': 'mp4', 'protocol': 'https',
                'width': 320, 'height': 180, 'vcodec': 'h264', 'acodec': 'aac', 'filesize': movie.stat().st_size}
    with ProjectLock(path) as lock:
        project = Project(path, create_or_load(path, meta, 'test'), lock)
        media = path/'media'; media.mkdir()
        original = media/'original.mp4'; shutil.copy2(movie, original)
        before = hashlib.sha256(original.read_bytes()).hexdigest()
        save_json(media/'source.json', identity)
        project.update('video', state='error', message='다운로드 후 검사 재개 검증')
        # 네트워크 수신만 대체한다. 저장된 원본의 ffprobe·전체 디코딩·확정은 실제 실행한다.
        downloader = MagicMock()
        downloader.extract_info.return_value = identity | {'duration': 1}
        with patch.object(video, 'YoutubeDL') as factory, patch.object(video, 'metadata', return_value=meta), \
                patch.dict(os.environ, {'PATH': str(Path(ffmpeg).parent)+os.pathsep+os.environ.get('PATH', '')}):
            factory.return_value.__enter__.return_value = downloader
            video.download(project, threading.Event())
        task = project.snapshot()['tasks']['video']
        assert task['state'] == 'complete', task
        assert Path(task['assets']['playback']) == Path('media/original.mp4'), task['assets']
        assert task['verification']['original_sha256'] == before
        assert hashlib.sha256(original.read_bytes()).hexdigest() == before
        chat = path/'exports/chat.jsonl'; chat.parent.mkdir()
        chat.write_text(json.dumps({'offset_ms': 0, 'text': '채팅 보존 🤩'}, ensure_ascii=False)+'\n', encoding='utf-8')
        project.update('chat', state='complete', assets={'jsonl': 'exports/chat.jsonl'})
    return {'root': str(root), 'vod_id': '1'}, before, chat.read_bytes()


def check(http, url, fixture):
    payload, before, chat_before = fixture
    def post(endpoint, **values):
        request = Request(url+'api/'+endpoint, data=json.dumps(payload | values).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': url.rstrip('/').rsplit('/', 1)[0]})
        with http.open(request, timeout=30) as response:
            return json.load(response)
    details = post('speech-info')
    assert details['duration_ms'] == 1000 and details['tracks'][0]['codec'] == 'aac'
    post('speech-start', action='audio', track=details['tracks'][0]['index'])
    deadline = time.monotonic()+30
    while True:
        state = post('state')['speech']
        if state['state'] not in ('running', 'stopping'):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('패키지 원음 추출 시간 초과')
        time.sleep(.1)
    assert state['state'] == 'complete', state
    path = Path(payload['root'])/'vod-1'
    audio = state['raw_audio']; file = path/'speech'/audio['file']
    with wave.open(str(file), 'rb') as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) == (1, 2, 16000, 16000)
    assert hashlib.sha256(file.read_bytes()).hexdigest() == audio['sha256']
    assert hashlib.sha256((path/'media/original.mp4').read_bytes()).hexdigest() == before
    assert (path/'exports/chat.jsonl').read_bytes() == chat_before
    return {'video_resume': True, 'packaged_audio_info': True, 'packaged_audio_extract': True,
            'duration_ms': audio['duration_ms'], 'original_and_chat_preserved': True}
