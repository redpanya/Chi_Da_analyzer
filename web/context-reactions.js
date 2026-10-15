// 요약 원문은 유지하고 같은 VOD의 반응 강도를 화면에만 겹친다.
export function contextReactions(items, analysis, offset = 0, stale = false, duration = Infinity) {
  let note = '';
  if (analysis?.unreadable) note = '반응 분석을 읽지 못해 🤩 표시를 생략했습니다.';
  else if (!analysis) note = '반응 분석 결과 없음 · 통합 분석에서 채팅을 분석하세요.';
  else if (analysis.stale || stale) note = '입력이 변경된 문맥 또는 반응 분석입니다. 🤩 표시는 새 결과에서 확인하세요.';
  else if (analysis.unavailable) note = '채팅 미제공 · 반응지수를 계산할 수 없습니다.';
  const points = !note ? (analysis?.reaction_index?.points || []).filter(p=>Number.isFinite(p.at_ms)&&Number.isInteger(p.index)&&p.index>=1&&p.index<=10) : [];
  const ranges = note ? [] : (analysis.candidates || []).filter(r => ['burst', 'word', 'consonant'].includes(r.kind)
    && Number.isFinite(r.start_ms) && Number.isFinite(r.end_ms) && r.end_ms > r.start_ms);
  const decorate=item=>{
    const usable=!item.gap&&!item.failed;
    const overlapping=usable?ranges.filter(r=>r.start_ms+offset<item.end_ms&&r.end_ms+offset>item.start_ms):[];
    const inside=usable?points.filter(p=>p.at_ms+offset>=Math.max(0,item.start_ms)&&p.at_ms+offset<Math.min(duration,item.end_ms)):[];
    const score=inside.reduce((best,p)=>Math.max(best,p.index),0);
    const strongest=inside.find(p=>p.index===score);
    const peaks=[...new Set([...overlapping.filter(r=>Number.isFinite(r.peak_ms)&&r.peak_ms>=r.start_ms&&r.peak_ms<r.end_ms)
      .map(r=>r.peak_ms+offset),...(strongest?[strongest.at_ms+offset]:[])].filter(at=>at>=0&&at<duration))].sort((a,b)=>a-b);
    return {...item,reaction_count:overlapping.length,reaction_index:score,reaction_peaks:peaks,
      ...(item.reactions?{reactions:item.reactions.map(decorate)}:{})};
  };
  if(!note)note=analysis.reaction_index
    ? '🤩 반응지수 1~10'
      +(!analysis.reaction_index.comparable&&points.length?' 동일 강도 또는 비교 자료 부족으로 1을 표시합니다.':'')
    : '이전 분석에는 반응지수가 없습니다. 통합 분석에서 다시 분석하면 지수를 계산합니다. 기존 반응 시각은 유지합니다.';
  if(analysis&&(!analysis.complete_source||analysis.boundary_unverified))note+=' 일부 채팅 또는 경계 확인이 필요한 자료 기준입니다.';
  return {items:items.map(decorate),note};
}
