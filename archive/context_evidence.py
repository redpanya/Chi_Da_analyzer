"""계층 문맥의 고정 근거 ID·입력 한도·검사된 추론 체크포인트."""
import hashlib
import json
import uuid
from collections import OrderedDict
from . import context_input as inputs
from .context_topic_summary import prompt
from .context_policy import POLICY
from .source import check_cancel
from .storage import read_json, save_json

REVISION = 4
LIMIT = 11000


class ModelResponseError(ValueError):
    """엔진·저장 오류와 구분되는, 재시도 후에도 유효하지 않은 모델 응답."""


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def speech(source):
    return [dict(id='S'+str(i), source_id=r.get('id',str(i)), kind='speech', start_ms=r['start_ms'],
                 end_ms=r['end_ms'], text=r['text'], speaker=r.get('speaker_name') or '화자 미분석')
            for i,r in enumerate(source['speech']) if r['text'].strip() and not
            ((r.get('repeat_review') or r.get('boundary_review') or r.get('encoding_review') or r.get('quality_review')) and not r.get('corrected'))]


def compact(rows):
    return [[r['id'],r['start_ms'],r['end_ms'],r.get('speaker','채팅'),r['text'],r.get('count',1)] for r in rows]


def records(rows):
    return [{'id':r['id'],'시작':r['start_ms'],'끝':r['end_ms'],'내용':r['text'],'횟수':r.get('count',1)} for r in rows]


def size(rows):
    return len(json.dumps(compact(rows),ensure_ascii=False))


def passages(rows):
    """ASR의 한두 단어 조각을 연결하되 시작 ID와 원문 범위는 유지한다."""
    result=[]
    for row in rows:
        last=result[-1] if result else None
        if last and row['start_ms']-last['end_ms']<=1800 and row['end_ms']-last['start_ms']<=18000 and len(last['text'])+len(row['text'])<280:
            last.update(end_ms=max(last['end_ms'],row['end_ms']),text=last['text']+' '+row['text']);last['source_ids'].append(row['id'])
        else:result.append({**row,'speaker':'발언 원문','source_ids':[row['id']]})
    return result


def batches(rows, budget=6500):
    groups=[]; group=[]
    for row in rows:
        if size([row])>budget:raise ValueError('문맥 입력 한도를 넘는 발언이 있습니다. 전사를 확인하세요')
        if group and size(group+[row])>budget:
            groups.append(group);group=[]
        group.append(row)
    if group:groups.append(group)
    return groups


def window(source, rows, start, end, chat_budget=2500):
    selected=[r for r in rows if start<=r['start_ms']<end]
    chats=OrderedDict();total=0
    for i,row in enumerate(source['chat']):
        at=max(0,row['offset_ms']+source['chat_offset_ms']);text=(row.get('text') or '').strip()
        if not start<=at<end or not text:continue
        total+=1
        if text in chats:chats[text]['count']+=1
        else:chats[text]=dict(id='C'+str(i),kind='chat',start_ms=at,end_ms=at,text=text,count=1,
                              message_type=row.get('message_type'))
    chosen=inputs.sample(list(chats.values()),chat_budget) if chat_budget else []
    notes=list(source['notes'])+['화자는 추정 이름입니다. 발언에서 언급한 인물과 실제 발언자를 혼동하지 마세요.']
    if len(chosen)<len(chats):notes.append('채팅 본문은 시간순 표본입니다. 반응 통계는 전체 제공 채팅 기준입니다.')
    return {'range':{'start_ms':start,'end_ms':end,'chat_offset_ms':source['chat_offset_ms']},
            'label':inputs.clock(start)+' ~ '+inputs.clock(end),'notes':notes,
            'stats':{'speech_used':len(selected),'speech_total':sum(start<=r['start_ms']<end for r in source['speech']),
                     'chat_total':total,'chat_used':sum(r['count'] for r in chosen)},'evidence':selected+chosen}


def string(limit=180):return {'type':'string','minLength':1,'maxLength':limit}
def enum(values):return {'type':'string','enum':list(values)}
def obj(properties):return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
def array(items, maximum=100, minimum=0):return {'type':'array','items':items,'maxItems':maximum,'minItems':minimum}


def call(job, folder, key, value, instruction, data, schema, validate, policy=POLICY):
    """응답뿐 아니라 입력·지시·스키마까지 같은 성공 단위만 재사용한다."""
    instruction=policy+'\n'+instruction
    text=prompt(instruction,data)
    if len(json.dumps(data,ensure_ascii=False))>LIMIT:raise ValueError('문맥 입력이 너무 큽니다. 완료 단계는 보존했습니다')
    signature=digest([REVISION,text,schema]);file=folder/(key+'.json')
    if file.exists():
        saved=read_json(file)
        if saved.get('signature')!=signature:raise ValueError('문맥 처리 방식 또는 입력이 바뀌었습니다. 새 정리를 시작하세요')
        validate(saved['raw']);return saved['raw']
    check_cancel(job.stop)
    seconds=0
    for attempt in range(2):
        try:
            try:raw,elapsed=job.infer_value(value,folder/(key+'-'+uuid.uuid4().hex),text,schema)
            except json.JSONDecodeError as error:raise ModelResponseError('요약 JSON 형식이 올바르지 않습니다') from error
            seconds+=elapsed
            try:validate(raw)
            except (ValueError,TypeError,KeyError,IndexError) as error:raise ModelResponseError(str(error)) from error
            break
        except ModelResponseError as error:
            if attempt:raise
            check_cancel(job.stop)
            text=prompt(instruction+' 직전 응답이 검사를 통과하지 못했다: '+str(error)+'. 이 오류를 바로잡아 전체 JSON을 다시 출력한다.',data)
    check_cancel(job.stop)
    save_json(file,{'signature':signature,'raw':raw,'seconds':seconds})
    return raw


def progress(job,stage,label,done,total):
    job.update(message=label,progress={'stage':stage,'done':done,'total':total,'seconds':0})


def text(value,limit=180):
    if not isinstance(value,str) or not 1<=len(value.strip())<=limit:raise ValueError('문맥의 제목·설명 길이가 올바르지 않습니다')
    return value.strip()


def refs(ids, rows, kinds=None):
    found={r['id']:r for r in rows}
    if not isinstance(ids,list) or not ids or len(ids)>4 or any(not isinstance(i,str) or i not in found for i in ids):
        raise ValueError('문맥에서 원문에 없는 근거를 참조했습니다')
    if kinds and not kinds<={found[i]['kind'] for i in ids}:raise ValueError('문맥의 발언·채팅 근거가 부족합니다')
    return ids
