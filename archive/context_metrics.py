"""추론 응답의 기존 계측을 집계한다. 누락된 시간은 0으로 추정하지 않는다."""
import json
import time
from .storage import read_json, save_json


def record(folder, value):
    with (folder/'inference-events.jsonl').open('a',encoding='utf-8') as file:
        file.write(json.dumps(value,ensure_ascii=False)+'\n')


def collect(folder, tokenizer, started, job=None):
    events_file=folder/'inference-events.jsonl'
    events=[]
    if events_file.exists():
        for line in events_file.read_text(encoding='utf-8').splitlines():
            try:events.append(json.loads(line))
            except json.JSONDecodeError:pass  # 마지막 로그 쓰기 도중 종료되어도 응답 파일로 계측한다.
    metrics=[read_json(file) for file in folder.glob('*-*/metrics.json')]
    requests={f.parent.name for f in folder.glob('*-*/request.json')}
    attempts=requests|{r['folder'] for r in events if not r['checkpoint_reused'] and r.get('folder')}
    unmeasured=sum(not (folder/name/'metrics.json').exists() for name in attempts)
    def total(key, completed_only=False):
        if unmeasured and not completed_only:return None
        values=[(m.get('timings') or {}).get(key) for m in metrics]
        return sum(values) if values and all(type(v) in (float,int) for v in values) else None
    result={'scope':'이 실행 폴더 누적 요청; 벽시계·토큰화는 이번 세션',
        'session_seconds':round(time.monotonic()-started,3),
        'fresh_attempts':len(attempts),
        'requests_without_response_metrics':sum(not (folder/name/'metrics.json').exists() for name in requests),
        'checkpoint_reuses':sum(r['checkpoint_reused'] for r in events),
        'measured_responses':len(metrics),'prompt_ms':total('prompt_ms'),'generation_ms':total('predicted_ms'),
        'completed_prompt_ms':total('prompt_ms',True),'completed_generation_ms':total('predicted_ms',True),
        'generated_tokens':total('predicted_n'),'cached_prompt_tokens':total('cache_n'),
        'tokenizer_seconds':round(getattr(tokenizer,'seconds',0),3),
        'tokenizer_requests':getattr(tokenizer,'tokenizer_requests',None),
        'tokenizer_hits':getattr(tokenizer,'tokenizer_hits',None),
        'files_bytes':sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())}
    server=getattr(job,'server',None)
    ready=server.folder/'ready.json' if server else None
    result.update(preflight_seconds=getattr(job,'preflight_seconds',None),
        model_hash_seconds=getattr(job,'model_hash_seconds',None),
        model_load_seconds=read_json(ready)['load_seconds'] if ready and ready.exists() else None)
    save_json(folder/'measurements.json',result)
    return result
