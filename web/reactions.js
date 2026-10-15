const $ = id => document.getElementById(id);
// 분석 생성·설정은 여기에서, 그래프·후보·채팅 탐색은 통합 화면에서 한 번만 표시한다.
export function createReactions({api,onDone}) {
  let project=null,key='',result=null,running=false,serial=0,errorMessage='';
  const options=()=>({window_seconds:Number($('window-seconds').value),min_messages:$('min-messages').valueAsNumber,burst_ratio:$('burst-ratio').valueAsNumber,min_repeats:$('min-repeats').valueAsNumber,repeat_share:$('repeat-share').valueAsNumber/100});
  function render(){
    $('analyze').disabled=!project||running||project.locked||!project.tasks.chat.assets?.jsonl;
    $('analysis-wait').hidden=!running&&!project?.analysis_running;
    $('analysis-status').textContent=errorMessage||(running?'채팅 반응 분석 중…':result?`${result.source_label||(result.complete_source?'전체 제공 범위':'일부 자료')} · ${result.messages.toLocaleString()}건 · 반응 후보 ${result.candidates.length}개${result.boundary_unverified?' · 경계 확인 필요':''}`:'저장된 채팅으로 반응 구간을 찾아보세요.');
    $('settings-note').textContent=result?(result.stale?'채팅이 변경됐습니다. 다시 분석하세요.':JSON.stringify(options())!==JSON.stringify(result.settings)?'설정이 바뀌었습니다. 현재 화면은 이전 분석 결과입니다.':'현재 설정의 저장된 분석을 표시합니다.'):'';
  }
  $('analysis-settings').oninput=render;
  $('analysis-form').onsubmit=async event=>{
    event.preventDefault();if(!project||running)return;
    const selected=project.path;errorMessage='';running=true;render();$('analysis-status').textContent='채팅 반응 분석 중…';
    try{const value=await api('analyze',{root:project.root,vod_id:project.vod_id,settings:options(),allow_partial:$('allow-partial').checked});if(project?.path===selected){result=value;render();onDone();}}
    catch(error){if(project?.path===selected){errorMessage=error.message;render();}}
    finally{running=false;$('analyze').disabled=!project||project.locked||!project.tasks.chat.assets?.jsonl;$('analysis-wait').hidden=true;}
  };
  return {async setProject(value){
    project=value;render();const next=value?JSON.stringify([value.path,value.tasks.chat.state,value.tasks.chat.assets?.jsonl]):'';if(next===key)return;
    key=next;result=null;errorMessage='';const request=++serial;render();if(!value)return;
    try{const data=await api('analysis',{root:value.root,vod_id:value.vod_id});if(request!==serial)return;result=data;if(data){for(const [id,name] of [['window-seconds','window_seconds'],['min-messages','min_messages'],['burst-ratio','burst_ratio'],['min-repeats','min_repeats']])$(id).value=data.settings[name];$('repeat-share').value=data.settings.repeat_share*100;}render();}catch(error){if(request===serial){errorMessage=error.message;render();}}
  }};
}
