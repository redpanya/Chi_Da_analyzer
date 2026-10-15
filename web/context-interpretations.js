import {timecode} from './player.js';
const node=(tag,text)=>{const el=document.createElement(tag);el.textContent=text;return el;};

export function interpretationDetails(item,player,onReject){
  const box=node('details','');
  const changes=(item.interpretations||[]).filter(x=>x.original_text!==x.proposed_text),omissions=item.omissions||[],held=item.held_claims||[];
  const applied=changes.filter(x=>x.status==='applied').length;
  box.append(node('summary',`문맥 보완 ${applied}개 · 생략 검토 ${omissions.length}개 · 보류 문장 ${held.length}개`));
  box.append(node('p','원본 전사·수동 교정·화자 배정은 유지합니다. 아래 내용은 이 요약 실행의 해석이며 정확성을 보증하지 않습니다.'));
  const refs=new Map(item.input.evidence.map(r=>[r.id,r]));
  function source(ids){
    const row=node('div','');row.className='play-actions';
    for(const id of new Set(ids||[])){
      const r=refs.get(id);if(!r)continue;
      const button=node('button',`${timecode(r.start_ms)} · 원음 확인`);button.className='subtle';button.title=r.text;
      button.onclick=()=>player.seek(r.start_ms,true,r.end_ms);row.append(button);
    }
    return row;
  }
  for(const change of changes){
    box.append(node('h4',change.status==='applied'?'요약용 문맥 보완':change.status==='rejected'?'사용자가 제외한 보완':'보완 후보 · 확인 필요'),
      node('p','원문: '+change.original_text),node('p','해석: '+change.proposed_text),node('p',change.reason),source(change.evidence));
    if(change.status==='applied'&&onReject&&change.part_id){
      const button=node('button','이 보완 제외 · 새 결과로 저장');button.className='subtle';
      button.onclick=async()=>{button.disabled=true;try{await onReject(change);}finally{button.disabled=false;}};box.append(button);
    }
  }
  for(const row of omissions){
    const label=row.status==='referenced'?'요약 근거로 유지':row.role==='unclear'?'관련성 판단 어려움':'이 문맥 본문에서 생략';
    box.append(node('h4',label),node('p',refs.get(row.source_id)?.text||row.source_id),node('p',row.reason),source([row.source_id]));
  }
  for(const claim of held)box.append(node('h4','미확정 문장'),node('p',claim.text),node('p',claim.reason),source(claim.evidence));
  for(const issue of item.review_issues||[])box.append(node('p',issue));
  return box;
}
