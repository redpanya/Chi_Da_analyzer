import {vodLabel} from './vod-label.js';
const names={complete:'완료',idle:'준비 전',error:'확인 필요',paused:'중단',review:'검토 필요',empty:'제공 없음',unavailable:'미제공'};
export function savedDescription(project){
 const state=task=>names[task?.state]||task?.state||'준비 전';
 return `VOD ${project.vod_id} · 영상 ${state(project.tasks.video)} · 채팅 ${state(project.tasks.chat)} · 전사 ${project.speech?.run?'결과 있음':'준비 전'} · 요약 ${state(project.context)}`;
}
export function createSavedPicker({api,getRoot,getSelected,onSelect}){
 const $=id=>document.getElementById(id),dialog=$('queue-saved-dialog');let generation=0,chosen=new Map(),opener=null;
 const close=()=>{generation++;dialog.close();opener?.focus();};
 function count(){$('queue-saved-status').textContent=`${chosen.size}개 선택 · 선택 순서대로 등록할 자료에 추가합니다`;$('queue-saved-confirm').disabled=!chosen.size;}
 $('queue-saved-close').onclick=close;
 dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
 $('queue-saved-confirm').onclick=()=>{for(const project of chosen.values())onSelect(project);close();};
 return {close,async open(){
   const ticket=++generation,root=getRoot();chosen=new Map();opener=document.activeElement;
   $('queue-saved-list').replaceChildren();$('queue-saved-status').textContent='저장한 VOD 확인 중…';$('queue-saved-confirm').disabled=true;dialog.showModal();
   try{
     const projects=await api('projects',{root});if(ticket!==generation||root!==getRoot())return;
     if(!projects.length){$('queue-saved-status').textContent='이 보관함에 저장한 VOD가 없습니다';return;}
     count();const selected=new Set(getSelected());
     for(const project of projects){
       const label=document.createElement('label');label.className='saved-vod-choice';const check=document.createElement('input');check.type='checkbox';check.disabled=selected.has(project.vod_id);check.checked=check.disabled;
       const text=document.createElement('span'),title=document.createElement('strong'),detail=document.createElement('small');title.textContent=vodLabel(project);detail.textContent=savedDescription(project)+(check.disabled?' · 등록할 자료에 선택됨':'');text.append(title,detail);
       check.onchange=()=>{if(check.checked)chosen.set(project.vod_id,project);else chosen.delete(project.vod_id);count();};label.append(check,text);$('queue-saved-list').append(label);
     }
   }catch(error){if(ticket===generation)$('queue-saved-status').textContent=error.message;}
 }};
}
