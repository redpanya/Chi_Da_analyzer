"""전체 제공 채팅에서 반응을 찾고 대화 관련성과 관측 사실을 분리한다."""
from collections import Counter
from . import analysis, analysis_store, context_evidence as ev
from .storage import load_project
from .source import check_cancel


def settings(path,vod):
    try:
        old=analysis_store.load(path,load_project(path,vod))
        if old and not old.get('stale'):return analysis.settings(old['settings'])
    except (OSError,ValueError,KeyError):pass
    return analysis.settings({})


def candidates(source,options):
    result=analysis.analyze(source['chat'],source['duration_ms'],'전체 제공 채팅' in source['notes'],options)
    bins={}
    for row in source['chat']:
        index=row['offset_ms']//10000
        b=bins.setdefault(index,{'rows':[],'terms':Counter()});b['rows'].append(row);b['terms'].update(analysis.features(row.get('text'))[0])
    peaks={}
    for c in result['candidates']:
        values=[]
        for index in range(c['start_ms']//10000,c['end_ms']//10000+1):
            b=bins.get(index,{'rows':[],'terms':{}})
            count=len(b['rows']) if c['kind']=='burst' else b['terms'].get((c['kind'],c['term']),0)
            values.append((index,count))
        for n,(index,count) in enumerate(values):
            before=values[n-1][1] if n else 0;after=values[n+1][1] if n+1<len(values) else 0
            if count>=options['min_repeats'] and count>before and count>=after:
                peaks.setdefault(index,{'score':0,'signals':set()});peaks[index]['score']=max(peaks[index]['score'],count);peaks[index]['signals'].add((c['kind'],c['term']))
    chosen=[]
    for index,p in sorted(peaks.items()):
        if chosen and index-chosen[-1]['bin']<=2:
            prev=chosen[-1];signals=prev['signals']|p['signals']
            if p['score']>prev['score']:prev.update(bin=index,score=p['score'])
            prev['signals']=signals
        else:chosen.append({'bin':index,**p})
    if len(chosen)>500:raise ValueError('반응 장면이 500개를 넘습니다. 반응 분석 기준을 높인 뒤 새 정리를 시작하세요')
    events=[]
    for n,p in enumerate(chosen):
        rows=bins[p['bin']]['rows'];offset=source['chat_offset_ms']
        peak=max(0,min(source['duration_ms']-1,p['bin']*10000+offset))
        authors={r.get('user_id_hash') for r in rows if r.get('user_id_hash')}
        events.append({'id':f'reaction-{n}','peak_ms':peak,'messages':len(rows),'known_authors':len(authors),
                       'unknown_authors':sum(not r.get('user_id_hash') for r in rows),'signals':sorted(p['signals'])})
    return events


def unsupported_link(raw):
    return raw['status']=='linked' and (raw['speech_id']=='none' or not any(kind=='word' and term not in {'아','와','오','어','헉','하하','하하하','네','응'} for kind,term in analysis.features(raw['chat_excerpt'])[0]))


def inspect(job,folder,source,rows,stories,options,publish=None):
    pending=candidates(source,options);events=[]
    for n,c in enumerate(pending):
        check_cancel(job.stop)
        ev.progress(job,'reactions',f'반응 관계 확인 · {n+1}/{len(pending)}',n,len(pending))
        start=max(0,c['peak_ms']-35000);end=min(source['duration_ms'],c['peak_ms']+25000)
        value=ev.window(source,rows,start,end,3000)
        while ev.size(value['evidence'])>8000 and end-start>10000:
            start=(start+c['peak_ms'])//2;end=(end+c['peak_ms']+1)//2;value=ev.window(source,rows,start,end,2500)
        evidence=value['evidence'];speech=[r for r in evidence if r['kind']=='speech'];chat=[r for r in evidence if r['kind']=='chat']
        if not chat:continue
        previous=[e for e in events if e['relation_status']!='failed' and abs(e['peak_ms']-c['peak_ms'])<=60000]
        schema=ev.obj({'observation':ev.string(350),
            'speech_id':ev.enum(['none']+[r['id'] for r in speech]),
            'chat_id':ev.enum(r['id'] for r in chat),
            'status':ev.enum(['linked','other','mixed','unknown']),'reason':ev.string(300),
            'title':ev.string(100),'same_as':ev.enum(['none']+[e['id'] for e in previous])})
        refs={r['id']:r for r in evidence}
        def validate(raw):
            if not isinstance(raw,dict) or set(raw)!=set(schema['properties']) or raw['status'] not in ('linked','other','mixed','unknown'):raise ValueError('반응 관계 형식이 올바르지 않습니다')
            ev.text(raw['title'],100);ev.text(raw['observation'],350);ev.text(raw['reason'],300)
            if raw['same_as'] not in ['none']+[e['id'] for e in previous]:raise ValueError('반응이 없는 사건에 연결됐습니다')
            ev.refs([raw['chat_id']],chat,{'chat'})
            if raw['speech_id']!='none':
                ev.refs([raw['speech_id']],speech,{'speech'})
                if raw['status']=='linked' and not any(s['start_ms']<=refs[raw['speech_id']]['start_ms']<s['end_ms'] for s in stories):raise ValueError('발언에 대응하는 하위 이야기가 없습니다')
            if raw['same_as']!='none' and not unsupported_link(raw|{'chat_excerpt':refs[raw['chat_id']]['text']}):
                prior=next(e for e in previous if e['id']==raw['same_as'])
                linked_story=next((s['id'] for s in stories if raw['speech_id']!='none' and s['start_ms']<=refs[raw['speech_id']]['start_ms']<s['end_ms']),None)
                if prior['relation_status']!=raw['status'] or (raw['status']=='linked' and prior['story_id']!=linked_story):raise ValueError('서로 다른 관계의 반응을 같은 사건으로 합칠 수 없습니다')
        instruction='''시청자 반응을 분석한다. observation은 채팅에서 관측한 사실이다. 판단에 사용한 발언 speech_id와 채팅 chat_id만 고른다. 원문 인용은 프로그램이 선택 ID로 가져오므로 다시 쓰지 않는다. 연결되는 발언이 없으면 speech_id=none이다. 내용을 직접 대응시킬 수 있으면 linked, 별도 인사·후원 등 다른 요인의 근거가 있으면 other, 여러 요인이 섞이면 mixed, 원인을 모르겠으면 unknown이다. reason은 그 판정의 구체적 근거다. 원문에 없는 감정·의도를 붙이지 않는다. title은 구체적인 반응 제목이다. 앞 사건과 같은 원문 사건을 반복 설명할 때만 same_as에 그 ID를 쓰고, 같은 종류의 웃음일 뿐이면 none이다.'''
        data={'반응':c,
             '앞사건':[{'id':e['id'],'title':e['summary']['title'],'status':e['relation_status'],'story':e['story_id'] or 'none','evidence':e['summary']['chat']} for e in previous],
             '방송발언':ev.records(speech),'시청자채팅':ev.records(chat),
             '채팅유형':{r['id']:r['message_type'] for r in chat if r.get('message_type')}}
        # 앞 반응의 실패가 복구되면 뒤 반응의 입력도 달라진다. 이전 성공 응답을 덮어쓰지 않는다.
        key=f'event-v2-{n}-{ev.digest(data)[:16]}'
        try:raw=ev.call(job,folder,key,value,instruction,data,schema,validate)
        except ev.ModelResponseError as error:
            check_cancel(job.stop)
            events.append({**c,'kind':'reaction','parent_id':None,'story_id':None,'start_ms':start,'end_ms':end,
                'relation_status':'failed','signal_ids':[c['id']],'input':value,'range_sources':False,
                'summary':{'title':'반응 분석 실패 · 검토 필요','context':[],'chat':[], 'relation':[],
                           'uncertainties':['AI 응답 검사에 두 번 실패했습니다. 이어하기로 재검토할 수 있습니다.',str(error)]}})
            if publish:publish(events)
            continue
        raw=raw|{'chat_excerpt':refs[raw['chat_id']]['text'],
                 'speech_excerpt':refs[raw['speech_id']]['text'] if raw['speech_id']!='none' else ''}
        # 형식은 유효해도 연결 근거가 부족하면 보류하고 다음 반응을 처리한다.
        if unsupported_link(raw):
            raw={**raw,'status':'unknown','same_as':'none','title':'채팅 반응 · 원인 확인 필요','observation':'채팅 원문: '+raw['chat_excerpt']}
        linked=raw['status']=='linked';anchor=refs.get(raw['speech_id']) if linked else None
        story=next((s for s in stories if anchor and s['start_ms']<=anchor['start_ms']<s['end_ms']),None)
        if linked and not story:raise ValueError('발언에 대응하는 하위 이야기가 없습니다')
        evidence_ids=[raw['chat_id']]+([raw['speech_id']] if anchor else [])
        begin=min([c['peak_ms']]+[refs[id]['start_ms'] for id in evidence_ids])
        finish=min(source['duration_ms'],max([c['peak_ms']+1000]+[refs[id]['end_ms']+1000 for id in evidence_ids]))
        parent=story['parent_id'] if linked else None
        uncertainties=[] if linked else [{'unknown':'원인 확인 필요','other':'대화 외 반응','mixed':'여러 반응 혼합'}[raw['status']]]
        summary={'title':raw['title'],'context':[{'text':'발언 원문: '+raw['speech_excerpt'],'evidence':[raw['speech_id']]}] if linked else [],
                 'chat':[{'text':raw['observation'],'evidence':[raw['chat_id']]}],
                 'relation':[{'text':raw['reason'],'evidence':evidence_ids}] if linked else [],'uncertainties':uncertainties}
        event={**c,'kind':'moment' if linked else 'reaction','parent_id':parent,'story_id':story['id'] if linked else None,
                       'start_ms':begin,'end_ms':finish,'play_start_ms':begin,'play_end_ms':finish,
                       'relation_status':raw['status'],'signal_ids':[c['id']],'summary':summary,'input':value,'range_sources':False}
        if raw['same_as']=='none':events.append(event)
        else:merge(next(e for e in previous if e['id']==raw['same_as']),event,source,rows)
        if publish:publish(events)
    return events


def merge(prior,event,source,rows):
    """같은 사건으로 판정된 새 반응도 구간과 근거를 버리지 않는다."""
    prior['signal_ids'].extend(event['signal_ids'])
    prior['start_ms']=prior['play_start_ms']=min(prior['start_ms'],event['start_ms'])
    prior['end_ms']=prior['play_end_ms']=max(prior['end_ms'],event['end_ms'])
    for name in ('context','chat','relation'):
        for claim in event['summary'][name]:
            if claim not in prior['summary'][name]:prior['summary'][name].append(claim)
    start=min(prior['input']['range']['start_ms'],event['input']['range']['start_ms'])
    end=max(prior['input']['range']['end_ms'],event['input']['range']['end_ms'])
    value=ev.window(source,rows,start,end,0)
    refs={r['id']:r for part in (prior,event) for r in part['input']['evidence']}
    value['evidence']=sorted(refs.values(),key=lambda r:r['start_ms'])
    texts={r['text'] for r in refs.values() if r['kind']=='chat'}
    value['stats']['speech_used']=sum(r['kind']=='speech' for r in refs.values())
    value['stats']['chat_used']=sum(start<=max(0,r['offset_ms']+source['chat_offset_ms'])<end and (r.get('text') or '').strip() in texts for r in source['chat'])
    prior['input']=value
