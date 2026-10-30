import {timecode} from './player.js';
import {contextSummaryFailed} from './context-tree.js';

export const contextCommentTitle=item=>contextSummaryFailed(item)?'요약 실패':item.gap?'사용 가능한 전사 없음':item.summary?.title||item.title||'제목 없음';
export const contextKey=item=>item.id||JSON.stringify([item.start_ms,item.end_ms,item.summary?.title??contextCommentTitle(item)]);
export const hasUsableContextSummary=item=>!item.provisional&&!item.time_review&&!item.gap&&!item.failed&&item.relation_status!=='failed'&&item.grounding_state!=='pending'&&item.grounding_state!=='review'&&item.copy_ready!==false;
export const canCopyContext=item=>hasUsableContextSummary(item)||(
  (contextSummaryFailed(item)||!!item.gap)&&!item.provisional&&!item.time_review
  &&Number.isFinite(item.start_ms)&&item.start_ms>=0&&Number.isFinite(item.end_ms)&&item.end_ms>item.start_ms);
export const validRange=row=>Number.isFinite(row.start_ms)&&row.start_ms>=0&&Number.isFinite(row.end_ms)&&row.end_ms>row.start_ms;
export const orderedRows=rows=>[...rows].sort((a,b)=>(a.start_ms??Infinity)-(b.start_ms??Infinity)||(a.end_ms??Infinity)-(b.end_ms??Infinity)||a.id.localeCompare(b.id));
export const commentText=(rows,offset=0)=>orderedRows(rows).map(row=>`${Number.isFinite(row.start_ms)?timecode(row.start_ms+offset)+' ':''}${row.title.replace(/\s+/g,' ').trim()}`).join('\n');
export function commentTimeText(ms){
  if(!Number.isFinite(ms))return '';
  const rounded=Math.round(ms),fraction=rounded%1000;
  return timecode(rounded)+(fraction?'.'+String(fraction).padStart(3,'0'):'');
}
export function editedCommentRange(startText,endText,offset=0,duration=null){
  const parse=text=>{
    const match=text.trim().match(/^(\d{1,3}):([0-5]\d):([0-5]\d)(?:\.(\d{1,3}))?$/);
    if(!match)throw Error('시각은 HH:MM:SS 형식으로 입력하세요. 분·초는 00~59입니다.');
    const ms=(+match[1]*3600 + +match[2]*60 + +match[3])*1000+Number((match[4]||'').padEnd(3,'0'))-offset;
    if(!Number.isFinite(ms)||ms<0)throw Error('저장한 영상의 시작 이전 시각은 사용할 수 없습니다.');
    return ms;
  };
  const start_ms=parse(startText),end_ms=endText.trim()?parse(endText):null;
  if(end_ms!==null&&end_ms<=start_ms)throw Error('재생 끝 시각을 시작보다 뒤로 바꾸세요. 끝을 비우면 댓글 복사만 가능합니다.');
  if(Number.isFinite(duration)&&duration>0&&(start_ms>=Math.round(duration)||(end_ms!==null&&end_ms>Math.round(duration))))throw Error('저장한 영상의 길이를 벗어난 시각입니다.');
  return {start_ms,end_ms};
}
export function commentRow(item){
  const source_id=contextKey(item),start=Number.isFinite(item.start_ms)&&item.start_ms>=0?item.start_ms:null;
  return {id:source_id,source_id,start_ms:start,end_ms:start!==null&&Number.isFinite(item.end_ms)&&item.end_ms>start?item.end_ms:null,title:contextCommentTitle(item).replace(/\s+/g,' ').trim()};
}
// 이전 메모는 원문을 별도로 보존한다. 모르는 끝 시각을 추측해 재생하지 않는다.
export function restoreComment(value,items,offset=0){
  if(value.format===2)return {rows:value.rows.map(row=>({...row})),legacy_text:value.legacy_text};
  const selected=new Set(value.selected||[]),sources=items.filter(canCopyContext),rows=[];
  if(!value.edited){
    for(const item of sources)if(selected.has(contextKey(item)))rows.push(commentRow(item));
    if(rows.length||!value.text)return {rows,legacy_text:value.text||''};
  }
  const used=new Set();
  for(const [index,line] of (value.text||'').split(/\r\n|\r|\n/).entries()){
    if(!line.trim())continue;
    const match=line.match(/^\s*(\d{1,3}):([0-5]\d):([0-5]\d)(?:\s+(.*))?$/);
    const start=match?((+match[1]*3600 + +match[2]*60 + +match[3])*1000-offset):null;
    const candidates=start!==null?sources.filter(item=>!used.has(contextKey(item))&&selected.has(contextKey(item))&&Math.floor((item.start_ms+offset)/1000)===Math.floor((start+offset)/1000)):[];
    const exact=candidates.filter(item=>contextCommentTitle(item).replace(/\s+/g,' ').trim()===(match?.[4]||''));
    const source=exact.length===1?exact[0]:candidates.length===1?candidates[0]:null;
    if(source){const row=commentRow(source);row.title=match[4]||'';rows.push(row);used.add(row.id);}
    else rows.push({id:`legacy:${index}`,source_id:null,start_ms:start!==null&&start>=0?start:null,end_ms:null,title:match&&start>=0?match[4]||'':line});
  }
  return {rows,legacy_text:value.text||''};
}
