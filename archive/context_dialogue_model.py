"""대화와 경계는 한 번에 판단하고 확정된 채팅은 묶어서 짧게 정리한다."""
import json
import uuid
from . import context_evidence as ev, context_dialogue_input as di, context_tokens as tokens
from .context_flat_model import POLICY
from .context_topic_summary import prompt
from .source import check_cancel
from .storage import read_json, save_json

REVISION=2
MAX_TOPICS=12


class SplitRequired(ValueError):pass


def dialogue_prompt(rows, active):
    return prompt(POLICY+'\n대사만으로 주제를 구분한다. P번호는 화자 추정 구별이고 ?는 인식 불명이다. 이를 실명이나 등장인물로 해석하지 않는다. '
        'continues는 첫 새 발언이 열린 문맥의 연속인지다. 열린 문맥이 없으면 false다. '
        'topics는 새 발언을 처음부터 끝까지 빠짐없이 순서대로 한 번씩 나눈 목록이다. '
        '각 start_id와 end_id는 새 발언의 실제 ID다. 참조용 앞뒤 발언은 새 목록에 넣지 않는다. '
        '같은 이야기의 연속이면 첫 요약에 열린 문맥의 앞·중간 핵심을 유지한다. '
        'title은 짧은 제목, context는 2~3문장이고 360자 이내다. 정보가 부족하면 한 문장만 쓴다. '
        '각 요약에는 그 start_id부터 end_id까지의 대사만 포함한다. 뒤 발언에서 알게 되는 사건을 앞 요약에 미리 쓰지 않는다. '
        '참조용 열린 문맥은 continues=true인 첫 요약에만 반영한다. 목록 마지막의 미완성 발언을 결말이나 새 사건으로 완성하지 않는다. '
        '사건 설명의 원인·과정·결과와 예시는 같은 이야기다. 한 작품이라도 별개 사건으로 실제 전환될 때만 나누고 항목 수를 채우지 않는다. '
        '부정·거짓말·가정이 가리키는 대상과 누가 누구에게 한 행동인지를 구별한다. 근거가 불확실한 세부사항은 확정하지 않는다. '
        '?는 다른 사람이 말한다는 증거가 아니다. P번호와 ?를 제목이나 설명에 노출하지 않는다.',
        {'열린문맥':di.brief(active),'새발언':di.lines(rows)})


def dialogue_schema(rows, active=None):
    return ev.obj({'continues':{'type':'boolean'} if active else {'type':'boolean','enum':[False]},'topics':ev.array(ev.obj({
        'start_id':ev.enum(r['id'] for r in rows),'end_id':ev.enum(r['id'] for r in rows),
        'title':ev.string(80),'context':ev.string(360)}),MAX_TOPICS,1)})


def validate_dialogue(raw, rows, active):
    if not isinstance(raw,dict) or set(raw)!={'continues','topics'} or type(raw['continues']) is not bool:
        raise ValueError('대화 경계 응답 형식이 올바르지 않습니다')
    if raw['continues'] and not active:raise ValueError('이어갈 문맥이 없습니다')
    parts=raw['topics'];ids=[r['id'] for r in rows];cursor=0
    if not isinstance(parts,list) or not 1<=len(parts)<=MAX_TOPICS:raise ValueError('문맥 목록이 비어 있거나 너무 많습니다')
    if len(parts)==MAX_TOPICS:raise SplitRequired('주제 목록 한도에 도달해 입력을 나누어 확인합니다')
    for part in parts:
        if not isinstance(part,dict) or set(part)!={'start_id','end_id','title','context'}:raise ValueError('문맥 항목 형식이 올바르지 않습니다')
        if cursor>=len(ids) or part['start_id']!=ids[cursor] or part['end_id'] not in ids[cursor:]:
            raise ValueError('발언 경계가 누락·중복되거나 순서가 맞지 않습니다')
        cursor=ids.index(part['end_id'])+1
    if cursor!=len(ids):raise ValueError('처리하지 않은 발언이 남아 있습니다')
    return all(isinstance(p[k],str) and 0<len(p[k].strip())<=limit for p in parts for k,limit in [('title',80),('context',360)])


def call(job, folder, key, value, text, schema, validate):
    from .context_job import EngineError, FatalEngineError, OutputLimitError
    signature=ev.digest([REVISION,job.model_info,text,schema])
    file=folder/(key+'-'+signature[:20]+'.json')
    if file.exists():
        saved=read_json(file)
        if saved['signature']!=signature:raise ValueError('추론 체크포인트의 입력이 다릅니다')
        if validate(saved['raw']) is not False:
            if getattr(job,'input',{}).get('version') in (8,9,10,11,12):
                from .context_metrics import record
                record(folder,{'stage':key,'checkpoint_reused':True})
            return saved['raw']
    original=text;seconds=0
    for attempt in range(2):
        check_cancel(job.stop)
        if getattr(job,'input',{}).get('version')==10:
            if getattr(job,'request_budget',10)<=0:raise ev.ModelResponseError('이 범위의 추가 요청 예산을 소진했습니다')
            job.request_budget=getattr(job,'request_budget',10)-1
        count=job.tokenizer.count(text)
        output=getattr(job,'output_tokens',tokens.OUTPUT)
        if count+output+tokens.MARGIN>tokens.CONTEXT:raise SplitRequired('출력 여유를 포함한 문맥 한도를 넘었습니다')
        attempt_folder=folder/(key+'-'+uuid.uuid4().hex)
        if getattr(job,'input',{}).get('version') in (8,9,10,11,12):
            from .context_metrics import record
            record(folder,{'stage':key,'attempt':attempt,'folder':attempt_folder.name,'checkpoint_reused':False})
        try:
            raw,elapsed=job.infer_value(value,attempt_folder,text,schema);seconds+=elapsed
            save_json(attempt_folder/'tokens.json',{'prompt_tokens':count,'output_reserve':output})
            valid=validate(raw)
        except SplitRequired:raise
        except (json.JSONDecodeError,UnicodeDecodeError,EngineError,ValueError,TypeError,KeyError,IndexError) as error:
            if getattr(job,'input',{}).get('version') in (10,12) and isinstance(error,OutputLimitError):raise SplitRequired(str(error)) from error
            if isinstance(error,FatalEngineError):raise
            if attempt:raise ev.ModelResponseError(str(error)) from error
            text=original.replace('<|im_end|>\n<|im_start|>user', '\n직전 응답 검사를 통과하지 못했습니다. 발언 ID의 연속 범위와 필수 필드를 확인하세요.<|im_end|>\n<|im_start|>user',1)
            continue
        check_cancel(job.stop)
        if valid is not False:save_json(file,{'signature':signature,'raw':raw,'seconds':seconds,'prompt_tokens':count})
        return raw


def chat_prompt(items):
    data=[]
    for item in items:
        chats=[r for r in item['input']['evidence'] if r['kind']=='chat']
        data.append({'id':item['id'],'대화':[r['text'] for r in item['summary']['context']],'채팅':[[r['id'],r['text'],r.get('count',1)] for r in chats]})
    return prompt('확정된 문맥별 대표 채팅을 한국어로 요약한다. 각 문맥의 ID별 chat에 관측 내용만 1~2문장, 240자 이내로 쓴다. '
        'relation은 대화와 같은 구체적 내용이 확인될 때만 160자 이내로 비교하고 불명확하면 빈 문자열이다. '
        '공지·후원·다른 사건·도배일 수 있으므로 시간 겹침이나 ㅋㅋ만으로 발언이 재미있거나 반응을 유발했다고 단정하지 않는다. '
        '대화 근거가 없으면 relation은 빈 문자열이다. 채팅 표본으로 전체 시청자의 생각을 단정하지 않는다. '
        'C번호나 채팅 원문을 나열하지 말고 공통 반응을 짧게 바꿔 쓴다. 주제 경계를 바꾸지 않는다.',data)


def chat_schema(items):
    return ev.obj({'items':ev.array(ev.obj({'id':ev.enum(r['id'] for r in items),
        'chat':{'type':'string','maxLength':240},'relation':{'type':'string','maxLength':160}}),len(items),1)})


def validate_chat(raw, items):
    if not isinstance(raw,dict) or set(raw)!={'items'} or not isinstance(raw['items'],list):raise ValueError('채팅 설명 목록 형식 오류')
    valid={r['id'] for r in items};seen=set()
    for row in raw['items']:
        if not isinstance(row,dict) or set(row)!={'id','chat','relation'} or row['id'] not in valid or row['id'] in seen:raise ValueError('채팅 설명의 문맥 ID 오류')
        seen.add(row['id'])
    return seen==valid and all(isinstance(r[k],str) and len(r[k])<=limit for r in raw['items'] for k,limit in [('chat',240),('relation',160)])
