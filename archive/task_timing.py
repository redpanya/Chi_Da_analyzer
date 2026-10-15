"""진행 상태와 함께 보존하는 실행 시간. 중단 대기와 과거 미기록 시간은 제외한다."""
import time

ACTIVE = {'queued', 'running', 'downloading', 'verifying', 'exporting', 'stopping'}


def now_ms():
    return round(time.time() * 1000)


def start(previous, resume=False):
    old = previous.get('timing') or {}
    carry = resume and previous.get('state') in ACTIVE | {'paused', 'error', 'review'}
    return {'elapsed_ms': old.get('elapsed_ms', 0) if carry else 0,
            'since_ms': now_ms(), 'finished_ms': None,
            'partial': bool(carry and (not old or old.get('partial') or old.get('since_ms') is not None))}


def update(previous, values):
    value = previous | values
    timer = value.get('timing')
    if timer and timer.get('since_ms') is not None:
        now = now_ms()
        running = value.get('state') in ACTIVE
        value['timing'] = timer | {'elapsed_ms': timer['elapsed_ms'] + max(0, now - timer['since_ms']),
                                  'since_ms': now if running else None,
                                  'finished_ms': None if running else now}
    return value


def interrupted(value):
    timer = value.get('timing')
    if timer and timer.get('since_ms') is not None:
        # 종료 시각을 알 수 없으므로 마지막 저장 이후의 시간을 만들어 더하지 않는다.
        return value | {'timing': timer | {'since_ms': None, 'partial': True}}
    return value
