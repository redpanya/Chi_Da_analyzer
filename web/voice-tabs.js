import {enterView} from './workspace-motion.js';
// 검토 목록의 DOM을 유지해 검색과 선택 상태를 보존한다.
export function createVoiceTabs(){
  const names=['speakers','assigned','failed'],$=id=>document.getElementById(id);let current='speakers';
  function select(name,focus=false){if(!names.includes(name))return;const changed=current!==name;current=name;for(const n of names){const button=$('voice-view-'+n);button.setAttribute('aria-selected',String(n===name));button.tabIndex=n===name?0:-1;$('voice-pane-'+n).hidden=n!==name;}if(changed)enterView($('voice-pane-'+name),0);if(focus)$('voice-view-'+name).focus();}
  for(const [i,name] of names.entries()){
    const button=$('voice-view-'+name);button.onclick=()=>select(name);
    button.onkeydown=e=>{const next=e.key==='ArrowRight'?(i+1)%3:e.key==='ArrowLeft'?(i+2)%3:e.key==='Home'?0:e.key==='End'?2:null;if(next!==null){e.preventDefault();select(names[next],true);}};
  }
  return {select,reset(){select('speakers');},counts(result){$('voice-view-assigned').textContent=`배정된 전사 ${result.total_rows-result.failed}`;$('voice-view-failed').textContent=`인식 실패 ${result.failed}`;},current:()=>current};
}
