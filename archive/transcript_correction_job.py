"""국소 보정 체크포인트와 부분 실패 복구. 추론 엔진은 호출자가 제공한다."""
import copy
import json
import time
from . import context_evidence as ev, context_tokens as tokens, transcript_correction as correction
from .source import check_cancel, Cancelled
from .storage import read_json, save_json

def process(source, folder, infer, tokenizer, stop, identity, offset_ms=0):
    folder.mkdir(parents=True, exist_ok=True)
    original = copy.deepcopy(source); effective = copy.deepcopy(source)
    rows = ev.speech(original); cursor = 0; batches = []; begin = time.monotonic()
    while cursor < len(rows):
        check_cancel(stop)
        group = tokens.fit(rows[cursor:], lambda r:correction.prompt(r, offset_ms), tokenizer)
        signature = ev.digest([correction.REVISION, original, identity, group, offset_ms])
        checkpoint = folder / f'batch-{cursor:05}.json'
        if checkpoint.exists():
            saved = read_json(checkpoint)
            if saved['signature'] != signature: raise ValueError('보정 체크포인트의 입력·모델·설정이 다릅니다')
            raw = saved['raw']; reused = True
        else:
            raw = None; reused = False; errors = []
            for attempt in range(2):
                check_cancel(stop)
                text = correction.prompt(group, offset_ms, retry=bool(attempt))
                if tokenizer.count(text) + tokens.OUTPUT + tokens.MARGIN > tokens.CONTEXT:
                    raise ValueError('보정 입력·출력 예약이 문맥 한도를 넘었습니다')
                try:
                    candidate, _ = infer(correction.payload(group, offset_ms),
                        folder / f'correction-{cursor:05}-{time.time_ns()}', text, correction.schema(group))
                    correction.apply(original, candidate, group)
                    raw = candidate
                    save_json(checkpoint, {'signature':signature, 'raw':raw})
                    break
                except Cancelled: raise
                except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as error:
                    errors.append(str(error))
            if raw is None:
                batches.append({'start_id':group[0]['id'],'end_id':group[-1]['id'],
                    'failed':True,'errors':errors,'accepted':[],'rejected':[],'unresolved':[]})
                cursor += len(group); continue
        patched, report = correction.apply(original, raw, group)
        changed = {r['id'] for r in report['accepted']}
        for i, row in enumerate(patched['speech']):
            if f'S{i}' in changed: effective['speech'][i]['text'] = row['text']
        batches.append({'start_id':group[0]['id'],'end_id':group[-1]['id'], 'failed':False,
                        'checkpoint_reused':reused, **report})
        cursor += len(group)
        save_json(folder / 'progress.json', {'processed':cursor,'total':len(rows),'batches':batches})
    correction.verify_metadata(original, effective)
    check_cancel(stop)
    report = {'revision':correction.REVISION,'source_fingerprint':ev.digest(original),
        'corrected_fingerprint':ev.digest(effective),'identity':identity,'batches':batches,
        'complete':not any(r['failed'] or r['rejected'] for r in batches),
        'accepted_edits':sum(len(r['accepted']) for r in batches),
        'changed_utterances':sum(a['text']!=b['text'] for a,b in zip(original['speech'],effective['speech'])),
        'seconds':round(time.monotonic()-begin,3), 'metadata_unchanged':True}
    save_json(folder / 'corrected-source.json', effective)
    save_json(folder / 'report.json', report)
    return effective, report
