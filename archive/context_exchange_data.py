"""빠른 주제·외부 결과의 공통 ID 계약. 외부 응답은 원본 시각을 쓸 수 없다."""
import json
import math
from . import context_input, context_adaptive_input, context_evidence as ev
from .context_job import local
from .storage import read_json

REVISION = 1
MODES = ('timestamps', 'detail')
MAX_RESULT_BYTES = 10 * 1024**2


def snapshot(path, vod, selection, include_chat=False, offset=0):
    if not isinstance(selection, dict):raise ValueError('분석할 전사를 선택하세요')
    value=context_input.source(path,vod,offset,selection,include_chat=include_chat)
    rows,rejected=context_adaptive_input.prepare(value)
    rows.sort(key=lambda r:r['start_ms'])  # 같은 시각의 긴 발언 조각·겹친 발화는 원래 순서를 유지한다.
    if not rows:raise ValueError('사용 가능한 전사가 없습니다')
    chats=[]
    for i,r in enumerate(value['chat']):
        at=r.get('offset_ms');text=r.get('text')
        if type(at) not in (int,float) or not math.isfinite(at) or not isinstance(text,str) or not text.strip():continue
        at=max(0,round(at+offset))
        if at<=value['duration_ms']:chats.append(dict(id=f'C{i}',kind='chat',start_ms=at,end_ms=at,text=text))
    chats.sort(key=lambda r:(r['start_ms'],r['id']))
    return {'rows':rows,'chat':chats,'duration_ms':value['duration_ms'],'input_selection':value['input_selection'],
            'input_label':value['input_label'],'rejected':rejected,'include_chat':include_chat,'chat_offset_ms':offset}


def fingerprint(source):
    return ev.digest({k:v for k,v in source.items() if k!='input_label'})


def stale(path,vod,saved):
    try:return fingerprint(snapshot(path,vod,saved['input_selection'],saved['include_chat'],saved['chat_offset_ms']))!=saved['fingerprint']
    except (ValueError,OSError,KeyError,TypeError):return True


def strict_json(text):
    if not isinstance(text,str) or len(text.encode('utf-8'))>MAX_RESULT_BYTES:raise ValueError('결과 JSON은 10MiB 이내로 입력하세요')
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('중복 JSON 키: '+k[:80])
            result[k]=v
        return result
    def constant(_):raise ValueError('유효하지 않은 JSON 숫자')
    try:return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)
    except (json.JSONDecodeError,RecursionError) as error:raise ValueError('완결된 JSON만 입력하세요: '+str(error)[:180]) from None


def records(rows):
    return [{k:r[k] for k in ('id','start_ms','end_ms','text')}|
            ({'speaker':r['speaker_tag'],'manual':r['corrected']} if r['kind']=='speech' else {}) for r in rows]


def validate(raw, rows, chats=(), mode='timestamps', allow_continue=True):
    if not isinstance(raw,dict) or set(raw)!={'continues_previous','topics'} or type(raw['continues_previous']) is not bool:
        raise ValueError('continues_previous와 topics 형식을 확인하세요')
    if raw['continues_previous'] and not allow_continue:raise ValueError('첫 묶음은 이전 주제와 연결할 수 없습니다')
    topics=raw['topics'];ids=[r['id'] for r in rows];chat_ids={r['id'] for r in chats};starts=[]
    if not isinstance(topics,list) or not 1<=len(topics)<=min(len(rows),1000):raise ValueError('주제 목록이 비었거나 너무 많습니다')
    required={'start_id','title','evidence_ids','review_needed'}
    if mode=='detail':required|={'speech_summary','chat_summary','chat_evidence_ids'}
    for p in topics:
        if not isinstance(p,dict) or set(p)!=required or not isinstance(p['start_id'],str) or p['start_id'] not in ids:
            raise ValueError('주제 필드 또는 시작 발언 ID가 올바르지 않습니다')
        if not isinstance(p['title'],str) or not p['title'].strip() or len(p['title'])>100:raise ValueError('제목은 1~100자로 입력하세요')
        if type(p['review_needed']) is not bool:raise ValueError('review_needed는 참·거짓이어야 합니다')
        refs=p['evidence_ids']
        if not isinstance(refs,list) or not 1<=len(refs)<=20 or any(not isinstance(x,str) or x not in ids for x in refs):
            raise ValueError('제목 근거는 이 묶음의 발언 ID 1~20개로 지정하세요')
        if mode=='detail':
            if any(not isinstance(p[k],str) or len(p[k])>2000 for k in ('speech_summary','chat_summary')) or not p['speech_summary'].strip():raise ValueError('대화 요약은 필수이며 요약문은 각각 2,000자 이내입니다')
            refs=p['chat_evidence_ids']
            if not isinstance(refs,list) or len(refs)>20 or any(not isinstance(x,str) or x not in chat_ids for x in refs):raise ValueError('채팅 근거 ID를 확인하세요')
            if bool(p['chat_summary'].strip())!=bool(refs):raise ValueError('채팅 설명과 채팅 근거를 함께 입력하세요')
        starts.append(ids.index(p['start_id']))
    if starts[0]!=0 or any(a>=b for a,b in zip(starts,starts[1:])):raise ValueError('첫 발언부터 주제 시작을 중복 없이 시간순으로 지정하세요')
    for p,a,b in zip(topics,starts,starts[1:]+[len(ids)]):
        if any(x not in ids[a:b] for x in p['evidence_ids']):raise ValueError('다른 주제의 발언을 근거로 사용할 수 없습니다')
        end=rows[b]['start_ms'] if b<len(rows) else math.inf
        if mode=='detail' and any(not rows[a]['start_ms']<=r['start_ms']<end for r in chats if r['id'] in p['chat_evidence_ids']):raise ValueError('다른 주제 시각의 채팅 근거입니다')
    return True


def render_items(source, chunks, replies, mode):
    """누락 묶음을 넘어 병합하지 않는다. 완료 묶음은 새 결과 버전에서 재구성한다."""
    items=[];active=None;allrows=source['rows'];chats={r['id']:r for r in source['chat']}
    for index,chunk in enumerate(chunks):
        selected=allrows[chunk['first']:chunk['last']];raw=replies.get(chunk['id'])
        if not raw:
            active=None
            if chunk.get('error'):
                items.append(card(selected,'타임스탬프 처리 실패',[],source)|{'failed':True,'error':chunk['error'],'copy_ready':False})
            continue
        starts=[next(i for i,r in enumerate(selected) if r['id']==p['start_id']) for p in raw['topics']]
        for n,(part,a,b) in enumerate(zip(raw['topics'],starts,starts[1:]+[len(selected)])):
            owned=selected[a:b]
            item=card(owned,part['title'],part['evidence_ids'],source)
            item['evidence_review']=part['review_needed']
            if mode=='detail':
                item['summary']['context']=[{'text':part['speech_summary'],'evidence':part['evidence_ids']}]
                if part['chat_summary']:
                    item['summary']['chat']=[{'text':part['chat_summary'],'evidence':part['chat_evidence_ids']}]
                    item['input']['evidence'] += [chats[k] for k in part['chat_evidence_ids']]
                    item['input']['stats']['chat_used']=len(part['chat_evidence_ids'])
                    item['input']['stats']['chat_total']=len(part['chat_evidence_ids'])
                    item['chat_state']='complete'
            if n==0 and raw['continues_previous'] and active:
                active['end_ms']=item['end_ms'];active['end_id']=item['end_id']
                active['input']['range']['end_ms']=item['end_ms']
                active['input']['label']=context_input.clock(active['start_ms'])+' ~ '+context_input.clock(active['end_ms'])
                active['input']['evidence']+=item['input']['evidence']
                active['summary']['context']+=item['summary']['context'];active['summary']['chat']+=item['summary']['chat']
                active['evidence_review']|=item['evidence_review']
                active['input']['stats']['speech_used']+=len(owned)
                active['input']['stats']['speech_total']+=len(owned)
                for key in ('chat_used','chat_total'):active['input']['stats'][key]+=item['input']['stats'][key]
                if item['chat_state']=='complete':active['chat_state']='complete'
            else:
                if active and active['end_ms']>item['start_ms']:
                    if item['start_ms']>active['start_ms']:
                        active['end_ms']=item['start_ms']
                        active['input']['range']['end_ms']=active['end_ms']
                        active['input']['label']=context_input.clock(active['start_ms'])+' ~ '+context_input.clock(active['end_ms'])
                    else:item['time_review']=True
                if n==0 and raw['continues_previous']:item['boundary_error']=True
                items.append(item);active=item
        if active:
            active['provisional']=index<len(chunks)-1 and chunks[index+1]['id'] not in replies
    return items


def card(rows,title,refs,source):
    start=rows[0]['start_ms'];end=max(r['end_ms'] for r in rows)
    chosen=list({r['id']:r for r in rows[:2]+rows[-2:]+[r for r in rows if r['id'] in refs]}.values())
    return {'id':'topic-'+rows[0]['id'],'start_id':rows[0]['id'],'end_id':rows[-1]['id'],'start_ms':start,'end_ms':end,
        'copy_ready':True,'chat_state':'skipped','input':{
            'range':{'start_ms':start,'end_ms':end,'chat_offset_ms':source['chat_offset_ms']},
            'label':context_input.clock(start)+' ~ '+context_input.clock(end),'notes':['원본 전사 보존 · 제목과 요약은 자동 생성 결과입니다.'],
            'stats':{'speech_used':len(rows),'speech_total':len(rows),'chat_used':0,'chat_total':0},'evidence':chosen},
        'summary':{'title':title.strip(),'context':[],'chat':[],'relation':[],'uncertainties':[]}}


def result(path,vod,id):
    saved=read_json(local(path,f'runs/{id}/result.json'))
    source=read_json(local(path,f'runs/{id}/source.json'))
    work=read_json(local(path,f'runs/{id}/work.json'))
    chunks=work['chunks'];replies=work['replies'];items=render_items(source,chunks,replies,saved['mode'])
    done=sum(c['last']-c['first'] for c in chunks if c['id'] in replies or c.get('error'))
    return saved|{'scope':'full','version':11,'stale':stale(path,vod,saved),'items':items,'phase':'done' if saved['complete'] else 'timestamps',
        'done':done,'total':len(source['rows']),'stats':{'speech_total':len(source['rows']),'speech_used':done,'chat_total':len(source['chat']),'chat_used':len(source['chat']) if saved['complete'] else 0},
        'notes':['외부 결과의 형식만 검사했습니다. 원문을 확인하세요.' if saved['origin']=='external' else '전사로 주제 제목만 생성했습니다. 상세 근거 검토·채팅 요약은 생략했습니다.'],
        'input_rejections':source['rejected'],'item_failures':sum(bool(c.get('error')) for c in chunks),'boundary_failures':0}
