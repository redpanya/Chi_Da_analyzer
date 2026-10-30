"""모든 화면과 작업의 오류 기록. 첨부용 사본에는 자유 형식 메시지를 제외한다."""
import hashlib
import json
import platform
import re
import threading
import time
import traceback
from pathlib import Path
from . import runtime
from .storage import ProjectLock, read_json, save_json, stamp

_guard = threading.RLock()
_warning = ''
LIMIT = 1000
MAX_BYTES = 4 * 1024**2


def enabled():
    return runtime.settings().get('error_logging', True) is not False


def location():
    folder = runtime.SUPPORT/'diagnostics'
    file = folder/'errors.json'
    if folder.is_symlink() or file.is_symlink():
        raise ValueError('오류 기록에 연결 파일을 사용할 수 없습니다')
    return file


def config():
    return dict(enabled=enabled(), limit=LIMIT, warning=_warning)


def configure(value):
    if type(value) is not bool: raise ValueError('로그 저장 여부를 선택하세요')
    with _guard:
        runtime.save_settings(error_logging=value)
    return config()


def scrub(message):
    text = str(message)[:8000]
    text = re.sub(r'https?://[^\s<>]+', '[주소 생략]', text, flags=re.I)
    text = re.sub(r'(?i)(?:bearer\s+\S+|hf_[A-Za-z0-9]+|(?:token|password|secret|authorization|cookie|api[_-]?key)\s*[:=]\s*[^\s,;]+)', '[인증정보 생략]', text)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[이메일 생략]', text)
    text = re.sub(r'(?:[A-Za-z]:[\\/]|/(?:Users|Volumes|home|tmp|private|var)/)[^\r\n\"\']+', '[경로 생략]', text)
    return text[:2000]


def classification(message, error):
    if '영역' in message and ('100%' in message or '벗어' in message): return '화면 영역 설정 확인'
    if '글꼴' in message or 'glyph' in message.lower(): return '글꼴·자막 렌더링 확인'
    if isinstance(error, PermissionError): return '파일 접근 권한 확인'
    if isinstance(error, FileNotFoundError): return '필요한 파일 없음'
    if isinstance(error, OSError): return '장치·파일·네트워크 처리 오류'
    if isinstance(error, (ValueError, KeyError, TypeError)): return '입력·자료 형식 또는 처리 조건 확인'
    return '작업 오류 · 발생 위치와 종료 코드를 확인하세요'


def _read():
    file = location()
    if not file.exists(): return []
    if file.stat().st_size > MAX_BYTES: raise ValueError('오류 기록 크기를 확인하세요')
    data = read_json(file)
    if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('events'), list):
        raise ValueError('오류 기록 형식을 확인하세요')
    if any(not isinstance(row,dict) for row in data['events']): raise ValueError('오류 항목 형식을 확인하세요')
    return data['events'][-LIMIT:]


def record(operation, error, *, path=None, vod=None, run=None):
    """기록 실패는 원래 작업의 오류·중단·복구를 바꾸지 않는다."""
    global _warning
    try:
        with _guard:
            if not enabled(): return
            operation = operation if isinstance(operation, str) and re.fullmatch(r'[a-zA-Z0-9_./:-]{1,100}', operation) else 'unknown'
            if path is not None and vod is None:
                match = re.fullmatch(r'vod-(\d+)', Path(path).name)
                vod = match[1] if match else None
            vod = str(vod) if vod is not None and re.fullmatch(r'\d{1,20}', str(vod)) else None
            run = run if isinstance(run, str) and re.fullmatch(r'[a-f0-9]{32}', run) else None
            message = scrub(error)
            frames = []
            if isinstance(error, BaseException):
                frames = [dict(file=Path(f.filename).name, function=f.name, line=f.lineno)
                          for f in traceback.extract_tb(error.__traceback__)[-8:]]
            code = getattr(error, 'returncode', None)
            if type(code) is not int:
                match = re.search(r'(?:종료[^\n(]{0,30}|exit(?:ed)?[^\n(]{0,20})\((-?\d+)\)', str(error), re.I)
                code = int(match[1]) if match else None
            event = dict(at=stamp(), last_at=stamp(), operation=operation, vod_id=vod, run=run,
                         error_type=type(error).__name__ if isinstance(error, BaseException) else '화면 오류',
                         code=code, summary=classification(message, error), message=message, frames=frames, count=1)
            key = hashlib.sha256(repr((operation, vod, run, message)).encode()).hexdigest()
            folder = location().parent
            with ProjectLock(folder):
                rows = _read()
                now = time.time()
                recent = next((r for r in reversed(rows[-30:]) if r.get('_key') == key and now-r.get('_time',0)<30), None)
                if recent:
                    recent.update(count=recent.get('count',1)+1, last_at=event['last_at'], _time=now)
                else:
                    rows.append(event | {'_key':key, '_time':now})
                rows = rows[-LIMIT:]
                while rows and len(json.dumps({'schema':1,'events':rows},ensure_ascii=False,indent=2).encode('utf-8')) > MAX_BYTES-4096:
                    rows.pop(0)
                save_json(location(), {'schema':1, 'events':rows})
            _warning = ''
    except Exception:
        _warning = '오류 로그를 저장하지 못했습니다. 저장 공간·접근 권한을 확인하세요. 원래 작업 결과는 유지합니다.'


def snapshot(*, export=False):
    global _warning
    with _guard:
        try: rows = _read()
        except (OSError, ValueError):
            rows = []
            _warning = '저장된 오류 로그를 읽지 못했습니다. 기존 파일은 보존했습니다.'
        # 메시지·경로·본문·명령줄은 이메일 첨부 사본에 넣지 않는다.
        fields = ('at','last_at','operation','vod_id','run','error_type','code','summary','frames','count')
        if not export: fields += ('message',)
        events = [{k:r.get(k) for k in fields} for r in rows]
        return dict(schema=1, app_version='0.20.0', system=platform.system(), architecture=platform.machine(), created_at=stamp(), **config(), events=events)


def install_hooks():
    """최상위에서 처리하지 못한 Python 오류도 원래 예외 처리를 유지하며 기록한다."""
    import sys
    previous = sys.excepthook
    previous_thread = threading.excepthook
    def main_hook(kind, error, tb):
        record('python-main', error.with_traceback(tb)); previous(kind,error,tb)
    def thread_hook(args):
        record('python-thread', args.exc_value.with_traceback(args.exc_traceback)); previous_thread(args)
    sys.excepthook = main_hook
    threading.excepthook = thread_hook


def dispatch(action, data):
    if action == 'config': return config()
    if action == 'settings': return configure(data.get('enabled'))
    if action == 'list': return snapshot()
    if action == 'export': return snapshot(export=True)
    if action == 'client':
        page, kind = data.get('page'), data.get('kind')
        if page not in ('index','clip-studio','video-split') or kind not in ('script','promise','network','response','media'):
            raise ValueError('화면 오류 기록 형식을 확인하세요')
        message = data.get('message', '')
        if not isinstance(message,str) or len(message)>2000: raise ValueError('화면 오류 내용이 너무 깁니다')
        record('browser-'+page+'-'+kind,message, vod=data.get('vod_id'))
        return {'saved':enabled() and not _warning, 'warning':_warning}
    raise ValueError('지원하지 않는 오류 기록 요청입니다')
