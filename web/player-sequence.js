// 선택한 문맥의 합집합만 시간순으로 재생한다. 겹친 구간은 되감지 않는다.
export function playbackRanges(rows,duration=Infinity){
  const sorted=rows.filter(r=>Number.isFinite(r.start_ms)&&r.start_ms>=0&&Number.isFinite(r.end_ms)&&r.end_ms>r.start_ms)
    .map(r=>({start:r.start_ms,end:Math.min(r.end_ms,duration)})).filter(r=>r.end>r.start).sort((a,b)=>a.start-b.start||a.end-b.end);
  const ranges=[];
  for(const row of sorted){const last=ranges.at(-1);if(last&&row.start<=last.end)last.end=Math.max(last.end,row.end);else ranges.push({...row});}
  return ranges;
}
