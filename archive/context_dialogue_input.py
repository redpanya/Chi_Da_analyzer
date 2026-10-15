"""대사 ID와 원본 시각 대응. 모델 입력과 화면의 원문 자료를 분리한다."""
import math
from . import context_evidence as ev

GAP_MS = 30000


def rows(source):
    result = [];speakers={}
    for row in ev.speech(source):
        valid = all(type(row[k]) in (int,float) and math.isfinite(row[k]) for k in ('start_ms','end_ms'))
        valid = valid and 0 <= row['start_ms'] < row['end_ms'] <= source['duration_ms']
        # 세부 시각이 없는 긴 발언은 내용을 보존하고 내부 경계의 시각은 확인 대상으로 남긴다.
        text = row['text']
        name=row.get('speaker') or '화자 미분석'
        tag='?' if name in ('화자인식 실패','화자 인식 실패','화자 미분석') else speakers.setdefault(name,'P'+str(len(speakers)+1))
        parts = [text[i:i+1200] for i in range(0,len(text),1200)]
        for i, part in enumerate(parts):
            result.append(row|{'id':row['id']+(f'p{i}' if len(parts)>1 else ''), 'text':part,
                               'time_review':not valid, 'fragment':len(parts)>1,'speaker_tag':tag})
    return result


def lines(rows):
    result=[];speaker=None;last=None
    for row in rows:
        if last and row['start_ms']-last['end_ms']>=GAP_MS:result.append('[긴 공백]')
        name=row.get('speaker_tag','?')
        if name!=speaker:result.append('['+name+']');speaker=name
        result.append(row['id']+' '+row['text'])
        last=row
    return '\n'.join(result)


def brief(active):
    if not active:return None
    evidence=[r for r in active['input']['evidence'] if r['kind']=='speech']
    selected=list({r['id']:r for r in evidence[:2]+evidence[-4:]}.values())
    return {'제목':active['summary']['title'],'요약':active['summary']['context'][0]['text'],
            '참조용_앞뒤발언':lines(selected)}


def value(source, selected, start=None, end=None, chat_budget=0):
    start=selected[0]['start_ms'] if start is None else start
    end=max(r['end_ms'] for r in selected) if end is None else end
    data=ev.window(source, [], max(0,start), min(source['duration_ms'],end), chat_budget)
    data['evidence']=selected+data['evidence']
    data['stats']['speech_used']=len({r['source_id'] for r in selected})
    if any(r.get('fragment') for r in selected):data['notes'].append('긴 발언 내부를 나누어 읽었습니다. 발언 내부의 세부 시각은 확인이 필요합니다.')
    return data


def card(source, selected, title, context):
    data=value(source,selected)
    return {'id':'dialogue-'+selected[0]['id'],'start_id':selected[0]['id'],'end_id':selected[-1]['id'],
            'start_ms':data['range']['start_ms'],'end_ms':data['range']['end_ms'], 'input':data,
            'summary':ev.inputs.narrative({'title':title,'context':context,'chat':'','relation':''},selected),
            'range_sources':True,'chat_state':'pending'}


def close(item, following=None):
    if following and item['end_ms']>following['start_ms']:
        if following['start_ms']>item['start_ms']:item['end_ms']=following['start_ms']
        else:item['time_review']=True
    item.pop('provisional',None)
    return item
