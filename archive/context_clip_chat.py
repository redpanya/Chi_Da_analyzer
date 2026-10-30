"""클립 전용 채팅 탐색 단서. 원문·공통 반응지수와 기존 입력 계약은 바꾸지 않는다."""
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from .analysis import features, normalise

REVISION = 1
WINDOW_MS = 10000
BEFORE_MS = 15000
AFTER_MS = 30000
RULES = '''채팅도 후보 발견에 사용한다. 전사를 전부 읽는 탐색과 채팅에서 출발하는 탐색을 함께 수행한다.
chat_discovery.cues의 모든 단서와 대표 채팅을 확인하고 해당 발언 주변에서 놓친 유머·반응·질문·정정·노래·게임·합방의 포인트를 찾는다. 채팅이 적은 장면도 계속 찾는다.
급증·반복은 관측 통계이며 인기, 긍정 감정, 대화와의 인과관계나 동일인 수를 뜻하지 않는다. 소수의 반복·인사·후원·별개 사건일 수 있다. 질문·정정·부정 반응도 읽고 장면과의 관계를 판단한다.
전사가 있는 구간만 후보로 만든다. 단서의 anchor_id는 시간상 가까운 검토 출발점일 뿐 관련성이 입증된 발언이 아니다. 관련 발언을 찾지 못하면 억지로 후보를 만들지 않는다.
채팅 시각은 이미 보정된 원본 시각이다. 지연 시간을 임의로 빼거나 채팅 시각을 장면의 핵심 시각으로 대체하지 않는다.
chat_reference는 인접 파일·지연 반응 검토용이다. 채팅 근거는 제공된 chat/chat_sample/chat_reference 중 후보 시작 15초 전부터 끝 30초 후까지 허용한다. 이 범위는 반응 탐색 여유이며 영상 재생 범위를 늘리는 규칙이 아니다.
discovery는 발견 출발점(speech=대화, chat=채팅, both=대화+채팅)이다. chat/both에는 실제 chat_evidence_ids가 필요하다. 사후에 채팅이 겹쳤다는 이유만으로 발견 출발점을 both로 바꾸지 않는다.
chat_relation은 supported(내용상 관련 단서 있음), uncertain(관련성 불확실), unrelated(별개 반응), not_used(채팅 미사용)다. supported도 인과관계 확정이 아니다. uncertain이면 review_needed=true다.
supported는 전사와 채팅 본문에 공통 사건·대상·질문과 답변을 연결할 구체적인 내용이 있을 때만 선택한다. 시간상 근접, 반복 횟수, 일반 인사·감탄이나 뜻을 모르는 이모티콘 코드만으로는 연결할 수 없다. 그런 채팅은 관측 사실만 설명하고 uncertain 또는 unrelated로 남긴다. 발언보다 앞서 기록된 채팅을 그 발언 직후의 반응이라고 서술하지 않는다.
chat_summary는 시청자 반응으로 구분하고, 대화 요약에 채팅 주장을 사실로 넣지 않는다. 관련 없는 채팅을 후보 추천 이유로 사용하지 않는다.
표본은 전체 채팅 의미 분석이 아니다. 닉네임·사용자 식별자는 제공하지 않으며 참여 인원은 추정하지 않는다.'''


def sample(rows, limit=12):
    """시간대·빈도 높은 표현·소수 표현을 섞되 동일 문구 반복이 표본을 독점하지 않는다."""
    if len(rows) <= limit:
        return list(rows)
    groups = defaultdict(list)
    for row in rows:
        groups[normalise(row['text']).strip()].append(row)
    groups = list(groups.values())
    spread = [rows[round(i*(len(rows)-1)/max(1,limit-1))] for i in range(limit)]
    rare = [g[len(g)//2] for g in sorted(groups,key=lambda g:(len(g),g[0]['start_ms']))]
    frequent = [g[len(g)//2] for g in sorted(groups,key=lambda g:(-len(g),g[0]['start_ms']))]
    chosen = {}; texts = set()
    for candidates in zip(spread, rare, frequent):
        for row in candidates:
            text = normalise(row['text']).strip()
            if text not in texts:
                chosen[row['id']] = row; texts.add(text)
            if len(chosen) == limit:break
        if len(chosen) == limit:break
    return sorted(chosen.values(),key=lambda r:(r['start_ms'],r['id']))


def attach(source):
    """새 클립 작업만 호출한다. 과거 파일은 당시 fingerprint와 시각 규칙을 유지한다."""
    if not source.get('include_chat'):
        return source | {'clip_chat':{'revision':REVISION,'cues':[],'unanchored':[],'sample_policy':'채팅 미사용'}}
    rows=source['rows']; starts=[r['start_ms'] for r in rows]
    longest=[];best=0
    for i,r in enumerate(rows):
        if r['end_ms']>rows[best]['end_ms']:best=i
        longest.append(best)
    bins=defaultdict(list)
    for row in source['chat']:bins[row['start_ms']//WINDOW_MS].append(row)
    cues=[];missing=[]
    for number,group in sorted(bins.items()):
        counts=Counter(term for r in group for term in features(r['text'])[0])
        repeats=[{'kind':kind,'term':term,'messages':count} for (kind,term),count in counts.most_common()
                 if count>=3 and count/len(group)>=.3][:6]
        baseline=sum(len(bins.get(n,())) for n in range(max(0,number-6),number))/max(1,min(number,6))
        ratio=len(group)/max(1,baseline)
        burst=number>=3 and len(group)>=5 and ratio>=3
        if not burst and not repeats:continue
        # 실제 채팅 시각을 사용한다. 밀집한 초의 첫 채팅이며 가상 시각을 만들지 않는다.
        seconds=Counter(r['start_ms']//1000 for r in group)
        second=min(seconds,key=lambda n:(-seconds[n],n))
        at=next(r['start_ms'] for r in group if r['start_ms']//1000==second)
        pos=bisect_right(starts,at)-1
        candidates=[]
        if pos>=0:
            prior=longest[pos]
            if rows[prior]['end_ms']>=at-AFTER_MS:candidates.append(prior)
        following=bisect_left(starts,at)
        if following<len(rows) and starts[following]<=at+BEFORE_MS:candidates.append(following)
        cue={'id':f'R{number}','start_ms':number*WINDOW_MS,'end_ms':(number+1)*WINDOW_MS,
             'reaction_ms':at,'messages':len(group),'unique_texts':len({normalise(r['text']).strip() for r in group}),
             'baseline_messages':round(baseline,2),'burst_ratio':round(ratio,2) if burst else None,
             'repeats':repeats,'sample_ids':[r['id'] for r in sample(group,6)]}
        if not candidates:
            missing.append({'id':cue['id'],'reaction_ms':at,'messages':len(group)})
            continue
        anchor=min(candidates,key=lambda i:(max(rows[i]['start_ms']-at,at-rows[i]['end_ms'],0),abs(starts[i]-at)))
        cues.append(cue|{'anchor_id':rows[anchor]['id']})
    return source | {'clip_chat':{'revision':REVISION,'cues':cues,'unanchored':missing,
        'sample_policy':'대표 표본·10초 집계 / 전체 채팅 의미 검토 아님 / 참여 인원 집계 없음'}}


class Index:
    """한 작업에서 시간 색인을 재사용한다. 후보마다 전체 채팅을 다시 훑지 않는다."""
    def __init__(self, source):
        self.chats=source['chat']; self.times=[r['start_ms'] for r in self.chats]
        self.by_id={r['id']:r for r in self.chats}; self.by_anchor=defaultdict(list)
        for cue in source.get('clip_chat',{}).get('cues',[]):self.by_anchor[cue['anchor_id']].append(cue)

    def between(self,start,end):
        return self.chats[bisect_left(self.times,max(0,start)):bisect_left(self.times,end)]

    def packet(self,owned,context=None):
        context=context or owned
        start=min(r['start_ms'] for r in context)-BEFORE_MS
        end=max(r['end_ms'] for r in context)+AFTER_MS
        observed=self.between(start,end)
        cues=[c for r in owned for c in self.by_anchor[r['id']]]
        selected={r['id']:r for r in sample(observed,12)}
        for cue in cues:
            selected.update((id,self.by_id[id]) for id in cue['sample_ids'] if id in self.by_id and start<=self.by_id[id]['start_ms']<end)
        return {'cues':cues,'sampled':True,'chat_total':len(observed),
                'reference_start_ms':max(0,start),'reference_end_ms':end,
                'chat_sample':sorted(selected.values(),key=lambda r:(r['start_ms'],r['id']))}


def presentation(clip, source, cues_by_bin=None):
    if cues_by_bin is None:
        cues_by_bin={c['start_ms']//WINDOW_MS:c for c in source.get('clip_chat',{}).get('cues',[])}
    reactions=[];signals={}
    for row in clip['chat_evidence']:
        cue=cues_by_bin.get(row['start_ms']//WINDOW_MS)
        if cue:signals[cue['id']]=cue
        reactions.append({'chat_id':row['id'],'time_ms':row['start_ms'],'text':row['text']})
    return {'discovery_info':{'source':clip.get('discovery','unrecorded'),
        'relation':clip.get('chat_relation','unrecorded'),'signals':list(signals.values())},
        'chat_reactions':reactions}
