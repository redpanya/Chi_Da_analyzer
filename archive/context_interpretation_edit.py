"""요약용 보완 제외는 별도 결과 버전으로 저장한다. 원본 실행은 수정하지 않는다."""
import copy
import uuid
from . import context_job, context_adaptive_result
from .storage import read_json, save_json, stamp


def reject(path,vod,run,item_id,part_id,change_id):
    # 등록된 실행 ID·경로·형식은 기존 읽기 경로로 확인한다.
    value=context_job.result(path,vod,run)
    if value.get('version')!=10 or not value.get('complete'):
        raise ValueError('처리가 끝난 새 방식 결과에서 보완을 제외할 수 있습니다')
    folder=context_job.local(path,f'runs/{run}')
    state=read_json(folder/'dialogue-state.json')
    owner=next((x for x in state['items'] if x['id']==item_id and not x.get('coverage_id')),None)
    part=owner.get('review_parts',{}).get(part_id) if owner else None
    change=next((c for c in part['changes'] if c['id']==change_id),None) if part else None
    if not change or change['status']!='applied' or change['original_text']==change['proposed_text']:
        raise ValueError('제외할 문맥 보완을 다시 선택하세요')
    change.update(status='rejected',reason='사용자가 이 요약에서 보완 해석을 제외했습니다')
    for group in part['groups']:
        kept=[];affected=False
        for claim in group['claims']:
            if change_id in claim['interpretations']:
                affected=True
                group['held'].append({**claim,'reason':'사용자가 보완 해석을 제외해 문장 재검토가 필요합니다'})
            else:kept.append(claim)
        group['claims']=kept
        if affected:group['title']=kept[0]['text'][:80] if kept else '문맥 해석 확인 필요'
    previous_side={x['id']:x for x in state['items'] if x.get('coverage_id')==item_id}
    state['items']=[x for x in state['items'] if x.get('coverage_id')!=item_id]
    for side in context_adaptive_result.publish(owner,read_json(folder/'source.json')):
        # 변경되지 않은 별개 대화의 독립 채팅 설명은 다시 추론하지 않는다.
        old=previous_side.get(side['id'])
        if old and (old['start_ms'],old['end_ms'])==(side['start_ms'],side['end_ms']):
            side['input']=old['input'];side['summary']['chat']=old['summary']['chat']
            side['chat_state']=old.get('chat_state','complete')
        else:
            side.update(chat_state='failed',chat_error='보완 제외로 근거 범위가 달라져 채팅 설명을 다시 확인해야 합니다')
        state['items'].append(side)
    state['items'].sort(key=lambda x:(x['start_ms'],x['end_ms'],x['id']))
    new_id=uuid.uuid4().hex;target=context_job.local(path,f'runs/{new_id}')
    saved=read_json(folder/'result.json')
    saved.update(id=new_id,created_at=stamp(),derived_from=run,
        manual_review={'action':'reject_interpretation','item':item_id,'part':part_id,'interpretation':change_id},
        evidence_reviews=sum(bool(x.get('evidence_review')) for x in state['items']),quality_state='review')
    saved['complete']=not any(x.get('chat_state')=='failed' for x in state['items'])
    # 원출력·계측은 원래 실행에서 열람한다. 추론을 새로 했다고 기록하지 않는다.
    for name in ('source.json','utterances.json','reaction-ranges.json'):
        save_json(target/name,read_json(folder/name))
    save_json(target/'dialogue-state.json',state);save_json(target/'result.json',saved)
    if not saved['complete']:save_json(target/'retry-from.json',state)
    catalog=copy.deepcopy(context_job.state(path))
    catalog.update(run=new_id,full_run=new_id,state='review',progress={},
        message='보완 해석을 제외한 별도 결과를 저장했습니다. 이전 결과와 원본은 유지됩니다.',updated_at=stamp())
    catalog.pop('timing',None)
    catalog['runs'].append({'id':new_id,'scope':'full','label':'전체 영상 · 보완 해석 제외','title':saved['created_at']})
    save_json(context_job.local(path,'state.json'),catalog)
    return new_id
