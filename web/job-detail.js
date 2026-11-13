import {elapsedText} from './task-timing.js';
import {animateUI,cancelMotion} from './workspace-motion.js';
import {bindOutsideDismiss} from './panel-dismiss.js';

const states={idle:'준비 전',queued:'대기',starting:'준비 중',running:'진행 중',downloading:'다운로드 중',verifying:'검사 중',exporting:'정리 중',stopping:'중단 중',paused:'중단됨',error:'확인 필요',review:'확인 필요',partial:'일부 완료',complete:'완료',empty:'제공 없음',unavailable:'미제공',cancelled:'취소됨'};
export const jobDetailKey=request=>JSON.stringify([request.kind,request.root||'',String(request.vod_id||''),request.id||'',request.run||'']);
const clock=value=>{const date=new Date(value);return value&&Number.isFinite(date.getTime())?date.toLocaleString('ko-KR'): '시각 기록 없음';};

export function createJobDetail({api,onResult,onChanged=()=>{},onSelection=()=>{},root=document}){
 const make=(tag,text='',cls='')=>{const el=root.createElement(tag);el.textContent=text;el.className=cls;return el;};
 const dialog=make('dialog','','result-drawer job-detail'),header=make('header','','result-drawer-header');
 const heading=make('h2','작업 상세'),close=make('button','×','result-drawer-close');
 dialog.id='job-detail';heading.id='job-detail-title';heading.tabIndex=-1;dialog.setAttribute('aria-labelledby',heading.id);
 close.type='button';close.setAttribute('aria-label','작업 상세 닫기');header.append(heading,close);
 const body=make('div','','result-drawer-body'),title=make('h3','','job-detail-title'),status=make('p','','job-detail-state');
 const message=make('p'),progress=make('progress'),counts=make('p','','hint'),timing=make('p','','hint'),fields=make('dl','','job-detail-fields');
 progress.max=1;progress.setAttribute('aria-label','작업 진행률');
 const resumeNote=make('p','','hint job-detail-resume-note'),recordsTitle=make('h3','최근 기록'),records=make('ol','','job-detail-records'),recordNote=make('p','','hint');
 const feedback=make('p','','job-detail-feedback'),error=make('p','','job-detail-error');
 for(const el of [feedback,error]){el.setAttribute('role','status');el.hidden=true;}
 const footer=make('footer','','job-detail-actions');body.append(title,status,message,progress,counts,timing,fields,resumeNote,recordsTitle,records,recordNote,feedback,error);dialog.append(header,body,footer);root.body.append(dialog);
 let current=null,generation=0,loading=null,timer=null,snapshot=null,signature='',actionsKey='',pending=false,opener=null,getOpener=null;
 const write=(el,text)=>{el.textContent=text||'';el.hidden=!text;};
 function dismiss(focus=true){
  if(!current)return;const target=getOpener?.()||opener;current=null;snapshot=null;generation++;loading=null;clearInterval(timer);timer=null;
  cancelMotion(dialog);dialog.inert=false;if(dialog.open)dialog.close();delete root.body.dataset.jobDetail;onSelection(null);
  if(focus&&target?.isConnected!==false)target?.focus({preventScroll:true});
 }
 function closeAnimated(focus=true){if(!current||dialog.inert)return;dialog.inert=true;animateUI(dialog,[{opacity:1,transform:'translateX(0)'},{opacity:0,transform:'translateX(20px)'}],{duration:180},()=>dismiss(focus));}
 bindOutsideDismiss(dialog,()=>closeAnimated(false),{root});
 close.onclick=closeAnimated;dialog.addEventListener('cancel',event=>{event.preventDefault();closeAnimated();});
 dialog.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();closeAnimated();}});
 dialog.addEventListener('close',()=>{if(!dialog.open)dismiss();});
 const button=(text,fn)=>{const b=make('button',text);b.type='button';b.onclick=fn;return b;};
 async function act(fn){
  if(pending)return;const token=generation;pending=true;for(const b of footer.children)b.disabled=true;write(error,'');write(feedback,'');
  try{const response=await fn();if(token===generation){write(feedback,response?.message||(response?.queued?'앞 작업 뒤에 이어서 처리하도록 대기열에 등록했습니다.':''));onChanged();await refresh();}}
  catch(e){if(token===generation){if(e.queued){write(feedback,'앞 작업 뒤에 이어서 처리하도록 대기열에 등록했습니다.');onChanged();await refresh();}else write(error,e.message);}}
  finally{if(token===generation){pending=false;for(const b of footer.children)b.disabled=false;}}
 }
 function paint(value){
  snapshot=value;write(title,value.title);write(status,`${value.label||'작업'} / ${states[value.state]||value.state||'상태 미확인'}`);
  status.dataset.state=value.state;write(message,value.message);write(counts,value.progress?.label);write(timing,current.kind==='external'?'':elapsedText(value).replaceAll(' · ',' / '));
  write(resumeNote,!value.owned&&['paused','error','partial','review','cancelled'].includes(value.state)&&!(value.actions||[]).some(action=>action.action==='job-resume')?value.resume_note:'');
  const fraction=value.progress?.fraction;progress.hidden=!Number.isFinite(fraction);if(!progress.hidden)progress.value=Math.max(0,Math.min(1,fraction));
  const next=JSON.stringify([value.fields,value.records,value.record_note]);
  if(next!==signature){signature=next;fields.replaceChildren();for(const field of value.fields||[])fields.append(make('dt',field.label),make('dd',String(field.value??'')));
   records.replaceChildren();for(const row of (value.records||[]).slice(-5)){const item=make('li'),date=make('time',clock(row.at));if(row.at)date.dateTime=row.at;item.append(date,make('p',row.message||states[row.state]||row.state||''));records.append(item);}
   write(recordNote,value.record_note||(!value.records?.length?'연결된 상세 실행 기록이 없습니다.':''));
  }
  const key=JSON.stringify([value.actions,value.result,value.workspace,!!value.records?.length,value.state==='error']);
  if(key!==actionsKey){
   const focused=root.activeElement?.dataset?.jobAction;actionsKey=key;footer.replaceChildren();
   for(const action of value.actions||[]){const b=button(action.label,()=>act(()=>api(action.action,action.data)));b.dataset.jobAction=action.action;footer.append(b);}
   const visit=destination=>act(async()=>{const token=generation;await onResult(current,destination,()=>generation===token);if(generation===token)dismiss(false);});
   if(value.result){const b=button('결과 보기',()=>visit(value.result));b.dataset.jobAction='result';footer.append(b);}
   else if(value.workspace){const b=button('작업 화면에서 확인',()=>visit(value.workspace));b.dataset.jobAction='workspace';footer.append(b);}
   if(value.records?.length||value.state==='error'){
    const b=button('표시 기록 저장',()=>{const value=snapshot;const blob=new Blob([JSON.stringify({title:value.title,label:value.label,state:value.state,message:value.message,fields:value.fields,records:value.records,record_note:value.record_note},null,2)],{type:'application/json'});
     const url=URL.createObjectURL(blob),link=make('a');link.href=url;link.download='chida-job-detail.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});b.dataset.jobAction='save';footer.append(b);
   }
   for(const b of footer.children){b.disabled=pending;if(b.dataset.jobAction===focused)b.focus({preventScroll:true});}
  }
 }
 async function refresh(){
  if(!current||loading===generation)return;const token=generation,request=current;loading=token;
  try{const value=await api('job-detail',request);if(token!==generation)return;paint(value);write(error,'');}
  catch(e){if(token===generation)write(error,(snapshot?'마지막 조회 내용을 표시합니다. ':'')+e.message);}
  finally{if(loading===token)loading=null;}
 }
 return {
  open(request,options={}){
   if(root.querySelector('dialog[open]:not(#job-detail)'))return;
   cancelMotion(dialog);dialog.inert=false;
   current={...request};generation++;signature='';actionsKey='';snapshot=null;pending=false;opener=options.opener;getOpener=options.getOpener;
   title.textContent='불러오는 중…';for(const el of [status,message,progress,counts,timing,resumeNote,recordNote,feedback,error])el.hidden=true;fields.replaceChildren();records.replaceChildren();footer.replaceChildren();body.scrollTop=0;
   if(!dialog.open){dialog.show();animateUI(dialog,[{transform:'translateX(24px)',opacity:0},{transform:'translateX(0)',opacity:1}],{duration:280});}
   root.body.dataset.jobDetail='open';onSelection(jobDetailKey(current));heading.focus({preventScroll:true});clearInterval(timer);timer=setInterval(refresh,5000);refresh();
  },
  close:()=>dismiss(false),refresh,key:()=>current?jobDetailKey(current):null,
 };
}
