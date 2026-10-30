import {editedCommentRange} from './context-comment-model.js';

export function rangeError(start,end,origin,duration){
  if(!Number.isFinite(start)||!Number.isFinite(end))return '시작과 끝 시각을 입력하세요.';
  if(end<=start)return '끝 시각은 시작 시각보다 뒤여야 합니다.';
  if(start<origin||end>origin+duration)return '저장된 영상 범위 안의 시각을 입력하세요.';
  return '';
}
export function editRange(start,end,origin,duration){
  const a=editedCommentRange(start,'').start_ms,b=editedCommentRange(end,'').start_ms,error=rangeError(a,b,origin,duration);
  if(error)throw Error(error);
  return {start_ms:a,end_ms:b};
}
export function collectRanges(result,run,origin,duration){
  let invalid=0;
  const rows=(result.items||[]).flatMap((item,i)=>{
    // 기존 분석 결과는 재생본 상대 시각이다. 편집 입력은 VOD 시각으로 표시한다.
    const start=(item.play_start_ms??item.start_ms)+origin,end=(item.play_end_ms??item.end_ms)+origin;
    if(rangeError(start,end,origin,duration)){invalid++;return [];}
    const title=String(item.title||item.summary?.title||'제목 없는 구간').slice(0,200);
    const context=item.summary?.context;
    const description=typeof item.summary==='string'?item.summary:Array.isArray(context)?context.map(part=>typeof part==='string'?part:part?.text||'').join(' '):typeof context==='string'?context:'';
    return [{id:JSON.stringify([run,i]),run,title,start_ms:start,end_ms:end,original_start:start,original_end:end,description:String(description),failed:!!item.failed}];
  });
  return {rows,invalid};
}
export function sortedRanges(values){return [...values].sort((a,b)=>a.start_ms-b.start_ms||a.end_ms-b.end_ms||a.id.localeCompare(b.id));}
export function totalLength(values){return [...values].reduce((sum,row)=>sum+row.end_ms-row.start_ms,0);}

export function captionPreviewTarget(caption,clips,active,origin,duration){
  if(!Number.isFinite(caption.start_ms)||!Number.isFinite(caption.end_ms)||caption.end_ms<=caption.start_ms)return null;
  const matches=sortedRanges(clips).filter(c=>Math.max(c.start_ms,caption.start_ms,origin)<Math.min(c.end_ms,caption.end_ms,origin+duration));
  const clip=matches.find(c=>c.id===active?.id)||matches[0];
  return clip?{clip,seconds:(Math.max(clip.start_ms,caption.start_ms,origin)-origin)/1000}:null;
}
