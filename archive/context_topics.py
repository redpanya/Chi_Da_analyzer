"""주제 전환 검출과 종료된 대화의 요약을 분리하고 진행 중인 주제를 보존한다."""
import uuid
from . import context_input as inputs, context_topic_summary as summary
from .context_job import local
from .source import check_cancel
from .storage import read_json, save_json, stamp


def schema(value,active=None):
    ids=[r['id'] for r in value['evidence'] if r['kind']=='speech']
    allowed=ids if active else ids[1:]
    title={'type':'string','minLength':1,'maxLength':150}
    change={'type':'object','properties':{'start':{'type':'string','enum':allowed or ids},'topic':title},'required':['start','topic'],'additionalProperties':False}
    properties={} if active else {'opening_topic':title}
    properties['changes']={'type':'array','maxItems':len(allowed),'items':change}
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def prompt(value,active,previous):
    system='''대화 주제의 전환 지점만 찾는다. 요약 본문은 생성하지 않는다. 같은 질문·사건·설명·진행 목표를 이어가는 동안 changes는 빈 배열이다. 화자 교대, 웃음, 감탄, 채팅 급증, 예시, 세부 설명, 같은 질문의 답변은 새 주제가 아니다. 별도의 구체적인 질문·사건·이야기로 실제로 전환할 때만 changes에 새 주제가 시작되는 현재 입력의 S 발언 ID와 짧은 topic을 넣는다. 단순히 같은 게임이라는 이유로 별개의 이야기를 합치지도 않는다. 판단이 모호하면 현재 주제를 유지하고 뒤의 발언으로 확인한다. 입력 시간이나 처리 경계는 주제 전환 근거가 아니다. 진행 중인 주제가 없으면 opening_topic에 첫 대화의 주제를 적는다. 프로그램이 첫 발언을 시작점으로 배정하므로 changes에는 그 이후의 실제 전환만 적는다. 이전 발언 ID는 경계로 출력하지 않는다. 근거 행의 열은 ID, 시작밀리초, 끝밀리초, 화자 또는 채팅, 내용, 반복횟수다. 채팅만으로 대화 주제를 바꾸지 않는다.'''
    system+=' opening_topic은 첫 대화, 각 changes의 topic은 반드시 그 start 발언 이후에 시작된 새 대화의 이름이다. 이전 주제 이름을 새 주제에 복사하지 않는다. 게임·요리·여행처럼 넓은 분류 대신 무엇을 설명하거나 질문하는지 구체적인 이름을 붙인다.'
    return summary.prompt(system,{'진행 중인 주제':active,'직전 발언':summary.compact(previous),'현재 범위':value['label'],'제한':value['notes'],'현재 근거':summary.compact(value['evidence'])})


def validate(raw,value,active):
    rows=[r for r in value['evidence'] if r['kind']=='speech'];ids={r['id']:r for r in rows}
    if not isinstance(raw,dict) or set(raw)!=({'changes'} if active else {'changes','opening_topic'}) or not isinstance(raw['changes'],list):raise ValueError('주제 전환 응답 형식이 올바르지 않습니다')
    changes=[];last=-1
    if not active:
        title=raw['opening_topic']
        if not isinstance(title,str) or not 1<=len(title.strip())<=150:raise ValueError('첫 대화 주제의 이름이 올바르지 않습니다')
        last=rows[0]['start_ms'];changes.append({'start_ms':last,'topic':title.strip()})
    for change in raw['changes']:
        if not isinstance(change,dict) or set(change)!={'start','topic'} or not isinstance(change['start'],str) or change['start'] not in ids or not isinstance(change['topic'],str) or not 1<=len(change['topic'].strip())<=150:raise ValueError('주제 전환에 없는 발언 또는 잘못된 주제를 사용했습니다')
        at=ids[change['start']]['start_ms']
        if at<=last or (active and at<=active['start_ms']):raise ValueError('주제 전환 시각이 중복되거나 역순입니다')
        changes.append({'start_ms':at,'topic':change['topic'].strip()});last=at
    if not active and (not changes or changes[0]['start_ms']!=rows[0]['start_ms']):raise ValueError('첫 대화 주제의 시작 발언이 없습니다')
    return changes


def process(job,saved,source):
    folder=local(job.path,f"runs/{saved['id']}");file=folder/'timeline.json'
    timeline=read_json(file) if file.exists() else {'done':0,'items':[],'seconds':0,'active':None}
    total=len(saved['chunks'])
    def close(active,end):
        result=summary.summarize(job,saved,source,active['start_ms'],end)
        timeline['items'].append(result);timeline['seconds']+=result['seconds']
    for index in range(timeline['done'],total):
        check_cancel(job.stop);chunk=saved['chunks'][index]
        job.update(message=f'대화 주제 전환 확인 · {chunk["label"]}',progress={'done':index,'total':total,'processed_ms':chunk['range']['start_ms'],'duration_ms':saved['duration_ms'],'stage':'topics','seconds':0})
        active=timeline['active']
        if chunk['state']=='pending':
            value=inputs.window(source,chunk['range'],whole=True)
            for row in value['evidence']:row['id']=row['id'][0]+str(index)+'_'+row['id'][1:]
            speech=[r for r in value['evidence'] if r['kind']=='speech']
            raw={'changes':[]};seconds=0
            if speech:
                previous=[{'id':'이전'+str(i),'kind':'speech',**r,'speaker':r.get('speaker_name','화자 미분석')} for i,r in enumerate(source['speech']) if r['start_ms']<chunk['range']['start_ms'] and not ((r.get('repeat_review') or r.get('boundary_review') or r.get('encoding_review')) and not r.get('corrected'))][-6:]
                raw,seconds=job.infer_value(value,folder/('detect-'+uuid.uuid4().hex),prompt(value,active,previous),schema(value,active))
                validate(raw,value,active)
            check_cancel(job.stop)
            name=f'chunk-{index}.json';save_json(folder/name,{'input':value,'changes':raw,'seconds':seconds})
            chunk.update(state='complete' if speech else 'gap',file=name);save_json(folder/'result.json',saved)
        data=read_json(folder/chunk['file']);value=data['input']
        speech=[r for r in value['evidence'] if r['kind']=='speech']
        if speech:
            for change in validate(data['changes'],value,active):
                if active:close(active,change['start_ms'])
                active=change|{'end_ms':change['start_ms']}
            active['end_ms']=min(source['duration_ms'],max(r['end_ms'] for r in speech))
        elif not active:
            timeline['items'].append({'start_ms':chunk['range']['start_ms'],'end_ms':chunk['range']['end_ms'],'gap':True,'input':value})
        check_cancel(job.stop)
        timeline.update(done=index+1,active=active);save_json(file,timeline)
        job.update(progress={'done':index+1,'total':total,'processed_ms':chunk['range']['end_ms'],'duration_ms':saved['duration_ms'],'stage':'topics','seconds':0})
    if timeline['active']:
        close(timeline['active'],source['duration_ms']);check_cancel(job.stop)
        timeline['active']=None;save_json(file,timeline)
    check_cancel(job.stop)
    from .context_full import fingerprint,current_source
    if fingerprint(current_source(job.path,job.vod,source['chat_offset_ms']))!=saved['fingerprint']:raise ValueError('처리 중 입력이 바뀌었습니다. 완료 부분은 보존합니다. 새 정리를 시작하세요')
    saved.update(complete=True,updated_at=stamp());save_json(folder/'result.json',saved)
