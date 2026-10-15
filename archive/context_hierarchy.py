"""버전 5: 이야기 구조·반응 관계·근거 요약을 하나의 복구 가능한 작업으로 처리."""
from . import context_evidence as ev, context_outline as outline, context_events as events, context_summaries as summaries
from .context_job import local
from .source import check_cancel
from .storage import read_json, save_json, stamp

REVISION = 5


def with_reactions(complete,reaction):
    items=[{k:v for k,v in item.items() if k!='reactions'} for item in complete.values()]
    by_id={item['id']:item for item in items}
    for event in reaction:
        target=by_id.get(event['story_id'])
        if target and event['relation_status']=='linked' and (min(target['end_ms'],event['end_ms'])-max(target['start_ms'],event['start_ms']))>=.8*(target['end_ms']-target['start_ms']):
            target.setdefault('reactions',[]).append(event)
        else:items.append(event)
    return items


def process(job,saved,source):
    folder=local(job.path,f"runs/{saved['id']}");file=folder/'timeline.json'
    rows=ev.speech(source)
    if not rows:raise ValueError('사용 가능한 전사가 없습니다. 전사를 확인하세요')
    structure=folder/'outline.json'
    if structure.exists():data=read_json(structure)
    else:
        found=outline.candidates(job,folder,source,rows)
        # 같은 시각의 발언은 한 경계로 다뤄 0초 문맥을 만들지 않는다.
        found=list({item['start_ms']:item for item in found}.values())
        stories=outline.refine(job,folder,source,rows,found)
        parents=outline.parents(job,folder,stories)
        data={'stories':stories,'parents':parents};check_cancel(job.stop);save_json(structure,data)
    stories,parents=data['stories'],data['parents']
    ranges=folder/'reaction-ranges.json'
    if not ranges.exists():
        save_json(ranges,events.analysis.analyze(source['chat'],source['duration_ms'],'전체 제공 채팅' in source['notes'],saved['reaction_settings']))
    timeline=read_json(file) if file.exists() else {'done':0,'items':[],'active':None}
    total=len(stories)+len(parents);complete={r['id']:{k:v for k,v in r.items() if k!='reactions'} for r in timeline['items'] if r['kind'] in ('story','topic')}
    for item in stories+parents:
        if item['id'] in complete:continue
        ev.progress(job,'summaries',f'요약 작성·검사 · {len(complete)+1}/{total}',len(complete),total)
        if item['kind']=='story':result=summaries.story(job,folder,source,rows,item)
        else:result=summaries.parent(job,folder,item,[complete[id] for id in item['children']])
        check_cancel(job.stop);complete[item['id']]=result
        timeline.update(items=list(complete.values()),done=len(complete));save_json(file,timeline)
        ev.progress(job,'summaries',f'요약 저장 완료 · {len(complete)}/{total}',len(complete),total)
    def publish(reaction):
        check_cancel(job.stop)
        timeline.update(items=with_reactions(complete,reaction),done=total)
        save_json(file,timeline)
    event_file=folder/'events.json'
    reaction=read_json(event_file) if event_file.exists() else None
    if reaction is None or any(e['relation_status']=='failed' for e in reaction):
        reaction=events.inspect(job,folder,source,rows,stories,saved['reaction_settings'],publish=publish)
        check_cancel(job.stop);save_json(event_file,reaction)
    items=with_reactions(complete,reaction)
    validate(items,source['duration_ms'])
    from .context_full import current_source,fingerprint
    if fingerprint(current_source(job.path,job.vod,source['chat_offset_ms']))!=saved['fingerprint']:raise ValueError('처리 중 입력이 바뀌었습니다. 새 정리를 시작하세요')
    timeline.update(items=items,done=total,active=None);check_cancel(job.stop);save_json(file,timeline)
    failures=sum(e['relation_status']=='failed' for e in reaction)
    saved.update(complete=not failures,reaction_failures=failures,updated_at=stamp());save_json(folder/'result.json',saved)
    ev.progress(job,'review' if failures else 'complete','반응 일부 검토 필요' if failures else '상위·하위 문맥 정리 완료',total,total)
    return failures


def validate(items,duration):
    items=[child for item in items for child in [item]+item.get('reactions',[])]
    ids={i['id']:i for i in items}
    if len(ids)!=len(items):raise ValueError('문맥 ID가 중복됐습니다')
    for item in items:
        if not 0<=item['start_ms']<item['end_ms']<=duration:raise ValueError('문맥 범위가 영상 밖에 있습니다')
        if not 0<=item.get('play_start_ms',item['start_ms'])<item.get('play_end_ms',item['end_ms'])<=duration:raise ValueError('문맥 재생 범위가 영상 밖에 있습니다')
        parent=ids.get(item.get('parent_id'))
        if item.get('parent_id') and (not parent or parent['kind']!='topic'):raise ValueError('문맥의 상위 주제가 없습니다')
        if item['kind']=='story' and not (parent and parent['start_ms']<=item['start_ms']<item['end_ms']<=parent['end_ms']):raise ValueError('하위 이야기가 상위 범위를 벗어났습니다')
        if item['kind']=='moment' and (item.get('story_id') not in ids or ids[item['story_id']]['kind']!='story' or ids[item['story_id']]['parent_id']!=item['parent_id']):raise ValueError('반응에 연결된 이야기가 없습니다')
        refs=item['input']['evidence']
        for name,kinds in [('context',{'speech'}),('chat',{'chat'}),('relation',{'speech','chat'})]:
            for row in item['summary'][name]:ev.refs(row['evidence'],refs,kinds)
    stories=sorted((i for i in items if i['kind']=='story'),key=lambda i:i['start_ms'])
    if any(a['end_ms']>b['start_ms'] for a,b in zip(stories,stories[1:])):raise ValueError('하위 이야기 범위가 중복됐습니다')


def result(path,saved,source):
    folder=local(path,f"runs/{saved['id']}");file=folder/'timeline.json';structure=folder/'outline.json'
    timeline=read_json(file) if file.exists() else {'done':0,'items':[]}
    data=read_json(structure) if structure.exists() else {'stories':[],'parents':[]}
    # 상위가 아직 요약 중이어도 완료된 하위는 임시 상위 표제 아래에서 볼 수 있다.
    from .context_full import fingerprint,current_source
    try:stale=fingerprint(current_source(path,source, saved['chat_offset_ms']))!=saved['fingerprint']
    except (ValueError,OSError,KeyError,TypeError):stale=True
    ranges=folder/'reaction-ranges.json'
    return {k:v for k,v in saved.items() if k!='chunks'}|{'items':timeline['items'],'topics':data['parents'],
        'reaction_analysis':read_json(ranges) if ranges.exists() else None,
        'done':timeline['done'],'total':len(data['stories'])+len(data['parents']),'stale':stale,
        'stats':{'speech_total':saved['speech_total'],'speech_used':saved['speech_used'],'chat_total':saved['chat_total']},'pending_topic':None}
