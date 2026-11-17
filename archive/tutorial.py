"""사용자별 첫 화면 안내. 서로 다른 창에서도 같은 안내는 한 번만 연다."""
import threading

from . import runtime
from .storage import ProjectLock, read_json, save_json

GUIDES = frozenset('welcome register library jobs prepare analysis explore voiceReview work clip mix split external report settings download audio speech voices context'.split())
_guard = threading.Lock()


def state():
    file = runtime.SUPPORT / 'tutorial' / 'state.json'
    try:
        value = read_json(file)
    except (OSError, ValueError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    guides = value.get('guides')
    guides = dict(guides) if isinstance(guides, dict) else {}
    old_mix = guides.pop('mixList', None)
    if old_mix == 'replay' or ('mix' not in guides and old_mix == 'seen'):
        guides['mix'] = old_mix
    return {'enabled': value.get('enabled') is not False,
            'guides': {k: v for k, v in guides.items() if k in GUIDES and v in ('seen', 'replay')}}


def update(data):
    if not data:
        return state()
    action, guide = data.get('action'), data.get('guide')
    if guide == 'mixList':
        guide = 'mix'
    if action not in ('visit', 'replay', 'enable', 'disable'):
        raise ValueError('안내 설정을 확인하세요')
    if action in ('visit', 'replay') and (not isinstance(guide, str) or guide not in GUIDES):
        raise ValueError('안내할 화면을 확인하세요')
    folder = runtime.SUPPORT / 'tutorial'
    with _guard, ProjectLock(folder):
        value = state()
        guides = value['guides']
        if action == 'visit':
            show = guides.get(guide) == 'replay' or (value['enabled'] and guide not in guides)
            if not show:
                return dict(value, show=False)
            guides[guide] = 'seen'
        elif action == 'replay':
            guides[guide] = 'replay'
        else:
            value['enabled'] = action == 'enable'
            if action == 'disable':
                value['guides'] = {k: v for k, v in guides.items() if v != 'replay'}
        save_json(folder / 'state.json', value)
        return dict(value, show=action == 'visit')
