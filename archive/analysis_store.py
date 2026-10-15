"""분석 입력 검증·별도 원자적 결과 저장·제한된 원문 조회."""

import hashlib
import json

from . import analysis
from .storage import ACTIVE, Conflict, asset_path, read_json, save_json, stamp


def source_info(path, data):
    task = data['tasks']['chat']
    relative = task.get('assets', {}).get('jsonl')
    if not relative:
        raise ValueError('저장된 채팅 내보내기가 없습니다. 먼저 채팅을 수집하세요')
    file = asset_path(path, relative)
    stat = file.stat()
    timeline={'local_start_vod_ms':data['input']['start_vod_ms']} if data.get('input') else {}
    return timeline|{'file': relative, 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'state': task['state'], 'duration': data['tasks']['video'].get('verification',{}).get('duration',data['metadata'].get('duration', 0)) if data.get('input') else data['metadata'].get('duration',0)}


def rows(path, data, digest=None, counter=None, mapping_offset=0):
    info = source_info(path, data)
    previous = -1
    with asset_path(path, info['file']).open('rb') as file:
        for index, line in enumerate(file):
            if digest is not None:
                digest.update(line)
            try:
                row = json.loads(line)
                offset = row['offset_ms']
                if (row['vod_id'] != data['vod_id'] or type(offset) is not int or
                        not 0 <= offset < analysis.MAX_SECONDS * 1000 or offset < previous):
                    raise ValueError()
                if row.get('text') is not None and not isinstance(row['text'], str):
                    raise ValueError()
                if any(row.get(key) is not None and not isinstance(row[key], str) for key in ('nickname', 'user_id_hash')):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise ValueError(f'채팅 내보내기 {index + 1}행의 VOD·시각·내용을 확인하세요') from None
            if counter is not None: counter[0] += 1
            previous = offset
            if data.get('input'):
                at=offset-data['input']['start_vod_ms']
                if not 0<=at+mapping_offset<(info['duration'] or 0)*1000:continue
                row=row|{'offset_ms':at,'vod_offset_ms':offset}
            yield row


def result_path(path):
    directory = path / 'analysis'
    if directory.is_symlink() or (directory / 'result.json').is_symlink():
        raise Conflict('분석 경로에 연결 파일을 사용할 수 없습니다')
    return directory / 'result.json'


def load(path, data):
    target = result_path(path)
    if not target.exists():
        return None
    result = read_json(target)
    if result.get('vod_id') != data['vod_id'] or result.get('version') != analysis.VERSION:
        raise ValueError('분석 결과 버전·VOD가 다릅니다. 다시 분석하세요')
    try:
        stale = result['source'] != source_info(path, data)
    except (ValueError, OSError):
        stale = True
    return result | {'stale': stale}


def run(path, data, options, allow_partial):
    if type(allow_partial) is not bool:
        raise ValueError('일부 채팅 분석 여부를 확인하세요')
    if any(task['state'] in ACTIVE for task in data['tasks'].values()):
        raise Conflict('다운로드를 완료하거나 중단한 뒤 분석하세요')
    info = source_info(path, data)
    state = info['state']
    summary_path = str((asset_path(path, info['file']).parent / 'summary.json').relative_to(path))
    summary = read_json(asset_path(path, summary_path))
    expected = {'complete': '제공 범위 순회·경계 대조 완료', 'empty': '현재 제공된 채팅 없음', 'unavailable': '채팅 미제공'}
    if state in expected and summary.get('status') != expected[state]:
        raise ValueError('채팅 내보내기의 수집 상태가 프로젝트와 다릅니다')
    complete = state in ('complete', 'empty')
    if not complete and state != 'unavailable' and not allow_partial:
        raise ValueError('전체 수집이 완료되지 않았습니다. 일부 자료 분석을 선택하거나 수집을 마치세요')
    digest = hashlib.sha256(); counter = [0]
    result = analysis.analyze(rows(path, data, digest, counter), (info['duration'] or 0) * 1000,
                              complete, options)
    if state == 'review':
        for bin in result['graph']:
            if bin['coverage'] == 'known':
                bin['coverage'] = 'unverified'
    if info != source_info(path, data):
        raise Conflict('분석 중 입력 자료가 변경됐습니다. 다시 분석하세요')
    if summary.get('messages') != counter[0]:
        raise ValueError('채팅 내보내기 건수가 수집 요약과 다릅니다. 원본을 확인하세요')
    result.update(vod_id=data['vod_id'], created_at=stamp(), source=info, source_sha256=digest.hexdigest(),
                  source_label=summary.get('status', '상태 미확인'), unavailable=state == 'unavailable',
                  boundary_unverified=state == 'review')
    target=result_path(path)
    if target.exists():
        import uuid
        previous=target.parent/'versions'/(uuid.uuid4().hex+'.json'); previous.parent.mkdir(exist_ok=True)
        if previous.parent.is_symlink(): raise Conflict('이전 분석 보존 폴더에 연결 파일은 사용할 수 없습니다')
        previous.write_bytes(target.read_bytes())
    save_json(target, result)
    return result | {'stale': False}


def search(path, data, query='', start_ms=0, end_ms=None, cursor=0):
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError('검색어는 200자 이내로 입력하세요')
    if (type(cursor) is not int or cursor < 0 or type(start_ms) is not int or start_ms < 0 or
            (end_ms is not None and (type(end_ms) is not int or end_ms < start_ms))):
        raise ValueError('채팅 조회 범위가 올바르지 않습니다')
    needle = analysis.normalise(query)
    found = []
    for index, row in enumerate(rows(path, data)):
        if index < cursor or row['offset_ms'] < start_ms:
            continue
        if end_ms is not None and row['offset_ms'] >= end_ms:
            break
        if needle not in analysis.normalise(row.get('text') or ''):
            continue
        if len(found) == 100:
            return {'items': found, 'next_cursor': index}
        found.append({key: row.get(key) for key in ('offset_ms', 'nickname', 'text')})
    return {'items': found, 'next_cursor': None}
