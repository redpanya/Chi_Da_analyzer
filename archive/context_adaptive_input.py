"""형식 10의 읽기 전용 전사 입력. 품질 신호와 자료 유효성을 분리한다."""
import math
import json

FLAGS = ('repeat_review', 'repeat_candidate', 'boundary_review', 'quality_review', 'encoding_review')


def prepare(source):
    result=[]; rejected=[]; speakers={};seen=set()
    for i, row in enumerate(source['speech']):
        key='S'+str(i); text=row.get('text'); start=row.get('start_ms'); end=row.get('end_ms')
        valid=all(type(x) in (int,float) and math.isfinite(x) for x in (start,end))
        reason=('전사 시각 확인 필요' if not valid or not 0<=start<end<=source['duration_ms'] else
                '빈 전사 또는 문자 형식 오류' if not isinstance(text,str) or not text.strip() else
                '손상된 전사 문자 확인 필요' if row.get('encoding_review') and not row.get('corrected') else None)
        if reason:
            safe_time=lambda value:value if type(value) in (int,float) and math.isfinite(value) else None
            rejected.append({'id':key,'source_id':row.get('id',str(i)),
                'start_ms':safe_time(start),'end_ms':safe_time(end),'reason':reason});continue
        if isinstance(row.get('id'),str):
            identity=(row['id'],json.dumps(row,ensure_ascii=False,sort_keys=True))
            if identity in seen:
                rejected.append({'id':key,'source_id':row['id'],'start_ms':start,'end_ms':end,
                                 'reason':'동일 원출력 항목의 중복 입력 · 먼저 읽은 원문 유지'});continue
            seen.add(identity)
        name=row.get('speaker_name') or '화자 미분석'
        unknown=row.get('status')=='failed' or name in ('화자인식 실패','화자 인식 실패','화자 미분석')
        tag='불명' if unknown else ('확인 ' if row.get('status')=='confirmed' else '추정 ')+speakers.setdefault(name,'P'+str(len(speakers)+1))
        parts=[text[n:n+1200] for n in range(0,len(text),1200)]
        for n, part in enumerate(parts):
            result.append({'id':key+(f'p{n}' if len(parts)>1 else ''),'source_id':row.get('id',str(i)),
                'kind':'speech','start_ms':start,'end_ms':end,'text':part,'speaker':name,'speaker_tag':tag,
                'corrected':bool(row.get('corrected')),'fragment':len(parts)>1,
                'quality_flags':[flag for flag in FLAGS if row.get(flag)]})
    return result,rejected


def rows(source): return prepare(source)[0]


def records(selected):
    return [{'id':r['id'],'text':r['text'],'speaker':r['speaker_tag'],
             'manual':r['corrected'],'signals':r['quality_flags']} for r in selected]


def reference(active):
    if not active:return None
    evidence=[r for r in active['input']['evidence'] if r['kind']=='speech']
    # 전체 원문은 최종 대조에서 읽는다. 다음 경계 판단에는 끝부분만 제한해서 전달한다.
    return {'title_hint':active['summary']['title'],'source_tail':records(evidence[-4:]),'reference_only':True}
