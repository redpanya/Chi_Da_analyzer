// 실패 항목의 참고 보기만 구성한다. 원 결과의 상태·본문·복사 가능 여부는 변경하지 않는다.
export function fallbackEvidence(item){
  const rows=(item.input?.evidence||[]).filter(r=>r.kind==='speech'&&typeof r.text==='string'&&r.text.trim());
  const candidates=rows.length<=3?rows:[rows[0],rows[Math.floor(rows.length/2)],rows.at(-1)];
  const seen=new Set();
  return candidates.filter(r=>{const key=r.id??`${r.start_ms}:${r.text}`;if(seen.has(key))return false;seen.add(key);return true;});
}
export function fallbackChats(item){
  return (item.input?.evidence||[]).filter(r=>r.kind==='chat'&&typeof r.text==='string'&&r.text.trim()).sort((a,b)=>(b.count||1)-(a.count||1)).slice(0,3);
}
