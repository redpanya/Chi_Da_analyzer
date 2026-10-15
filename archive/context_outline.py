"""구체적 이야기 추출, 입력 경계를 넘는 재확인, 두 단계 주제 구성."""
from . import context_evidence as ev
from .source import check_cancel


def candidates(job,folder,source,rows):
    groups=ev.batches(rows);found={};previous=[]
    for i,group in enumerate(groups):
        ev.progress(job,'stories',f'이야기 찾기 · {i+1}/{len(groups)}',i,len(groups))
        overlap=[]
        for row in reversed(previous):
            if ev.size([row]+overlap)>1200:break
            overlap.insert(0,row)
        evidence=overlap+group;passages=ev.passages(evidence);ids=[r['id'] for r in passages];order={id:n for n,id in enumerate(ids)}
        schema=ev.obj({'stories':ev.array(ev.obj({'start':ev.enum(ids),'title':ev.string(100),'detail':ev.string(220)}),6,1)})
        def validate(raw):
            last=-1
            if not isinstance(raw,dict) or set(raw)!={'stories'} or not isinstance(raw['stories'],list) or not 1<=len(raw['stories'])<=6:raise ValueError('이야기 후보 형식이 올바르지 않습니다')
            for item in raw['stories']:
                if set(item)!={'start','title','detail'} or item['start'] not in order or order[item['start']]<=last:raise ValueError('이야기 후보의 시작 발언이 역순이거나 없습니다')
                ev.text(item['title'],100);ev.text(item['detail'],220);last=order[item['start']]
            if raw['stories'][0]['start']!=ids[0]:raise ValueError('입력 첫 이야기의 근거가 누락됐습니다')
        instruction='''방송의 구체적인 하위 이야기를 찾는다. 영상 전체를 포괄하는 큰 제목만으로 합치지 않는다. 독립적으로 찾아볼 사건·질문·논점·경험이 하위 이야기 후보다. 다만 한 사건의 도입·설명·답변은 하나로 유지하고 한 문장마다 나누지 않는다. 첫 stories 항목은 제공된 첫 발언에서 시작한다. 그 뒤는 구체적인 이야기의 도입 발언 ID를 start로 삼는다. 직전 겹침은 같은 설명을 입력 경계에서 끊지 않기 위한 자료다. title은 실제 소재를 드러내고 detail에는 확인된 구체적 내용을 한 문장으로 적는다. 화자 인식 상태나 채팅 분위기를 대화 내용으로 쓰지 않는다. 발언에서 언급하거나 인용한 사람을 실제 방송 화자로 해석하지 않는다.'''
        instruction+=' 제공된 행은 전사를 이어 읽기 위한 묶음이지 문맥 단위가 아니다. 행마다 제목을 붙이지 않는다. 원인·과정·결과를 차례로 설명하거나 하나의 질문에 예시를 들어 답하는 내용은 이어 읽는다. 제목에 미완결 문장 조각이나 단어만 쓰지 않는다. 구체적인 설명 전체를 읽고 내용을 대표하는 제목을 만든다.'
        value={'evidence':evidence,'label':'이야기 후보'}
        raw=ev.call(job,folder,f'map-{i}',value,instruction,{'첫발언':ids[0],'새범위시작':group[0]['id'],'발언':ev.compact(passages)},schema,validate)
        # 겹침의 첫 행은 실제 이야기 시작을 뜻하지 않는다. 새 범위의 첫 후보만 임시 경계로 넣는다.
        opening=raw['stories'][0]|{'start':group[0]['id']}
        for item in [opening]+raw['stories'][1:]:
            if item['start'] in found and item['start']!=group[0]['id']:continue
            row=next(r for r in evidence if r['id']==item['start'])
            found[item['start']]={**item,'start_ms':row['start_ms']}
        previous=group
        check_cancel(job.stop)
    return sorted(found.values(),key=lambda x:x['start_ms'])


def refine(job,folder,source,rows,items):
    order={r['id']:i for i,r in enumerate(rows)};accepted=[items[0]]
    for index,item in enumerate(items[1:],1):
        ev.progress(job,'boundaries',f'경계·구조 확인 · {index}/{len(items)-1}',index-1,max(1,len(items)-1))
        at=order[item['start']];low=order[accepted[-1]['start']]+1
        high=order[items[index+1]['start']] if index+1<len(items) else len(rows)
        # 발언 수 대신 원문 분량으로 앞뒤를 읽고, 앞 입력의 도입부도 경계로 허용한다.
        left=[];right=[]
        for r in reversed(rows[max(0,low-1):at]):
            if ev.size([r]+left)>2500:break
            left.insert(0,r)
        for r in rows[at:]:
            if ev.size(right+[r])>2500:break
            right.append(r)
        evidence=left+right;passages=ev.passages(left)+ev.passages(right)
        allowed=[r['id'] for r in passages if low<=order[r['id']]<high]
        schema=ev.obj({'decision':ev.enum(['continue','new','uncertain']),'start':ev.enum(allowed),
                       'title':ev.string(100),'detail':ev.string(220),'reason':ev.string(140)})
        def validate(raw):
            if set(raw)!=set(schema['properties']) or raw['decision'] not in ('continue','new','uncertain') or raw['start'] not in allowed:raise ValueError('이야기 경계 응답을 확인할 수 없습니다')
            for k in ('title','detail','reason'):ev.text(raw[k],{'title':100,'detail':220,'reason':140}[k])
        instruction='''제공된 앞뒤 원문을 이어 읽고 검토 후보에서 별개 하위 이야기가 시작되는지 판정한다. 후보는 부정확하며 모든 후보를 채택하면 안 된다. continue: 같은 사건·질문·논점의 원인, 예시, 결과, 설명이 이어진다. new: 앞 논점에서 벗어나 독립적으로 찾아볼 별개 사건·질문·비교·경험으로 이동한다. 같은 대상에 대한 내용이어도 별개의 논점은 하위 이야기로 나눌 수 있다. 시작 ID와 끝 ID는 처리 묶음이지 문맥 경계가 아니다. 애매하면 uncertain이다. start는 허용된 ID 중 새 논점의 도입이며 후보보다 앞이어도 된다. title/detail은 실제 원문의 구체적인 논점을 설명한다. reason은 후보 앞과 뒤의 내용이 어떤 점에서 이어지거나 달라지는지 한 문장으로 쓴다. 앞서 내려진 판정은 제공되지 않으며 원문만으로 판단한다.'''
        raw=ev.call(job,folder,f'boundary-{index}',{'evidence':evidence,'label':'경계 확인'},instruction,
                    {'검토후보':item['start'],'앞뒤원문':ev.compact(passages)},schema,validate)
        if raw['decision']!='continue':
            row=rows[order[raw['start']]]
            accepted.append({'start':row['id'],'start_ms':row['start_ms'],'title':raw['title'],'detail':raw['detail'],
                             'review':raw['decision']=='uncertain','reason':raw['reason']})
    accepted=review_short(job,folder,source,rows,accepted)
    for i,item in enumerate(accepted):
        item.update(id=f'story-{i}',kind='story',end_ms=accepted[i+1]['start_ms'] if i+1<len(accepted) else source['duration_ms'])
    return accepted


def review_short(job,folder,source,rows,items):
    items=list(items)
    for start,item in [(item['start'],item) for item in items]:
        if item not in items or item['start']!=start or len(items)==1:continue
        index=items.index(item);end=items[index+1]['start_ms'] if index+1<len(items) else source['duration_ms']
        own=[r for r in rows if item['start_ms']<=r['start_ms']<end]
        # 짧은 길이는 재검토 신호일 뿐, 합치는 기준은 원문의 의미다.
        if end-item['start_ms']>=30000 and sum(len(r['text']) for r in own)>=80:continue
        left=[];right=[]
        for r in reversed([r for r in rows if r['start_ms']<item['start_ms']]):
            if ev.size([r]+left)>2000:break
            left.insert(0,r)
        for r in rows:
            if r['start_ms']<end:continue
            if ev.size(right+[r])>2000:break
            right.append(r)
        choices=['keep','uncertain']+(['previous'] if index else [])+(['next'] if index+1<len(items) else [])
        schema=ev.obj({'decision':ev.enum(choices),'reason':ev.string(180)})
        def validate(raw):
            if set(raw)!=set(schema['properties']) or raw['decision'] not in choices:raise ValueError('짧은 이야기의 경계 판정이 올바르지 않습니다')
            ev.text(raw['reason'],180)
        ev.progress(job,'boundaries','짧은 이야기의 앞뒤 원문 확인',index,len(items))
        raw=ev.call(job,folder,'short-'+item['start'],{'evidence':left+own+right,'label':'짧은 이야기 확인'},
            '가운데 원문이 독립된 이야기인지 확인한다. previous는 앞 설명의 연결 발언·후속 답변만 남은 조각이다. next는 뒤 설명의 도입부만 잘린 조각이다. keep은 짧아도 별개의 사건·질문·경험·화면 반응이다. 서로 다른 이야기를 길이만으로 합치지 않는다. 원문만으로 판단하기 어려우면 uncertain으로 남긴다. 가운데에 없는 뒤 내용을 가운데의 독립 소재로 해석하지 않는다.',
            {'앞':ev.compact(ev.passages(left)),'가운데':ev.compact(ev.passages(own)),'뒤':ev.compact(ev.passages(right))},schema,validate)
        if raw['decision']=='previous':items.pop(index)
        elif raw['decision']=='next':
            items[index+1].update(start=item['start'],start_ms=item['start_ms']);items.pop(index)
        elif raw['decision']=='uncertain':item.update(review=True,reason=raw['reason'])
    return items


def parents(job,folder,stories):
    result=[]
    for index,item in enumerate(stories):
        decision='new';title=item['title'];reason=''
        if result:
            ev.progress(job,'boundaries',f'상위 주제 연결 확인 · {index}/{len(stories)-1}',index-1,len(stories)-1)
            schema=ev.obj({'reason':ev.string(180),'decision':ev.enum(['same','new','uncertain']),'title':ev.string(100)})
            def validate(raw):
                if set(raw)!=set(schema['properties']) or raw['decision'] not in ('same','new','uncertain'):raise ValueError('상위 주제 연결 판정이 올바르지 않습니다')
                ev.text(raw['reason'],180);ev.text(raw['title'],100)
            raw=ev.call(job,folder,'parent-link-'+item['id'],{'evidence':[],'label':'상위 주제'},
                '기존 상위 주제와 다음 하위 이야기를 비교한다. 중심 대상·진행 목적이 유지되면 same이다. 같은 대상의 설명·사례·비교·질문 응답은 하위 내용 차이일 수 있다. 중심 대상이나 활동 자체가 바뀌면 new다. 공통 대상을 판단하기 어려우면 uncertain이다. reason은 공통되거나 달라진 대상·목적, title은 new일 때의 구체적인 상위 제목이다. 새 단어나 인물이 나왔다는 이유만으로 new로 판단하지 않는다.',
                {'기존상위':result[-1]['title'],'최근이야기':stories[index-1]['detail'],'다음이야기':item['detail']},schema,validate)
            decision,title,reason=raw['decision'],raw['title'],raw['reason']
        if decision=='new':
            parent={'id':f'topic-{len(result)}','kind':'topic','parent_id':None,'title':title,'start_ms':item['start_ms'],'children':[]}
            result.append(parent)
        else:parent=result[-1]
        if decision=='uncertain':
            parent['review']=True;item['parent_review']=reason
        parent['children'].append(item['id']);parent['end_ms']=item['end_ms'];item['parent_id']=parent['id']
    return result
