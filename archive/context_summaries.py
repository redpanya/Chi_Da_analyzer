"""확인된 이야기의 원문 요약과 근거를 유지하는 상위 요약."""
import json
from . import context_evidence as ev, context_input as inputs


def validate(raw,value):
    inputs.validate(raw,value['evidence'])
    for name in ('context','chat','relation'):
        if len(raw[name])>2 or any(len(r['text'])>650 for r in raw[name]):raise ValueError('문맥 설명이 너무 깁니다')


def infer(job,folder,key,value,data,parent=False):
    schema=inputs.schema(value['evidence'])
    schema['properties']['title'].update(minLength=1,maxLength=100)
    for name in ('context','chat','relation'):schema['properties'][name]['items']['properties']['text'].update(minLength=1,maxLength=650)
    instruction='''방송 대화의 문맥을 한국어로 간결하게 정리한다. title은 구체적인 제목이다. context는 실제 발언의 주된 내용 2~3문장, chat은 채팅에서 관측한 내용, relation은 발언과 채팅의 구체적 대응이 있을 때만 쓴다. 각 text에 실제 근거 ID evidence를 1~4개 연결한다. context는 S, chat은 C, relation은 S와 C가 모두 필요하다. 웃음 표현만으로 특정 발언 때문이라고 단정하지 말고 relation을 비운다. 감정·의도·인과관계·없는 장면을 추측하지 않는다. 인용·설명의 대상과 실제 방송 화자를 구분한다. 화자 인식 실패 등 자료의 상태는 대화 내용이 아니다. 인물 이름이 잘못 인식됐으면 임의로 고치거나 실제 인물로 확정하지 않는다. uncertainties는 제공된 자료의 제한에만 쓴다.'''
    if parent:instruction+=' 하위 요약의 시간순 큰 흐름을 짧게 정리한다. 세부 사건은 하위에 있으므로 모든 내용을 늘어놓지 않는다. 근거 ID는 하위 요약에서 실제로 사용한 것만 고른다.'
    return ev.call(job,folder,key,value,instruction,data,schema,lambda raw:validate(raw,value))


def story(job,folder,source,rows,item):
    selected=[r for r in rows if item['start_ms']<=r['start_ms']<item['end_ms']]
    parts=[];allrefs={};notes=[];stats={'speech_total':0,'speech_used':0,'chat_total':0,'chat_used':0}
    groups=ev.batches(selected,6000)
    for i,group in enumerate(groups):
        start=item['start_ms'] if i==0 else group[0]['start_ms']
        end=groups[i+1][0]['start_ms'] if i+1<len(groups) else item['end_ms']
        value=ev.window(source,rows,start,end,1800)
        raw=infer(job,folder,f"summary-{item['id']}-{i}",value,{'임시제목':item['title'],'제한':value['notes'],
            '방송발언':ev.records([r for r in value['evidence'] if r['kind']=='speech']),
            '시청자채팅':ev.records([r for r in value['evidence'] if r['kind']=='chat'])})
        parts.append(raw);allrefs.update((r['id'],r) for r in value['evidence']);notes.extend(value['notes'])
        for k,n in value['stats'].items():stats[k]=stats.get(k,0)+n
    value={'label':inputs.clock(item['start_ms'])+' ~ '+inputs.clock(item['end_ms']),
           'range':{'start_ms':item['start_ms'],'end_ms':item['end_ms']},'evidence':list(allrefs.values()),'notes':list(dict.fromkeys(notes)),'stats':stats}
    raw=reduce(job,folder,item['id'],parts,value) if len(parts)>1 else parts[0]
    if item.get('review'):raw['uncertainties'].append('이야기 경계 확인 필요: '+item['reason'])
    if item.get('parent_review'):raw['uncertainties'].append('상위 주제 연결 확인 필요: '+item['parent_review'])
    return {**item,'summary':raw,'input':value,'range_sources':False}


def reduce(job,folder,key,parts,value):
    level=0
    while len(parts)>1:
        groups=[];group=[]
        for part in parts:
            if group and len(json.dumps(group+[part],ensure_ascii=False))>6500:groups.append(group);group=[]
            group.append(part)
        if group:groups.append(group)
        if len(groups)==len(parts):raise ValueError('상위 요약 입력이 너무 큽니다. 완료된 하위 요약은 보존했습니다')
        reduced=[]
        for i,group in enumerate(groups):
            if len(group)==1:reduced.append(group[0]);continue
            ids={ref for p in group for name in ('context','chat','relation') for r in p[name] for ref in r['evidence']}
            part_value=value|{'evidence':[r for r in value['evidence'] if r['id'] in ids]}
            reduced.append(infer(job,folder,f'parent-{key}-{level}-{i}',part_value,{'시간순하위요약':group},True))
        parts=reduced;level+=1
    return parts[0]


def parent(job,folder,item,children):
    evidence={r['id']:r for c in children for r in c['input']['evidence']}
    stats={k:sum(c['input']['stats'].get(k,0) for c in children) for k in ('speech_total','speech_used','chat_total','chat_used')}
    value={'label':inputs.clock(item['start_ms'])+' ~ '+inputs.clock(item['end_ms']),'stats':stats,
           'evidence':list(evidence.values()),'notes':['상위 요약은 하위 원문 요약의 큰 흐름입니다. 세부 내용은 하위 이야기를 확인하세요.']}
    raw=reduce(job,folder,item['id'],[c['summary'] for c in children],value)
    if item.get('review'):raw={**raw,'uncertainties':raw['uncertainties']+['상위 주제 연결에 불확실한 항목이 있습니다. 하위 원문을 확인하세요.']}
    return {**item,'summary':raw,'input':value,'range_sources':False}
