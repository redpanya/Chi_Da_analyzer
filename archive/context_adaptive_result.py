"""문장·보완·생략을 각각 검사한다. 유효한 ID는 의미 정확성 보증이 아니다."""
import copy
import hashlib
from collections import Counter
from difflib import SequenceMatcher
from . import context_dialogue_input as di


def text(value,limit=500):return isinstance(value,str) and 0<len(value.strip())<=limit


def ids(value,allowed):
    return (isinstance(value,list) and 0<len(value)<=12 and all(isinstance(x,str) and x in allowed for x in value)
            and len(value)==len(set(value)))


def checked(raw,rows):
    allowed={r['id']:r for r in rows}; changes=[]; omissions=[]; groups=[]; issues=[]
    if not isinstance(raw,dict):return {'changes':[],'omissions':[],'groups':[],'issues':['검토 응답 누락']}
    candidates=raw.get('interpretations',[]) if isinstance(raw.get('interpretations'),list) else []
    counts=Counter(c['id'] for c in candidates if isinstance(c,dict) and isinstance(c.get('id'),str))
    seen=set(); usable={}
    for c in candidates:
        if not isinstance(c,dict):issues.append('보완 후보 형식 오류');continue
        key=c.get('id');source=c.get('source_id'); ref=c.get('evidence');r=allowed.get(source) if isinstance(source,str) else None
        valid=(text(key,30) and counts[key]==1 and key not in seen and r is not None and text(c.get('proposed_text'),1200)
               and text(c.get('reason'),240) and ids(ref,allowed) and source in ref and c.get('risk') in ('surface','meaning'))
        if not valid:issues.append('보완 후보의 원문·근거·형식 확인 필요');continue
        seen.add(key)
        status='applied';reason=c['reason']
        if c['proposed_text']==r['text']:pass  # 원문 재출력은 수동 교정을 바꾼 것이 아니다.
        elif r['corrected']:status='review';reason='수동 교정은 자동 변경하지 않습니다'
        elif c['risk']=='meaning' and (c.get('basis')!='explicit_restatement' or not any(x!=source for x in ref)):
            status='review';reason='의미 변경을 명시적으로 뒷받침하는 재언급·정정 확인 필요 · '+reason
        elif not any(x!=source for x in ref) and ''.join(c['proposed_text'].split())!=''.join(r['text'].split()):
            status='review';reason='보완을 뒷받침하는 다른 발언이 없습니다'
        edits=[{'start':a,'end':b,'original':r['text'][a:b],'proposed':c['proposed_text'][x:y]}
               for op,a,b,x,y in SequenceMatcher(None,r['text'],c['proposed_text'],autojunk=False).get_opcodes() if op!='equal']
        value={**c,'original_text':r['text'],'source_sha256':hashlib.sha256(r['text'].encode()).hexdigest(),
               'edits':edits,'status':status,'reason':reason}
        changes.append(value);usable[key]=status=='applied'
    for o in raw.get('omissions',[]) if isinstance(raw.get('omissions'),list) else []:
        if not isinstance(o,dict) or not isinstance(o.get('source_id'),str) or o['source_id'] not in allowed or o.get('role') not in ('aside','reaction','unclear') or not text(o.get('reason'),240):
            issues.append('생략 근거 형식 오류');continue
        if any(x['source_id']==o['source_id'] for x in omissions):continue
        omissions.append(dict(o))
    seen_threads=set()
    for group in raw.get('threads',[]) if isinstance(raw.get('threads'),list) else []:
        if not isinstance(group,dict) or group.get('id') not in ('main','parallel_1','parallel_2') or group['id'] in seen_threads:
            issues.append('대화 묶음 형식·중복 오류');continue
        seen_threads.add(group['id']);claims=[];held=[]
        for c in group.get('claims',[]) if isinstance(group.get('claims'),list) else []:
            if not isinstance(c,dict) or not text(c.get('text'),500) or not ids(c.get('evidence'),allowed):
                held.append({'text':c.get('text','') if isinstance(c,dict) else '', 'reason':'문장 근거 범위·형식 확인 필요'});continue
            refs=c.get('interpretations')
            valid_refs=(isinstance(refs,list) and all(isinstance(x,str) and usable.get(x) for x in refs)
                        and all(set(change['evidence']).issubset(c['evidence']) for change in changes if change['id'] in refs))
            reason='보완 후보 확인 필요' if not valid_refs else '의미 해석 확인 필요'
            uncertain=any(o['source_id'] in c['evidence'] and o['role']=='unclear' for o in omissions)
            if c.get('decision')!='supported' or not valid_refs or uncertain:
                held.append({'text':c['text'],'evidence':c['evidence'],'reason':reason});continue
            claims.append({'text':c['text'],'evidence':c['evidence'],'interpretations':refs})
        refs={x for c in claims for x in c['evidence']}
        title=group.get('title')
        if not text(title,80) or not ids(group.get('title_evidence'),refs):
            title=(claims[0]['text'][:77]+'…' if len(claims[0]['text'])>80 else claims[0]['text']) if claims else '문맥 해석 확인 필요'
        if held and claims:
            # 제외된 주장에만 의존한 제목을 남기지 않는다. 의미 독립성은 모델·사람 검토가 필요하다.
            title=claims[0]['text'][:77]+'…' if len(claims[0]['text'])>80 else claims[0]['text']
        groups.append({'id':group['id'],'title':title,'claims':claims,'held':held})
    # 생략과 요약 근거가 충돌하면 원문을 숨기지 않는다.
    used={x for g in groups for c in g['claims'] for x in c['evidence']}
    for o in omissions:o['status']='referenced' if o['source_id'] in used else 'review' if o['role']=='unclear' else 'omitted'
    return {'changes':changes,'omissions':omissions,'groups':groups,'issues':issues}


def publish(item,source):
    """긴 문맥의 부분 검토와 동시 대화를 원문 소유와 별개로 표시한다."""
    item.setdefault('draft_summary',copy.deepcopy(item['summary']))
    changes=[];omissions=[];main=[];held=[];issues=[];side=[];title=None
    rows={r['id']:r for r in item['input']['evidence'] if r['kind']=='speech'}
    for key,part in item.get('review_parts',{}).items():
        changes.extend({**c,'part_id':key,'owner_id':item['id']} for c in part['changes']);omissions.extend(part['omissions']);issues.extend(part['issues'])
        for group in part['groups']:
            if group['id']=='main':
                main.extend(group['claims']);held.extend(group['held']);title=title or group['title']
            elif group['claims']:
                selected=[r for r in rows.values() if any(r['id'] in c['evidence'] for c in group['claims'])]
                entry=di.card(source,selected,group['title'],'동시 대화')
                entry.update(id=item['id']+'-'+key+'-'+group['id'],coverage_id=item['id'],adaptive=True,parallel=True,
                             grounding_state='complete',copy_ready=True,range_sources=False,
                             interpretations=[{**c,'part_id':key,'owner_id':item['id']} for c in part['changes'] if c['source_id'] in {r['id'] for r in selected}],omissions=[],held_claims=group['held'],
                             evidence_review=bool(group['held']))
                entry['summary']['context']=group['claims'];side.append(entry)
            else:
                held.extend(group['held'])
    item['summary'].update(title=title or '문맥 해석 확인 필요',context=main,relation=[],
        uncertainties=['일부 문장·문맥 해석은 원음 확인이 필요합니다.'] if held or issues else [])
    review=bool(held or issues or any(c['status']!='applied' for c in changes) or any(o['role']=='unclear' for o in omissions))
    item.update(interpretations=changes,omissions=omissions,held_claims=held,review_issues=issues,
                grounding_state='complete' if main else 'review',copy_ready=bool(main),range_sources=False,
                evidence_review=review or not main)
    return side
