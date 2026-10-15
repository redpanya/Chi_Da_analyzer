import {timecode} from './player.js';

const key=item=>item.id||JSON.stringify([item.start_ms,item.end_ms,item.summary.title]);
export const canCopyContext=item=>!item.provisional&&!item.time_review&&!item.gap&&!item.failed&&item.relation_status!=='failed'&&item.grounding_state!=='pending'&&item.grounding_state!=='review'&&item.copy_ready!==false;
export function createContextCopy({api}={}){
  const $=id=>document.getElementById(id),text=$('context-comment-text'),notice=$('context-copy-notice'),status=$('context-draft-state');
  const drafts=new Map();let current=null,items=[],vodOffset=0;
  function payload(d){return {revision:d.revision,text:d.text,selected:[...d.selected],edited:d.edited,basis:d.basis};}
  async function save(d){
    clearTimeout(d.timer);
    if(!api||!d.identity||d.loading||d.loadError||d.saving||!d.changed)return;
    const serial=d.serial;d.saving=true;d.error='';renderStatus();
    try{
      const value=await api('context-comment-save',{...d.identity,draft:payload(d)});
      d.revision=value.revision;d.changed=d.serial!==serial;
    }catch(error){d.error='미저장 · '+error.message;}
    finally{d.saving=false;renderStatus();if(d.changed&&!d.error)save(d);}
  }
  function changed(d){d.changed=true;d.serial++;clearTimeout(d.timer);d.timer=setTimeout(()=>save(d),350);}
  if(api)globalThis.addEventListener?.('beforeunload',event=>{
    const pending=[...drafts.values()].filter(d=>d.changed||d.saving);
    if(!pending.length)return;
    pending.forEach(save);event.preventDefault();event.returnValue='';
  });
  function pruneSelection(){
    if(!current||current.loading||current.loadError)return;
    const valid=new Set(items.map(key)),selected=new Set([...current.selected].filter(id=>valid.has(id)));
    if(selected.size!==current.selected.size){current.selected=selected;changed(current);}
  }
  function generated(){return items.filter(item=>current.selected.has(key(item))).sort((a,b)=>a.start_ms-b.start_ms||(b.kind==='topic')-(a.kind==='topic')||a.end_ms-b.end_ms)
    .map(item=>`${timecode(item.start_ms+vodOffset)} ${item.summary.title.replace(/\s+/g,' ').trim()}`).join('\n');}
  function renderStatus(){
    if(!current){status.textContent='';return;}
    status.textContent=current.loading?'저장한 댓글 초안 확인 중…':current.loadError||current.error||(current.saving||current.changed?'저장 중…':api?'이 컴퓨터에 저장됨':'화면 초안')
      +(current.edited?' · 직접 편집한 초안':'')+(current.edited&&current.basis!==generated()?' · 선택 목록이 변경됨. 편집을 유지하거나 선택 목록으로 다시 만드세요.':'');
  }
  function render(){
    if(!current){text.value='';text.disabled=true;$('context-copy').disabled=$('context-copy-select').disabled=$('context-copy-reset').disabled=true;renderStatus();return;}
    const value=generated();
    if(!current.loading&&!current.edited&&current.text!==value){current.text=value;current.basis=value;changed(current);}
    if(text.value!==current.text)text.value=current.text;
    text.disabled=current.loading;
    const rows=items.filter(item=>current.selected.has(key(item)));
    const duplicate=new Set(rows.map(x=>timecode(x.start_ms))).size<rows.length;
    $('context-copy-count').textContent=`선택한 문맥 ${rows.length}개 · 시간순${duplicate?' · 같은 시작 시각이 있습니다. 미리보기를 확인하세요.':''}`;
    $('context-copy').disabled=$('context-copy-select').disabled=!current.text||current.loading;
    $('context-copy-reset').disabled=current.loading||!current.edited;
    renderStatus();
  }
  text.oninput=()=>{if(!current||current.loading)return;current.text=text.value;current.edited=true;changed(current);render();};
  text.onblur=()=>{if(current)save(current);};
  $('context-copy-reset').onclick=()=>{
    if(!current||current.loading)return;
    if(current.edited&&!globalThis.confirm('직접 편집한 댓글을 선택한 문맥의 시각·제목으로 다시 만듭니다. 계속할까요?'))return;
    current.edited=false;current.text=generated();current.basis=current.text;changed(current);notice.textContent='선택 목록으로 다시 만들었습니다.';render();
  };
  const select=()=>{text.focus();text.select();};
  $('context-copy-select').onclick=select;
  $('context-copy').onclick=async()=>{
    const value=text.value,source=current;if(!value)return;
    if(source)save(source);
    try{await navigator.clipboard.writeText(value);if(source===current&&value===text.value)notice.textContent='복사했습니다. 치지직 다시보기 댓글에 붙여넣으세요.';}
    catch{if(source===current&&value===text.value){select();notice.textContent='자동 복사를 사용할 수 없습니다. 선택된 내용을 ⌘C로 복사하세요.';}}
  };
  return {
    async setItems(values,scope,offset=0,identity=null){
      if(current?.scope!==scope){
        if(current)save(current);
        notice.textContent='';current=null;
        if(scope){
          if(!drafts.has(scope)){
            const d={scope,identity,revision:0,text:'',selected:new Set(),edited:false,basis:'',serial:0,changed:false,loading:!!api};drafts.set(scope,d);
            if(api)d.ready=api('context-comment',identity).then(value=>{Object.assign(d,value,{selected:new Set(value.selected),loading:false});})
              .catch(error=>{d.loading=false;d.loadError='기존'+' 초안 조회 실패 · 편집 내용은 자동 저장하지 않습니다: '+error.message;});
          }
          current=drafts.get(scope);
        }
      }
      items=values.filter(canCopyContext);vodOffset=offset;
      pruneSelection();
      render();const d=current;
      if(d?.ready){await d.ready;if(d!==current)return;d.ready=null;pruneSelection();render();}
    },
    checkbox(item){
      const label=document.createElement('label'),input=document.createElement('input');label.className='inline-check context-check';input.type='checkbox';input.checked=current?.selected.has(key(item))||false;input.disabled=!!current?.loading;
      input.setAttribute('aria-label',`댓글에 포함: ${item.summary.title}`);
      input.onchange=()=>{if(!current||current.loading)return;if(input.checked)current.selected.add(key(item));else current.selected.delete(key(item));changed(current);notice.textContent='';render();};
      label.append(input,'댓글에 포함');return label;
    }
  };
}
