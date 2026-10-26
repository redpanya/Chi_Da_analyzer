import {timecode} from './player.js';
import {canCopyContext,contextCommentTitle,contextKey,commentRow,commentText,orderedRows,restoreComment,validRange} from './context-comment-model.js';
export {canCopyContext,contextCommentTitle,hasUsableContextSummary} from './context-comment-model.js';

export function createContextCopy({api,player}={}){
  const $=id=>document.getElementById(id),list=$('context-comment-list'),notice=$('context-copy-notice'),status=$('context-draft-state');
  const drafts=new Map(),nodes=new Map();let current=null,items=[],vodOffset=0,renderedOrder='';
  const blocked=()=>!current||current.loading||!!current.loadError;
  const text=()=>current?commentText(current.rows,vodOffset):'';
  function payload(d){return {revision:d.revision,format:2,rows:d.rows.map(row=>({...row})),legacy_text:d.legacy_text};}
  async function save(d){
    clearTimeout(d.timer);
    if(!api||!d.identity||d.loading||d.loadError||d.saving||!d.changed)return;
    const serial=d.serial;d.saving=true;d.error='';renderStatus();
    try{const value=await api('context-comment-save',{...d.identity,draft:payload(d)});d.revision=value.revision;d.changed=d.serial!==serial;}
    catch(error){d.error='미저장 · '+error.message;}
    finally{d.saving=false;renderStatus();if(d.changed&&!d.error)save(d);}
  }
  function changed(d){d.changed=true;d.serial++;clearTimeout(d.timer);d.timer=setTimeout(()=>save(d),350);}
  if(api)globalThis.addEventListener?.('beforeunload',event=>{
    const pending=[...drafts.values()].filter(d=>d.changed||d.saving);
    if(!pending.length)return;
    pending.forEach(save);event.preventDefault();event.returnValue='';
  });
  function renderStatus(){status.textContent=!current?'':current.loading?'저장한 댓글 목록 확인 중…':current.loadError||current.error||(current.saving||current.changed&&api?'저장 중…':api?'이 컴퓨터에 저장됨':'화면 목록');}
  function syncChecks(){
    if(!current)return;
    for(const input of document.querySelectorAll('.context-check input')){
      if(input.commentScope!==current?.scope)continue;
      input.checked=current.rows.some(row=>row.source_id===input.commentSource);input.disabled=blocked();
    }
  }
  function playbackStatus(){
    const state=player?.sequenceState?.()||{active:false},button=$('context-list-play');
    button.textContent=state.active?(state.paused?'목록 재생 계속':'목록 재생 일시정지'):'목록 구간 이어 재생';
    button.disabled=blocked()||!player||!current.rows.some(validRange);
    $('context-list-playing').textContent=state.active?`선택 구간 ${state.index+1}/${state.total}${state.paused?' · 일시정지':' · 빈 시간 건너뛰기'}`:'';
  }
  player?.onSequence?.(playbackStatus);
  function remove(id){
    if(blocked())return;player?.stopSequence?.();current.rows=current.rows.filter(row=>row.id!==id);
    changed(current);notice.textContent='댓글 목록에서 항목을 제거했습니다.';render();
  }
  function rowNode(row){
    const d=current,li=document.createElement('li'),clock=document.createElement('button'),title=document.createElement('input'),del=document.createElement('button');
    li.className='context-comment-row';clock.className='subtle comment-time';title.type='text';title.maxLength=50000;title.className='comment-title';del.className='subtle comment-remove';del.textContent='×';
    title.oninput=()=>{if(d!==current||blocked())return;const value=current.rows.find(r=>r.id===row.id);if(!value)return;value.title=title.value;changed(d);$('context-copy-fallback').hidden=true;renderStatus();};
    title.onblur=()=>save(d);
    clock.onclick=()=>{if(d!==current||blocked())return;const value=current.rows.find(r=>r.id===row.id);if(value&&validRange(value))player?.seek(value.start_ms,true,value.end_ms);};
    del.onclick=()=>{if(d===current)remove(row.id);};
    li.append(clock,title,del);return {li,clock,title,del};
  }
  function render(){
    const rows=current?orderedRows(current.rows):[],ids=new Set(rows.map(r=>r.id));
    for(const [id,node] of nodes)if(!ids.has(id)){node.li.remove();nodes.delete(id);}
    for(const row of rows){
      if(!nodes.has(row.id))nodes.set(row.id,rowNode(row));const {clock,title,del}=nodes.get(row.id);
      const at=Number.isFinite(row.start_ms)?timecode(row.start_ms+vodOffset):'시각 없음';
      clock.textContent=at;clock.disabled=blocked()||!player||!validRange(row);
      clock.title=validRange(row)?`${at} 구간 재생`:'끝 시각을 확인할 수 없어 이어 재생에서 제외합니다.';
      title.setAttribute('aria-label',`${at} 댓글 제목`);title.disabled=blocked();if(title.value!==row.title)title.value=row.title;
      del.setAttribute('aria-label',`${at} 항목 제거`);del.disabled=blocked();
    }
    const order=JSON.stringify(rows.map(r=>r.id));
    if(order!==renderedOrder){for(const row of rows)list.append(nodes.get(row.id).li);renderedOrder=order;}
    $('context-comment-empty').hidden=!!rows.length;
    const excluded=rows.filter(row=>!validRange(row)).length;
    $('context-copy-count').textContent=`목록 ${rows.length}개 · 시간순${excluded?' · 재생 범위 미확인 '+excluded+'개':''}`;
    $('context-copy').disabled=blocked()||!rows.length;$('context-copy-reset').disabled=blocked()||!rows.length;
    $('context-comment-legacy').hidden=!current?.legacy_text;$('context-comment-legacy-text').textContent=current?.legacy_text||'';
    syncChecks();renderStatus();playbackStatus();
  }
  $('context-copy-reset').onclick=()=>{
    if(blocked()||!current.rows.length)return;
    if(!globalThis.confirm('댓글 목록과 편집한 제목을 초기화합니다. 요약 원본과 보관된 이전 메모는 유지합니다. 계속할까요?'))return;
    player?.stopSequence?.();current.rows=[];changed(current);notice.textContent='댓글 목록을 초기화했습니다.';$('context-copy-fallback').hidden=true;render();
  };
  $('context-list-play').onclick=()=>{
    if(blocked()||!player)return;
    if(player.sequenceState().active)player.toggleSequence();else if(player.playSequence(orderedRows(current.rows)))notice.textContent='목록의 시작·끝 시각으로 재생합니다. 겹치는 구간은 한 번만 재생합니다.';
    playbackStatus();
  };
  $('context-copy').onclick=async()=>{
    if(blocked())return;const value=text(),source=current;if(!value)return;save(source);
    try{await navigator.clipboard.writeText(value);if(source===current&&value===text()){notice.textContent='복사했습니다. 치지직 다시보기 댓글에 붙여넣으세요.';$('context-copy-fallback').hidden=true;}}
    catch{if(source===current&&value===text()){const fallback=$('context-copy-fallback');fallback.hidden=false;fallback.value=value;fallback.focus();fallback.select();notice.textContent='자동 복사를 사용할 수 없습니다. 선택된 내용을 ⌘C 또는 Ctrl+C로 복사하세요.';}}
  };
  return {
    async setItems(values,scope,offset=0,identity=null){
      if(current?.scope!==scope){
        if(current)save(current);player?.stopSequence?.();notice.textContent='';current=null;nodes.clear();list.replaceChildren();renderedOrder='';$('context-copy-fallback').hidden=true;
        if(scope){
          if(!drafts.has(scope)){
            const d={scope,identity,revision:0,rows:[],legacy_text:'',serial:0,changed:false,loading:!!api};drafts.set(scope,d);
            if(api)d.ready=api('context-comment',identity).then(value=>{d.raw=value;d.loading=false;})
              .catch(error=>{d.loading=false;d.loadError='기존 목록 조회 실패 · 새로고침 후 다시 확인하세요: '+error.message;});
          }
          current=drafts.get(scope);
        }
      }
      items=values.filter(canCopyContext);vodOffset=offset;render();const d=current;
      if(d?.ready){await d.ready;if(d!==current)return;d.ready=null;if(d.raw){Object.assign(d,restoreComment(d.raw,items,vodOffset),{revision:d.raw.revision});delete d.raw;}render();}
    },
    checkbox(item){
      const draft=current,id=contextKey(item),label=document.createElement('label'),input=document.createElement('input');
      label.className='inline-check context-check';input.type='checkbox';input.checked=current?.rows.some(row=>row.source_id===id)||false;input.disabled=blocked();input.commentScope=current?.scope;input.commentSource=id;
      input.setAttribute('aria-label',`댓글에 포함: ${contextCommentTitle(item)}`);
      input.onchange=()=>{
        if(current!==draft||blocked())return;const selected=items.find(row=>contextKey(row)===id);
        if(input.checked&&!selected)return;
        const existing=current.rows.find(row=>row.source_id===id);
        if(input.checked&&!existing){player?.stopSequence?.();current.rows.push(commentRow(selected));notice.textContent='시간순 위치에 추가했습니다.';}
        else if(!input.checked&&existing){remove(existing.id);return;}else return;
        changed(current);$('context-copy-fallback').hidden=true;render();
      };
      label.append(input,'댓글에 포함');return label;
    }
  };
}
