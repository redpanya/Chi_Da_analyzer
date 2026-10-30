import {groupReactionTimes,reactionHelp,reactionDetails} from './reaction-times.js';
import {timecode} from './player.js';
const node=(tag,text,cls='')=>{const el=document.createElement(tag);el.textContent=text;el.className=cls;return el;};

// 발견 경로와 채팅의 실제 관측 시각은 장면의 핵심 시각과 구분한다.
export function clipEvidence(card,item,seek){
  const info=item.discovery_info||{},names={speech:'대화',chat:'채팅',both:'대화 + 채팅'};
  card.append(node('p',names[info.source]?`발견 근거 · ${names[info.source]}`:'발견 근거 · 이전 결과에 기록 없음','hint'));
  const relations={supported:'내용상 관련 단서 있음 · 원인 확정 아님',uncertain:'대화와의 관련성 확인 필요',unrelated:'별개 반응',not_used:'채팅 근거 미사용'};
  if(relations[info.relation])card.append(node('p',`채팅 연결 (AI 판단) · ${relations[info.relation]}`,'hint'));
  const signals=info.signals||[];
  if(signals.length){
    const detail=node('details','');detail.append(node('summary','채팅 탐색 단서'));
    for(const signal of signals){
      const labels=[];
      if(signal.burst_ratio)labels.push(`주변 대비 ${signal.burst_ratio}배`);
      for(const repeat of signal.repeats||[])labels.push(`${repeat.term} ${repeat.messages}건`);
      detail.append(node('p',`${timecode(signal.reaction_ms)} · 10초 동안 ${signal.messages}건 · 서로 다른 문구 ${signal.unique_texts}개 · ${labels.join(' / ')}`));
    }
    detail.append(node('p','반응량은 긍정·인기 점수가 아닙니다. 같은 사람의 반복일 수 있으며 참여 인원은 집계하지 않습니다.','hint'));card.append(detail);
  }
  const reactions=item.chat_reactions||[];
  if(!reactions.length)return;
  card.append(node('h4','채팅 반응 시각'));
  const actions=node('div','','play-actions clip-chat-reactions');
  const groups=groupReactionTimes(reactions,item.start_ms,item.end_ms);
  for(const row of groups){
    const nearby=row.time_ms<item.start_ms||row.time_ms>=item.end_ms;
    const button=node('button',`${timecode(row.time_ms)}${nearby?' · 인접 반응':''}`,'subtle');button.type='button';
    button.title=row.texts.join(' / ')+' · 원시 시각 '+row.raw.map(ms=>(ms/1000).toFixed(3)+'초').join(', ')+' · '+reactionHelp;button.onclick=()=>seek(row.time_ms);actions.append(button);
  }
  const raw=reactionDetails(groups);if(raw)card.append(raw);
  card.append(actions,node('p','반응이 기록된 시각입니다. 장면의 핵심 시각과 다를 수 있습니다.','hint'));
}

export function skippedChatEvidence(box,result){
  const rows=result.chat_discovery?.unanchored||[];if(!rows.length)return;
  const details=node('details','');details.append(node('summary',`주변 전사가 없어 보류한 채팅 반응 ${rows.length}구간`));
  // 긴 방송도 펼치기 전에는 수천 개의 행을 만들지 않는다.
  details.addEventListener('toggle',()=>{
    if(!details.open||details.dataset.loaded)return;details.dataset.loaded='true';
    for(const row of rows)details.append(node('p',`${timecode(row.reaction_ms)} · 채팅 ${row.messages}건`));
  });box.append(details);
}
