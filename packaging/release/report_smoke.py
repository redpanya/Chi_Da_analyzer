"""패키지 안의 새 API를 합성 자료로 확인한다. 외부 제출은 하지 않는다."""
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request


def check(http, url, project):
    def post(action, values):
        request = Request(url+'api/'+action, data=json.dumps(values).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': url.rstrip('/').rsplit('/', 1)[0]})
        with http.open(request, timeout=30) as response:
            return json.load(response)

    queue = post('queue-status', {'root': project['root']})
    assert queue['state'] == 'idle' and not queue['active'] and not queue['items']
    config = post('report-config', {})
    assert 'hardware' in config and 'configuration' not in config
    deadline = time.monotonic()+20
    while True:
        records = post('reports', project)
        if records:
            selected = project | {'report_id': records[0]['id']}
            value = post('report-read', selected)
            if any(s['stage'] == 'audio' and s['state'] == 'complete' for s in value['payload']['stages']):
                break
        if time.monotonic() >= deadline:
            raise RuntimeError('패키지 원음 추출의 리포트 완료 기록을 확인하지 못했습니다')
        time.sleep(.1)
    payload = post('report-preview', selected)['payload']
    assert payload['schema'] == 2 and payload['vod_id'] == project['vod_id']
    assert payload['app_version'] == '0.20.0'
    assert 'events' not in payload and 'details' not in payload
    assert payload['hardware']['os'] and 'video_seconds' in payload['counts']
    # 구형 파일을 직접 열어도 내보내기 사본만 보완하고 파일은 바꾸지 않는다.
    legacy = json.loads(json.dumps(value))
    legacy['payload'].update(schema=1, policy='2026-10-18.1', report_id='f'*32)
    del legacy['payload']['vod_id']
    folder = Path(project['root'])/('vod-'+project['vod_id'])/'diagnostics/reports'
    file = folder/('f'*32+'.json')
    original = json.dumps(legacy, ensure_ascii=False).encode('utf-8')
    file.write_bytes(original)
    restored = post('report-preview', project | {'report_id': 'f'*32})['payload']
    assert restored['schema'] == 2 and restored['vod_id'] == project['vod_id']
    assert file.read_bytes() == original
    try:
        post('report-submit', {})
    except HTTPError as error:
        assert error.code == 410
        assert '이메일' in json.loads(error.read())['error']
    else:
        raise AssertionError('제거된 자동 전송 API가 실행되었습니다')
    with http.open(url, timeout=15) as response:
        html = response.read().decode('utf-8')
    assert 'mailto:redpanyaday@gmail.com' in html and 'id="report-send"' not in html
    return {'queue_idle': True, 'audio_report_recorded': True, 'vod_id_in_export': True,
            'legacy_file_preserved': True, 'email_instructions': True, 'upload_removed_410': True}
