// 의미상 부모와 화면의 시간순 배치를 분리한다. 별도 반응은 부모 ID를 만들지 않는다.
export const relationLabel={linked:'대화 연결',other:'대화 외 반응',mixed:'여러 반응 혼합',unknown:'원인 확인 필요',failed:'반응 분석 실패 · 검토 필요'};
export function contextClipRange(item){
  const title=Array.from(item.summary.title.replace(/[\s\x00-\x1f]+/g,' ').trim());
  return {start_ms:item.play_start_ms??item.start_ms,end_ms:item.play_end_ms??item.end_ms,name:title.length>80?title.slice(0,79).join('')+'…':title.join('')};
}
export function contextGroups(value){
  const items=value.items||[],parents=value.topics||items.filter(x=>x.kind==='topic'),used=new Set();
  const groups=parents.map(topic=>{
    const children=items.filter(x=>x.parent_id===topic.id||(x.kind==='reaction'&&x.start_ms>=topic.start_ms&&x.start_ms<topic.end_ms));
    children.forEach(x=>used.add(x.id));
    return {topic:items.find(x=>x.id===topic.id)||topic,children:children.sort((a,b)=>a.start_ms-b.start_ms||a.end_ms-b.end_ms)};
  });
  for(const item of items)if(item.kind!=='topic'&&!used.has(item.id))groups.push({topic:null,children:[item]});
  return groups.sort((a,b)=>(a.topic?.start_ms??a.children[0].start_ms)-(b.topic?.start_ms??b.children[0].start_ms));
}
export function phaseProgress(progress,complete,revision=5,version=0){
  if(complete)return 100;
  if(version===9||version===10){
    const ratio=progress.total?progress.done/progress.total:0;
    if(progress.stage==='dialogue')return Math.min(59,60*ratio);
    if(progress.stage==='grounding')return Math.min(84,60+25*ratio);
    if(progress.stage==='dialogue-chat')return Math.min(99,85+15*ratio);
  }
  if(progress.stage==='dialogue')return Math.min(79,80*(progress.total?progress.done/progress.total:0));
  if(progress.stage==='dialogue-chat')return Math.min(99,80+20*(progress.total?progress.done/progress.total:0));
  if(progress.stage==='review')return 99;
  const phase=(revision<5?['stories','boundaries','reactions','summaries']:['stories','boundaries','summaries','reactions']).indexOf(progress.stage);
  return phase<0?null:Math.min(99,phase*25+25*(progress.total?progress.done/progress.total:0));
}

export const contextSummaryFailed=item=>!item.gap&&(!!item.failed||(item.grounding_state==='review'&&!item.summary?.context?.length));

// 화면 필터만 계산한다. 댓글 선택에는 필터 전의 전체 자료를 계속 전달한다.
export function contextReactionRows(items, minimum=0){
  const rows=items.flatMap((item,index)=>[{item,index},...(item.reactions||[]).map(child=>({item:child,index}))]);
  return minimum===0?rows:rows.filter(({item})=>Number.isInteger(item.reaction_index)&&item.reaction_index>=minimum&&item.reaction_index<=10)
    .sort((a,b)=>a.item.start_ms-b.item.start_ms||a.item.end_ms-b.item.end_ms);
}
