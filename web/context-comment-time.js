import {commentTimeText,editedCommentRange} from './context-comment-model.js';
const $=id=>document.getElementById(id);

// 결과 원문 대신 선택한 댓글 행의 시각만 편집한다.
export function createCommentTimeEditor(){
  const dialog=$('comment-time-editor'),start=$('comment-time-start'),end=$('comment-time-end'),reaction=$('comment-time-reaction'),error=$('comment-time-error');
  let editing=null;
  const close=()=>{const trigger=editing?.trigger;editing=null;if(dialog.open)dialog.close();trigger?.focus();};
  $('comment-time-cancel').onclick=close;
  dialog.onclose=()=>{if(!dialog.open){const trigger=editing?.trigger;editing=null;trigger?.focus();}};
  reaction.onchange=()=>{if(editing&&reaction.value!==''){start.value=commentTimeText(Number(reaction.value)+editing.offset);error.textContent='시작 시각을 선택한 채팅 반응 시각으로 바꿨습니다. 적용을 눌러 저장하세요.';}};
  $('comment-time-original').onclick=()=>{
    if(!editing?.item)return;
    start.value=commentTimeText(editing.item.start_ms+editing.offset);
    end.value=Number.isFinite(editing.item.end_ms)?commentTimeText(editing.item.end_ms+editing.offset):'';
    reaction.value='';error.textContent='원래 문맥 시각입니다. 적용을 누르면 댓글 목록에 반영합니다.';
  };
  $('comment-time-form').onsubmit=event=>{
    event.preventDefault();if(!editing)return;
    try{editing.apply(editedCommentRange(start.value,end.value,editing.offset,editing.duration));close();}
    catch(e){error.textContent=e.message;}
  };
  return {close,open({row,item,offset,duration,apply,trigger}){
    editing={item,offset,duration,apply,trigger};error.textContent='';
    $('comment-time-title').textContent=row.title;
    start.value=Number.isFinite(row.start_ms)?commentTimeText(row.start_ms+offset):'';
    end.value=Number.isFinite(row.end_ms)?commentTimeText(row.end_ms+offset):'';
    const option=(text,value)=>{const node=document.createElement('option');node.textContent=text;node.value=value;return node;};
    const peaks=[...new Set((item?.reaction_peaks||[]).filter(at=>Number.isFinite(at)&&at>=0&&(!Number.isFinite(duration)||at<duration)))].sort((a,b)=>a-b);
    reaction.replaceChildren(option('채팅 반응 시각 선택',''),...peaks.map(at=>option(commentTimeText(at+offset)+(at<item.start_ms||at>=item.end_ms?' (인접 반응)':''),String(at))));reaction.value='';
    $('comment-time-reactions').hidden=!peaks.length;
    $('comment-time-original').disabled=!Number.isFinite(item?.start_ms);
    $('comment-time-range').textContent=`저장 영상 범위 ${commentTimeText(offset)} ~ ${Number.isFinite(duration)&&duration>0?commentTimeText(duration+offset):'끝 시각 미확인'}`;
    dialog.showModal();start.focus();
  }};
}
