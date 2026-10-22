"""파일별 검사를 모아 보여주고 명시적으로 동의한 정상 묶음만 저장한다."""
from collections import Counter
from . import context_exchange as exchange, context_exchange_data as data, context_exchange_zip as zipper, context_evidence as ev
from .storage import Conflict


def checked(path,vod,values):
    if ('text' in values)==('archive' in values):raise ValueError('결과 JSON 또는 ZIP 하나를 선택하세요')
    files=zipper.unpack(values['archive']) if 'archive' in values else [('입력 JSON',values['text'],None)]
    entries=[];errors=[]
    for name,text,error in files:
        try:
            if error:raise ValueError(error)
            value=data.strict_json(text.lstrip('\ufeff') if isinstance(text,str) else text)
            rows=value['results'] if isinstance(value,dict) and set(value)=={'results'} else [value]
            if not isinstance(rows,list) or not rows:raise ValueError('결과 목록이 비었습니다')
            for index,entry in enumerate(rows,1):entries.append((name,index,entry))
        except ValueError as ex:errors.append({'file':name,'chunk':'','message':str(ex)})
    if len(entries)>5000:raise ValueError('가져올 묶음은 최대 5,000개입니다')
    export_ids={e.get('export_id') for _,_,e in entries if isinstance(e,dict) and isinstance(e.get('export_id'),str)}
    if len(export_ids)>1:raise ValueError('다른 외부 작업의 결과가 섞여 있습니다. 같은 내보내기 ID의 결과만 함께 가져오세요')
    if not export_ids:
        errors.extend({'file':name,'chunk':str(i),'message':'내보내기 ID가 있는 결과 JSON 객체가 필요합니다'} for name,i,_ in entries)
        return None,None,None,{'token':None,'accepted':0,'received':0,'total':0,'topics':[],'complete':False,'errors':errors,'files':len(files),'missing':[]}
    saved,source=exchange.load_active(path,vod,export_ids.pop())
    counts=Counter(e['chunk_id'] for _,_,e in entries if isinstance(e,dict) and isinstance(e.get('chunk_id'),str))
    replies=dict(saved['replies']);accepted=0
    for name,index,entry in entries:
        chunk=entry.get('chunk_id') if isinstance(entry,dict) else None
        try:
            if isinstance(chunk,str) and counts[chunk]>1:raise ValueError('같은 묶음 결과가 여러 파일/항목에 있습니다. 사용할 결과 하나만 남기세요')
            id,raw=exchange.validate_entry(saved,source,entry);replies[id]=raw;accepted+=1
        except (ValueError,TypeError) as ex:
            errors.append({'file':name,'chunk':chunk if isinstance(chunk,str) else str(index),'message':str(ex) if isinstance(ex,ValueError) else '결과 필드 형식을 확인하세요'})
    token=ev.digest([saved['fingerprint'],saved['replies'],replies,files])
    items=data.render_items(source,saved['chunks'],replies,saved['mode'])
    info={'token':token,'export_id':saved['id'],'accepted':accepted,'received':len(replies),'total':len(saved['chunks']),
          'topics':[{'start_ms':r['start_ms'],'title':r['summary']['title']} for r in items],
          'complete':len(replies)==len(saved['chunks']),'errors':errors,'files':len(files),
          'missing':[c['id'] for c in saved['chunks'] if c['id'] not in replies]}
    return saved,source,replies,info


def preview(path,vod,values):return checked(path,vod,values)[3]


def receive(path,vod,values):
    saved,source,replies,info=checked(path,vod,values)
    if not info['accepted']:raise ValueError('저장 가능한 결과가 없습니다. 검사 오류를 확인하세요')
    if values.get('token')!=info['token']:raise Conflict('파일·입력 또는 가져오기 내역이 바뀌었습니다. 결과를 다시 검사하세요')
    if info['errors'] and values.get('allow_partial') is not True:raise ValueError('오류 묶음을 제외한 부분 저장에 먼저 동의하세요')
    return exchange.save_replies(path,saved,source,replies)
