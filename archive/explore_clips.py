"""공통 시간축의 클립 후보. 저장된 결과를 읽으며 추론이나 저장은 하지 않는다."""
from . import context_job


def read(path, vod, duration, selected=None):
    if selected is not None and not isinstance(selected, str):
        raise ValueError('시간축에 표시할 클립 후보 버전을 선택하세요')
    try:
        state = context_job.state(path)
        runs = [r for r in state.get('runs', []) if r.get('mode') == 'clips']
        ids = {r['id'] for r in runs}
        chosen = selected or (state.get('clip_run') if state.get('clip_run') in ids else runs[-1]['id'] if runs else None)
        if selected and selected not in ids:
            raise ValueError('선택한 클립 후보 버전이 없습니다. 다시 선택하세요')
        if chosen is None:
            return {'run': None, 'items': [], 'notes': ['클립 후보 결과 없음 · AI 문맥에서 생성하거나 외부 결과를 가져오세요']}
        result = context_job.result(path, vod, chosen)
        items, skipped = [], 0
        for row in result.get('items', []):
            a, b = row.get('start_ms'), row.get('end_ms')
            if row.get('failed') or any(type(v) is not int for v in (a, b)) or not 0 <= a < b <= duration:
                skipped += 1
                continue
            items.append({'id':row.get('id'), 'start_ms':a, 'end_ms':b, 'title':str(row.get('title') or '제목 없는 클립 후보')})
        label = next(r for r in runs if r['id'] == chosen).get('label') or '클립 후보'
        notes = [f"클립 후보 {len(items)}개 · {label}" + (' · 일부 처리의 완료 후보' if not result.get('complete') else '')]
        if result.get('stale'):notes.append('클립 후보: 지난 입력의 결과 · 영상 확인 필요')
        if skipped:notes.append(f'시각 확인이 필요하거나 실패한 클립 후보 {skipped}개 제외')
        return {'run':chosen, 'items':sorted(items, key=lambda r:(r['start_ms'],r['end_ms'])), 'notes':notes}
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        return {'run':selected, 'items':[], 'notes':['클립 후보 결과를 읽지 못했습니다. AI 문맥의 클립 후보 버전을 확인하세요']}
