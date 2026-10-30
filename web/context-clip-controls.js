import {createBackground} from './context-background.js';
import {createContextInputs} from './context-inputs.js';
import {elapsedText} from './task-timing.js';
const $=id=>document.getElementById('context-clips-'+id);

// 생성 설정·진행은 결과 뷰어와 분리한다. 외부 결과에는 이어하기를 제공하지 않는다.
export function createClipControls({api,onProject}){
  let project=null,result=null;
  const inputs=createContextInputs(controls,'context-clips');
  const background=createBackground({api,message:text=>$('notice').textContent=text,onChange:controls,prefix:'context-clips',mode:()=> 'clips'});
  function controls(){
    $('generate').disabled=!project||project.locked||!inputs.ready()||!background.ready();
    $('resume').disabled=!project||project.locked||!result||result.origin!=='local'||result.complete||result.stale;
    $('prepare').disabled=!project||project.locked;
    for(const id of ['thinking','chat','offset'])$(id).disabled=!project||project.locked;
    $('stop').disabled=!project?.context?.owned||project.context.state==='stopping';
  }
  async function start(action,options){
    if(!project)return;const path=project.path;$('notice').textContent='';
    try{const value=await api('context-start',{root:project.root,vod_id:project.vod_id,action,options});if(project?.path===path)onProject(value);}
    catch(error){if(project?.path===path)$('notice').textContent=error.message;}
  }
  $('generate').onclick=async()=>{
    if(!inputs.ready())return;
    const offset=$('offset').valueAsNumber;
    if(!Number.isFinite(offset)||Math.abs(offset)>600){$('notice').textContent='채팅 보정은 -600~600초로 입력하세요.';return;}
    const path=project?.path,options={selection:inputs.selection(),thinking:$('thinking').checked,include_chat:$('chat').checked,chat_offset_ms:Math.round(offset*1000)};
    const settings=await background.save();if(!settings||project?.path!==path)return;
    return start('clips',{...options,...settings});
  };
  $('resume').onclick=()=>result&&start('clips-resume',{run:result.id});
  $('prepare').onclick=()=>start('model',{});
  $('stop').onclick=async()=>{
    if(!project)return;const path=project.path;
    try{const value=await api('context-stop',{root:project.root,vod_id:project.vod_id});if(project?.path===path)onProject(value);}
    catch(error){if(project?.path===path)$('notice').textContent=error.message;}
  };
  return {setResult(value){result=value;controls();},setProject(value){
    const changed=project?.path!==value?.path;project=value;
    if(changed){result=null;$('notice').textContent='';$('thinking').checked=true;$('chat').checked=true;$('offset').value='0';}
    inputs.setProject(value);background.setProject(value);controls();
    const s=value?.context,p=s?.progress||{},m=s?.model,clipTask=s?.action?.startsWith('clips');
    $('model').textContent=m?`Gemma 4 E4B · ${m.ready?'모델 준비됨':'모델 준비 필요'} · ${m.engine?'엔진 포함/설치됨':'엔진 없음'}`:'';
    $('progress-status').textContent=s?.action?`${clipTask?'클립 후보':s.action==='model'?'모델 준비':'다른 문맥 모드'} · ${s.message||''}${p.total!=null?` · ${p.done}/${p.total} 발언 범위`:''}`:'전사를 선택하고 Gemma 클립 후보 생성을 시작하세요.';
    $('elapsed').textContent=elapsedText(s);
    const bar=$('progress');
    if(p.total_bytes)bar.value=Math.min(99,100*p.bytes/p.total_bytes);
    else if(clipTask&&p.total)bar.value=Math.min(100,100*p.done/p.total);
    else if(s?.owned)bar.removeAttribute('value');else bar.value=0;
  }};
}
