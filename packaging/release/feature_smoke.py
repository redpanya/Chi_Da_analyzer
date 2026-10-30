"""설치된 Python 대신 실제 패키지 HTTP로 편집·분할·오디오 선택을 검사한다."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.request import Request


def check(http, url, work, ffmpeg, ffprobe, fixture):
    def post(action, **data):
        request = Request(url+'api/'+action, data=json.dumps(data).encode('utf-8'),
                          headers={'Content-Type': 'application/json', 'Origin': url.rstrip('/').rsplit('/', 1)[0]})
        with http.open(request, timeout=90) as response:
            return json.load(response)

    def wait(action, data, active):
        deadline = time.monotonic()+90
        while time.monotonic() < deadline:
            value = post(action, **data)
            if value['state'] not in active:
                return value
            time.sleep(.1)
        raise RuntimeError('패키지 기능 검사 시간 초과: '+action)

    def probe(file):
        return json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(file)]))

    def packets(file):
        value = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_packets', '-show_data_hash', 'sha256',
                          '-show_entries', 'packet=stream_index,data_hash', '-of', 'json', str(file)]))
        result = {}
        for row in value['packets']:
            result.setdefault(row['stream_index'], []).append(row['data_hash'])
        return result

    source = work/'다중 오디오 source.mp4'
    args = [ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30:duration=4']
    for tone in (220, 440, 880):
        args += ['-f', 'lavfi', '-i', f'sine=frequency={tone}:sample_rate=48000:duration=4']
    args += ['-map', '0:v', '-map', '1:a', '-map', '2:a', '-map', '3:a',
             '-c:v', 'libx264', '-g', '30', '-c:a', 'aac', str(source)]
    subprocess.run(args, check=True, timeout=30)
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    registered = post('split-register', path=str(source))
    source_id = registered['source_id']
    preview = post('split-audio-preview', source_id=source_id, track=2, at=1)
    with http.open(url+'split-audio?id='+preview['id'], timeout=15) as response:
        assert response.headers.get_content_type() == 'audio/mp4'
        file = work/'미리듣기.m4a'; file.write_bytes(response.read())
    assert len(probe(file)['streams']) == 1
    assert packets(file)[0] == packets(source)[2]
    split_counts = []
    for mode, indices in [('all', [0, 1, 2, 3]), ('selected', [0, 2, 3])]:
        plan = post('split-plan', source_id=source_id, points=[1.4], audio_selection={'mode': mode, 'tracks': [2, 3]})
        state = wait('split-status', {'id': plan['id']}, ('planning',))
        assert state['state'] == 'ready', state
        destination = work/('출력 '+mode); destination.mkdir()
        post('split-start', id=state['id'], folder=str(destination))
        state = wait('split-status', {'id': state['id']}, ('running',))
        assert state['state'] == 'complete', state
        combined = {i: [] for i in range(len(indices))}
        for row in state['outputs'].values():
            output = Path(state['folder'])/row['name']
            assert len(probe(output)['streams']) == len(indices)
            for stream, hashes in packets(output).items():
                combined[stream].extend(hashes)
        assert combined == {i: packets(source)[source_index] for i, source_index in enumerate(indices)}
        assert state['command'][state['command'].index('-c')+1] == 'copy'
        split_counts.append(len(indices)-1)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original

    # 동봉 글꼴로 실제 한글을 그려 PNG로 등록한 뒤 패키지 FFmpeg로 클립에 합성한다.
    fonts = post('studio-fonts', **fixture)['fonts']
    font = next(f for f in fonts if f['bundled'] and f['family'] == 'Jua')
    assert 'ko' in font['languages']
    png = post('studio-decoration-preview', **fixture, size=[320, 180],
               text='한글 자막  공백 유지 123', options={'caption': True, 'font': font['id'], 'style': 'box'})
    assert base64.b64decode(png['png']).startswith(b'\x89PNG\r\n\x1a\n')
    asset = post('studio-image-add', **fixture, png=png['png'], name='검사 자막.png')
    image = {k: asset[k] for k in ('asset', 'name')} | {'x': 50, 'y': 50, 'width': 100, 'opacity': 100}
    job = post('studio-start', **fixture, request={'clips': [{'title': '자막 PNG 검사', 'start_ms': 0, 'end_ms': 1000}],
                                                  'options': {'image': image}})
    deadline = time.monotonic()+90
    while time.monotonic() < deadline:
        state = next(r for r in post('studio-status', **fixture)['runs'] if r['id'] == job['id'])
        if state['state'] != 'running':
            break
        time.sleep(.1)
    assert state['state'] == 'complete', state
    assert state['outputs']['clip-001']['verification']['bytes'] > 0
    return {'split_audio_counts': split_counts, 'all_video_and_selected_audio_packets_identical': True,
            'aac_preview_packets_identical': True, 'source_preserved': True,
            'packaged_korean_font_and_png_render': True, 'packaged_png_clip_encode': True}
