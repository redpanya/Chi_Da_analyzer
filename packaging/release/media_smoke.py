"""임시 영상으로 수신 후 검사 재개와 패키지의 원음 추출 API를 확인한다."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
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


def prepare_recovery(work, movie, ffmpeg):
    root = work/'복구 보관함'; path = root/'vod-2'
    meta = {'id': '2', 'title': '시각 이동·채팅 경계 복구', 'duration': 1,
            'chat_enabled': True, 'formats': [{'id': 'test'}]}
    with ProjectLock(path):
        data = create_or_load(path, meta, 'test')
        media = path/'media'; media.mkdir()
        original, playback = media/'original.mp4', media/'playback.tmp.mp4'
        subprocess.run([ffmpeg, '-v', 'error', '-copyts', '-itsoffset', '2.7', '-i', str(movie),
                        '-c', 'copy', '-movflags', 'frag_keyframe+delay_moov', str(original)], check=True, timeout=30)
        subprocess.run([ffmpeg, '-v', 'error', '-i', str(original), '-c', 'copy', '-movflags', '+faststart', str(playback)], check=True, timeout=30)
        with patch.dict(os.environ, {'PATH': str(Path(ffmpeg).parent)+os.pathsep+os.environ.get('PATH', '')}):
            info = video.probe(original)
        assert float(info['format']['start_time']) > 1
        save_json(media/'probe.json', info)
        save_json(media/'source.json', {'id': '2', 'format_id': 'test', 'protocol': 'https', 'filesize': original.stat().st_size})
        def message(at, text):
            return {'playerMessageTime': at, 'messageTime': 10000+at, 'userIdHash': 'fixture', 'content': text}
        def page(items, following):
            return {'code': 200, 'content': {'videoChats': items, 'previousVideoChats': [], 'nextPlayerMessageTime': following}}
        repeated = message(100, '실제 반복 🤩')
        first, last = page([message(1, '앞'), repeated], 100), page([message(300, '뒤')], None)
        for sequence, cursor, value in ((0, 0, first), (1, 100, last)):
            save_json(path/f'chat-pages/{sequence:06}.json', {'vod_id': '2', 'cursor': cursor, 'response': value})
        save_json(path/'diagnostics/chat-audit/0.json', first)
        save_json(path/'diagnostics/chat-audit/99.json', page([repeated, repeated, message(300, '뒤')], None))
        save_json(path/'diagnostics/chat-audit.json', {'match': False, 'checks': [{'cursor': 99, 'missing': 1}]})
        old = path/'exports/old.json'; save_json(old, {'이전 결과': '유지'})
        data['tasks']['video'].update(state='error', message='길이 비교 실패')
        data['tasks']['chat'].update(state='review', assets={'json': 'exports/old.json'})
        save_json(path/'project.json', data)
        before = {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in path.rglob('*') if p.is_file() and p.name not in ('project.json', '.write.lock')}
    return {'root': str(root), 'vod_id': '2'}, before


def check_recovery(http, url, fixture):
    payload, before = fixture
    def post(endpoint, **values):
        request = Request(url+'api/'+endpoint, data=json.dumps(payload | values).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': url.rstrip('/').rsplit('/', 1)[0]})
        with http.open(request, timeout=30) as response: return json.load(response)
    post('start', kind='all', format_id='test')
    deadline = time.monotonic()+60
    while True:
        state = post('state')
        if not state['locked']: break
        if time.monotonic() >= deadline: raise RuntimeError('패키지 복구 시간 초과')
        time.sleep(.1)
    assert all(task['state'] == 'complete' for task in state['tasks'].values()), state['tasks']
    verified = state['tasks']['video']['verification']
    assert verified['received_file_reused'] and verified['playback_file_reused']
    assert verified['timeline']['copied']
    chat = state['tasks']['chat']
    assert chat['verification']['recovered'] == 1 and chat['verification']['network_requests'] == 0
    assert chat['progress']['messages'] == 4
    details = post('speech-info')
    assert details['duration_ms'] > 0 and details['tracks']
    path = Path(payload['root'])/'vod-2'
    for name, digest in before.items():
        assert hashlib.sha256((path/name).read_bytes()).hexdigest() == digest, name
    return {'nonzero_start': True, 'offline_video_recovery': True, 'reused_playback': True,
            'chat_recovered': 1, 'chat_network_requests': 0, 'all_existing_files_preserved': True}
