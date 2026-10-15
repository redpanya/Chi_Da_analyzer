"""형식 8 전용 입력·소유 범위. 형식 7의 프롬프트와 계약은 변경하지 않는다."""
import re
from . import context_dialogue_input as di, context_dialogue_model as model
from . import context_evidence as ev, context_tokens as tokens
from .context_topic_summary import prompt
from .context_flat_model import POLICY

REVISION = 2
REFERENCE_TOKENS = 768
LOOKAHEAD_TOKENS = 256


def rows(source):
    return [row | {'ordinal':i, 'source_ordinal':int(re.match(r'S(\d+)',row['id'])[1])}
            for i,row in enumerate(di.rows(source))]


def lines(selected):
    result=[];last=None;speaker=None
    for row in selected:
        if last:
            if row['ordinal'] != last['ordinal']+1:result.append('[참고 발언 사이 생략]')
            elif row['source_ordinal'] > last['source_ordinal']+1:result.append('[검토 대상 전사 제외]')
            elif row['start_ms']-last['end_ms'] >= di.GAP_MS:result.append('[전사 시각 간격 30초 이상 · 무음 여부 미확인]')
        name=row.get('speaker_tag','?')
        if name!=speaker:result.append('['+name+']');speaker=name
        result.append(row['id']+' '+row['text']);last=row
    return '\n'.join(result)


def fit(rows, build, tokenizer, budget=tokens.TARGET):
    """작은 후보부터 두 배씩 탐색. 최종 판단은 고유 템플릿의 실제 토큰 수다."""
    if not rows:return []
    if tokenizer.count(build(rows[:1]))>budget:raise model.SplitRequired('단일 발언과 참고가 입력 예산을 넘었습니다')
    lo=1;hi=min(len(rows),2)
    while hi>lo and tokenizer.count(build(rows[:hi]))<=budget:
        lo=hi
        if hi==len(rows):return rows[:hi]
        hi=min(len(rows),hi*2)
    while lo+1<hi:
        mid=(lo+hi)//2
        if tokenizer.count(build(rows[:mid]))<=budget:lo=mid
        else:hi=mid
    return rows[:lo]


def reference_budget(selected, tokenizer, budget):
    """최대 여섯 원문을 발췌. 모델에 보낸 발췌만 기록하며 원본은 수정하지 않는다."""
    selected=[dict(r) for r in selected]
    while selected and tokenizer.count(prompt('',lines(selected)))>budget:
        longest=max(selected,key=lambda r:len(r['text']))
        if len(longest['text'])>32:
            longest['text']=longest['text'][:max(16,len(longest['text'])//2)]+' [발췌]'
        else:selected.pop(0)
    return selected


def references(active, tokenizer):
    if not active:return None
    evidence=[r for r in active['input']['evidence'] if r['kind']=='speech']
    n=len(evidence)
    indices=sorted({0,n//3,2*n//3,*range(max(0,n-3),n)})
    selected=reference_budget([evidence[i] for i in indices],tokenizer,REFERENCE_TOKENS)
    return {'title':active['summary']['title'],'summary':active['summary']['context'][0]['text'],
            'rows':selected}


def build(selected, previous, following):
    return prompt(POLICY+'\n대사만으로 같은 이야기인지 새 주제인지 판단한다. '
        'topics는 참고 발언을 골라 적는 목록이 아니라 새발언 전체를 연속 범위로 빠짐없이 나눈 목록이다. '
        f"첫 start_id는 반드시 {selected[0]['id']}, 마지막 end_id는 반드시 {selected[-1]['id']}다. "
        '각 다음 start_id는 직전 end_id 바로 다음 새 발언 ID다. 중간의 짧은 발언도 범위에 포함한다. '
        '새 주제가 실제 시작된 발언부터 새 범위로 잡고 이전 이야기의 마무리를 다음 문맥으로 옮기지 않는다. '
        'continues는 첫 새 발언이 열린문맥과 같은 이야기인지다. 없으면 false다. '
        '원인·과정·결과·예시는 같은 이야기다. 시간 길이·화자 교체·참고 생략만으로 나누지 않는다. '
        '이전 구체적 사건·질문이 끝나고 독립적인 이야기나 다음 활동을 시작하면 새 문맥이다. 단순 비교로 다른 작품을 언급하는 경우와 다음 작품으로 실제 넘어가는 경우를 구별한다. '
        '열린 문맥을 계속 잇기 위해 제목·요약을 "미디어 분석" 같은 큰 분류로 넓히지 않는다. '
        '각 title은 짧은 제목, context는 360자 이내 1~3문장이다. '
        '핵심 인물·행동·비교·주장을 구체적으로 적는다. "심층적으로 분석한다" 같은 표현으로 실제 내용을 대체하지 않는다. '
        '같은 이야기로 이어지는 첫 요약에는 열린문맥의 앞·중간 핵심을 유지한다. '
        '다음참고는 경계 판단 전용이다. 다음참고의 사건·결말·ID를 이번 요약이나 evidence_ids에 넣지 않는다. '
        'evidence_ids에는 해당 요약을 뒷받침하는 새 발언 ID를 1~4개 고른다. '
        'continues=true인 첫 요약만 실제 제공된 열린문맥 참고 ID도 쓸 수 있다. 다른 문맥 ID는 쓰지 않는다. '
        '근거가 없으면 빈 목록으로 남긴다. 부정·가정·행위 주체를 구별하고 불확실한 사실을 확정하지 않는다. '
        '화자가 전달하는 이야기·인용 질문의 대상과 실제 말하는 사람을 구별한다. '
        '검토는 주제 경계와 누가 누구에게 무엇을 했는지에 집중한다. 규칙·전체 대사를 재서술하거나 요약 초안을 반복 작성하지 말고 간결하게 검토한 뒤 최종 JSON을 한 번 작성한다. '
        'P번호와 ?는 화자 추정 표지이며 등장인물·실명으로 해석하거나 요약에 노출하지 않는다.',
        {'열린문맥':None if not previous else {'제목':previous['title'],'요약':previous['summary'],'참고발언':lines(previous['rows'])},
         '새발언':lines(selected),'다음참고_요약금지':lines(following)})


def plan(remaining, active, tokenizer, limit=None):
    previous=references(active,tokenizer)
    eligible=remaining[:limit] if limit else remaining
    # 다음 참고를 넣을 여유를 먼저 예약하되, 한 발언도 안 들어가면 참고부터 버린다.
    try:selected=fit(eligible,lambda r:build(r,previous,[]),tokenizer,tokens.TARGET-LOOKAHEAD_TOKENS)
    except model.SplitRequired:
        previous=None
        selected=fit(eligible,lambda r:build(r,None,[]),tokenizer)
    following=remaining[len(selected):len(selected)+4]
    while following and tokenizer.count(prompt('',lines(following)))>LOOKAHEAD_TOKENS:following=following[:-1]
    while following and tokenizer.count(build(selected,previous,following))>tokens.TARGET:following=following[:-1]
    text=build(selected,previous,following)
    if tokenizer.count(text)>tokens.TARGET:raise model.SplitRequired('입력 예산을 넘었습니다')
    return {'rows':selected,'previous':previous,'following':following,'text':text}


def schema(plan):
    value=model.dialogue_schema(plan['rows'],plan['previous'])
    properties=value['properties']['topics']['items']
    ids=[r['id'] for r in plan['rows']+(plan['previous'] or {}).get('rows',[])]
    properties['properties']['evidence_ids']=ev.array(ev.enum(ids),4,0)
    properties['required'].append('evidence_ids')
    return value


def validate(raw, plan):
    # 경계·본문 오류는 기존 부분 실패 규칙을 따른다. 근거만 잘못된 경우 재추론하지 않는다.
    if not isinstance(raw,dict) or not isinstance(raw.get('topics'),list):raise ValueError('문맥 목록 형식 오류')
    cleaned=[]
    for part in raw['topics']:
        if not isinstance(part,dict) or set(part)-{'start_id','end_id','title','context','evidence_ids'}:raise ValueError('문맥 항목 형식 오류')
        cleaned.append({k:v for k,v in part.items() if k!='evidence_ids'})
    return model.validate_dialogue(raw|{'topics':cleaned},plan['rows'],plan['previous'])


def apply(source, plan, raw, state):
    from . import context_dialogue as dialogue
    ids=[r['id'] for r in plan['rows']]
    for index,part in enumerate(raw['topics']):
        selected=plan['rows'][ids.index(part['start_id']):ids.index(part['end_id'])+1]
        continues=index==0 and raw['continues'] and state['active'] is not None
        allowed={r['id'] for r in selected}
        if continues:allowed.update(r['id'] for r in (plan['previous'] or {}).get('rows',[]))
        refs=part.get('evidence_ids')
        valid=isinstance(refs,list) and 1<=len(refs)<=4 and all(isinstance(r,str) and r in allowed for r in refs) and len(set(refs))==len(refs)
        dialogue.apply(source,selected,{'continues':bool(continues),'topics':[part]},state)
        item=state['active']
        if item is None:continue
        item['summary']['context'][0]['evidence']=refs if valid else []
        item['evidence_review']=not valid
        item['range_sources']=False


def infer(job, folder, plan, state):
    value={k:v for k,v in plan.items() if k!='text'}
    raw=model.call(job,folder,'dialogue',value,plan['text'],schema(plan),lambda raw:validate(raw,plan))
    apply(job.input['source'],plan,raw,state)
