// 화면의 초 단위로 묶되 원시 관측 시각은 유지한다. 대표는 가장 이른 시각이다.
export function groupReactionTimes(values,start,end){
  const groups=new Map();for(const value of values){const at=typeof value==='number'?value:value.time_ms;if(!Number.isFinite(at))continue;
    const inside=at>=start&&at<end,key=Math.floor(at/1000)+':'+inside;
    if(!groups.has(key))groups.set(key,{time_ms:at,inside,raw:[],texts:[]});const group=groups.get(key);group.time_ms=Math.min(group.time_ms,at);if(!group.raw.includes(at))group.raw.push(at);if(value?.text&&!group.texts.includes(value.text))group.texts.push(value.text);
  }return [...groups.values()].sort((a,b)=>a.time_ms-b.time_ms);
}
export const reactionHelp='🤩는 이 영상 안에서의 상대적인 채팅 활동량입니다. 긍정·인기·추천 점수나 대화와의 인과관계를 뜻하지 않습니다.';

export function reactionDetails(groups){
  const rows=groups.filter(r=>r.raw.length>1);if(!rows.length)return null;
  const details=document.createElement('details'),title=document.createElement('summary');title.textContent='같은 초로 묶인 원시 반응 시각';details.append(title);
  details.addEventListener('toggle',()=>{if(!details.open||details.dataset.loaded)return;details.dataset.loaded='true';
    for(const row of rows){const p=document.createElement('p');p.textContent=(row.inside?'구간 내부':'인접 반응')+' · '+row.raw.map(ms=>(ms/1000).toFixed(3)+'초').join(', ')+' · 대표는 가장 이른 시각';details.append(p);}});return details;
}
