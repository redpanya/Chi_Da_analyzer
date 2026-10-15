"""형식 9: 시작 경계만 추론하고 범위 소유는 프로그램이 확정한다."""
from . import context_boundary as bounded, context_dialogue_model as model
from . import context_dialogue_input as di, context_evidence as ev, context_uncertainty
from .context_topic_summary import prompt
from .context_flat_model import POLICY

REVISION = 1
fit = bounded.fit
rows = context_uncertainty.rows


def build(selected, active):
    brief = di.brief(active) if active and active['summary'].get('context') else None
    return prompt(POLICY+'\n화자 불명이어도 내용 중심으로 요약한다. 추정 화자·게임·인용의 인물을 실제 발언자로 단정하지 않는다. '
        '새 발언이 같은 이야기면 이어 붙이고 독립된 주제·활동으로 바뀔 때만 나눈다. 짧은 반응이나 화자 변경만으로 나누지 않는다. '
        'topics에는 각 주제의 시작 ID만 순서대로 적는다. 끝은 다음 시작 바로 전으로 프로그램이 정한다. '
        f"첫 start_id는 반드시 {selected[0]['id']}다. 짧은 감탄사도 범위 안에 포함된다. "
        'continues는 첫 항목만 열린문맥의 연속인지를 뜻한다. 열린문맥이 없으면 false다. '
        'title은 구체적 제목, context는 근거가 있는 사실만 1~2문장·240자 이내다. 모호한 대사를 자연스럽게 꾸며 사실을 추가하지 않는다. '
        '먹었다/안 먹었다, 이미 있는 장소/새 목적지, 비유/실물, 질문/확정 사실을 구별한다. 원인 연결은 발언에 명시된 경우만 쓴다. '
        '자료 앞의 부정을 뒤 발언에 임의로 적용하지 않는다. 뒷주제의 사건을 앞주제 요약에 넣지 않는다. '
        '근거가 부족하면 context를 빈 문자열로 두고 title은 내용을 확인할 수 있는 범위로 쓴다. '
        '인식이 이상한 단어에 임의로 직업·물건·장소를 보충하지 않는다. '
        '이전문맥은 첫 항목 continues=true일 때만 사용한다. 사실 여부는 이후 원문 대조 단계에서 다시 확인한다.',
        {'열린문맥':brief,'새발언':di.lines(selected)})


def plan(remaining, active, tokenizer, limit=None):
    selected = fit(remaining[:limit] if limit else remaining,lambda r:build(r,active),tokenizer)
    return {'rows':selected,'active':active,'text':build(selected,active)}


def schema(plan):
    return ev.obj({'continues':{'type':'boolean'} if plan['active'] else {'type':'boolean','enum':[False]},
        'topics':ev.array(ev.obj({'start_id':ev.enum(r['id'] for r in plan['rows']),
            'title':ev.string(80),'context':{'type':'string','maxLength':240}}),12,1)})


def ranges(raw, selected, active):
    if not isinstance(raw,dict) or set(raw)!={'continues','topics'} or type(raw['continues']) is not bool:
        raise ValueError('대화 응답 형식 오류')
    if raw['continues'] and not active: raise ValueError('이어갈 문맥이 없습니다')
    parts=raw['topics'];ids=[r['id'] for r in selected]
    if not isinstance(parts,list) or not 1<=len(parts)<=12: raise ValueError('주제 목록 형식 오류')
    if len(parts)==12: raise model.SplitRequired('주제 한도에 도달해 작은 범위로 다시 확인합니다')
    starts=[]
    for part in parts:
        if not isinstance(part,dict) or set(part)!={'start_id','title','context'} or part['start_id'] not in ids:
            raise ValueError('주제 시작 ID 오류')
        starts.append(ids.index(part['start_id']))
    if starts[0]!=0 or any(a>=b for a,b in zip(starts,starts[1:])): raise ValueError('주제 시작 순서·중복 오류')
    return [(part,selected[a:b]) for part,a,b in zip(parts,starts,starts[1:]+[len(selected)])]


def infer(job, folder, plan, state):
    from . import context_dialogue as dialogue
    def valid(raw):
        parts=ranges(raw,plan['rows'],plan['active'])
        return all(isinstance(p['title'],str) and 0<len(p['title'].strip())<=80
                   and isinstance(p['context'],str) and len(p['context'])<=240 for p,_ in parts)
    raw=model.call(job,folder,'dialogue',{'rows':plan['rows'],'active':plan['active']},plan['text'],schema(plan),
        valid)
    for index,(part,selected) in enumerate(ranges(raw,plan['rows'],plan['active'])):
        if any(r.get('time_review') for r in selected):
            dialogue.close(state,selected[0]);state['items'].append(dialogue.failed(job.input['source'],selected,'전사 시각 확인 필요'));continue
        if not isinstance(part['title'],str) or not 0<len(part['title'].strip())<=80 or not isinstance(part['context'],str) or len(part['context'])>240:
            dialogue.close(state,selected[0]);state['items'].append(dialogue.failed(job.input['source'],selected,'해당 항목의 요약 형식 오류'));continue
        continued=index==0 and raw['continues'] and state['active'] is not None
        if continued:selected=[r for r in state['active']['input']['evidence'] if r['kind']=='speech']+selected
        else:dialogue.close(state,selected[0])
        item=di.card(job.input['source'],selected,part['title'],part['context'].strip() or '원문 대조 대기')
        if not part['context'].strip():item['summary']['context']=[]
        item.update(provisional=True,grounding_state='pending',range_sources=True)
        state['active']=item


def finalize(job, folder, source, state):
    from .context_grounding import finalize
    return finalize(job,folder,state)


def chat(job, folder, source, state):
    from .context_grounded_chat import process
    return process(job,folder,source,state)
