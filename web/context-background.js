export function createBackground({api,message,onChange=()=>{}}){
  const $=id=>document.getElementById(id);let project=null,serial=0,loaded=false,busy=false;
  const identity=()=>({root:project.root,vod_id:project.vod_id});
  function controls(){$('context-background').disabled=!project||project.locked||busy||!loaded;$('context-background-save').disabled=!project||project.locked||busy||!loaded;onChange();}
  async function save(){
    if(!project||!loaded||busy)return false;
    const selected=project.path,request=serial;busy=true;controls();
    try{await api('context-background-save',{...identity(),text:$('context-background').value});if(request!==serial||project?.path!==selected)return false;$('context-background-status').textContent='저장됨 · 다음 새 분석부터 적용';return true;}
    catch(error){if(request===serial)message(error.message);return false;}
    finally{busy=false;controls();}
  }
  $('context-background-form').onsubmit=e=>{e.preventDefault();save();};
  $('context-background').oninput=()=>{$('context-background-status').textContent='미저장 · 새 분석을 시작하면 함께 저장합니다';};
  return {save,ready:()=>loaded&&!busy,async setProject(value){const changed=value?.path!==project?.path;project=value;if(!changed){controls();return;}const request=++serial;loaded=false;$('context-background').value='';$('context-background-status').textContent=value?'방송 배경 설명 확인 중…':'';controls();if(!value)return;
    try{const result=await api('context-background',identity());if(request!==serial)return;$('context-background').value=result.text;loaded=true;$('context-background-status').textContent='선택 입력 · 실제 발언에 없는 사건은 추가하지 않습니다';}
    catch(error){if(request===serial)message(error.message);}finally{controls();}}};
}
