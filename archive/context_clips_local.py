"""Gemma 클립 작업·복구. 원문과 기존 결과는 읽기만 한다."""
import copy
import time
import uuid
from . import context_exchange_data as data, context_clip_model as policy, context_dialogue_model as model, context_server
from .context_job import local, state, FatalEngineError
from . import context_guidance as guidance
from . import context_clip_chat as chat
from .source import check_cancel, safe_error
from .storage import read_json, save_json, stamp


def prepare(path, vod, action, options):
    if set(options)-{'run','selection','thinking','include_chat','chat_offset_ms','background','custom_request'}:raise ValueError('클립 설정을 확인하세요')
    recovery=None
    if action=='clips-resume':
        id=options.get('run')
        if not any(r['id']==id and r.get('scope')=='clips-local' for r in state(path)['runs']):raise ValueError('이어갈 Gemma 클립 결과를 선택하세요')
        saved=read_json(local(path,f'runs/{id}/result.json'))
        if saved['complete']:raise ValueError('이미 완료된 클립 결과입니다')
        if saved.get('policy_revision')!=policy.REVISION or not guidance.current(saved,'clips') or data.stale(path,vod,saved):raise ValueError('입력 또는 처리 방식이 바뀌었습니다. 기존 결과를 보존하고 새로 시작하세요')
        source=read_json(local(path,f'runs/{id}/source.json'))
        work=read_json(local(path,f'runs/{id}/work.json'))
        if any(c.get('error') for c in work['chunks']):
            recovery=copy.deepcopy(work)
            for c in recovery['chunks']:c.pop('error',None)
            recovery['reviews']={k:v for k,v in recovery['reviews'].items() if 'error' not in v}
            saved=saved|{'id':uuid.uuid4().hex,'created_at':stamp(),'recovered_from':id}
    else:
        thinking=options.get('thinking',True);include=options.get('include_chat',True)
        if type(thinking) is not bool or type(include) is not bool:raise ValueError('사고·채팅 설정을 확인하세요')
        source=data.snapshot(path,vod,options.get('selection'),include_chat=include,offset=options.get('chat_offset_ms',0))
        source=chat.attach(source)
        source=guidance.attach(source,guidance.prepare(path,'clips',options))
        saved={'clip_chat_revision':chat.REVISION,'analysis_guidance':source['analysis_guidance'],'id':uuid.uuid4().hex,'revision':data.REVISION,'policy_revision':policy.REVISION,
               'scope':'clips-local','mode':'clips','origin':'local','created_at':stamp(),'complete':False,
               'model':'Gemma 4 E4B','inference':context_server.profile(thinking),'fingerprint':data.fingerprint(source),
               **{k:source[k] for k in ('input_selection','input_label','duration_ms','include_chat','chat_offset_ms')}}
    return {'saved':saved,'source':source,'inference':saved['inference'],'version':12,'recovery':recovery}


def run(job):
    started=time.monotonic();saved=job.input['saved'];source=job.input['source'];rows=source['rows']
    id=saved['id'];folder=local(job.path,f'runs/{id}')
    if not folder.exists():
        save_json(folder/'source.json',source);save_json(folder/'result.json',saved)
        save_json(folder/'work.json',job.input.get('recovery') or {
            'chunks':[{'id':f'0-{len(rows)}','first':0,'last':len(rows)}],'scans':{},'reviews':{},'replies':{}})
    work=read_json(folder/'work.json')
    entries=[r for r in job.value['runs'] if r['id']!=id]+[{'id':id,'scope':'clips-local','mode':'clips',
        'label':'Gemma 클립 후보 · '+saved['created_at'][:16],'title':saved['input_label']}]
    job.update(clip_run=id,runs=entries,message='Gemma 클립 후보 생성 준비 중')
    job.check_engine();job.tokenizer=job.make_tokenizer()
    job.clip_chat_index=chat.Index(source)
    try:
        for c in work['chunks']:c.pop('error',None)
        index=0
        while index<len(work['chunks']):
            check_cancel(job.stop)
            chunk=work['chunks'][index];key=chunk['id'];first,last=chunk['first'],chunk['last']
            try:
                if key not in work['scans']:
                    job.update(message='전사·채팅 단서에서 클립 후보를 찾는 중' if source['include_chat'] else '전사를 읽어 클립 후보를 찾는 중',progress={'stage':'clips-scan','done':first,'total':len(rows),'seconds':0})
                    owned,context,text=policy.scan_plan(rows,first,last,job.tokenizer,job.clip_chat_index)
                    if len(owned)<last-first:
                        end=first+len(owned)
                        work['chunks'][index:index+1]=[dict(id=f'{first}-{end}',first=first,last=end),dict(id=f'{end}-{last}',first=end,last=last)]
                        chunk=work['chunks'][index];key=chunk['id']
                        save_json(folder/'work.json',work)
                    packet=job.clip_chat_index.packet(owned,context)
                    raw=model.call(job,folder,'clips-scan',{'rows':context,'chat_discovery':packet},text,policy.seed_schema(context,owned,packet),
                                   lambda raw:policy.validate_seeds(raw,context,owned,packet))
                    work['scans'][key]=raw;save_json(folder/'work.json',work)
                seeds=work['scans'][key]['clips'];accepted=[];errors=[]
                for n,seed in enumerate(seeds):
                    check_cancel(job.stop);review_key=f'{key}:{n}'
                    job.update(message=f'클립 후보의 앞뒤 맥락·추천 이유 검토 중 · {n+1}/{len(seeds)}',
                               progress={'stage':'clips-review','done':first,'total':len(rows),'seconds':0})
                    if review_key not in work['reviews']:
                        try:work['reviews'][review_key]=policy.review(job,folder,source,seed)
                        except FatalEngineError:raise
                        except (ValueError,TypeError,KeyError) as error:work['reviews'][review_key]={'error':safe_error(error)}
                    checked=work['reviews'][review_key]
                    if 'error' in checked:errors.append(checked['error'])
                    else:accepted.extend(checked['clips'])
                    # 검토가 끝난 후보부터 표시한다. 중단되면 나머지 후보만 이어간다.
                    work['replies'][key]={'clips':accepted};save_json(folder/'work.json',work)
                work['replies'][key]={'clips':accepted};chunk['processed']=True
                if errors:chunk['error']=f'후보 검토 실패 {len(errors)}개 · '+errors[0]
            except FatalEngineError:raise
            except model.SplitRequired as error:
                if chunk['last']-first>1 and key not in work['scans']:
                    # 출력 초과 범위만 나눈다. 앞뒤 참고로 장면 경계를 유지한다.
                    end=(chunk['first']+chunk['last'])//2
                    work['chunks'][index:index+1]=[dict(id=f'{first}-{end}',first=first,last=end),dict(id=f'{end}-{chunk["last"]}',first=end,last=chunk['last'])]
                    save_json(folder/'work.json',work);continue
                chunk['error']=safe_error(error)
            except (ValueError,TypeError,KeyError) as error:chunk['error']=safe_error(error)
            save_json(folder/'work.json',work)
            job.update(progress={'stage':'clips-review','done':sum(c['last']-c['first'] for c in work['chunks'] if c.get('processed') or c.get('error')),'total':len(rows),'seconds':0})
            index+=1
        failures=sum(bool(c.get('error')) for c in work['chunks'])
        if data.stale(job.path,job.vod,saved):raise ValueError('처리 중 입력이 바뀌었습니다. 완료 후보는 보존합니다')
        saved.update(complete=not failures,updated_at=stamp());save_json(folder/'result.json',saved)
        return failures
    finally:
        from .context_metrics import collect
        collect(folder,job.tokenizer,started,job)
