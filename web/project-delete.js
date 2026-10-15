export function connectDeletion({api,getProject,onDeleted,beforeOpen=()=>{}}) {
  const $=id=>document.getElementById(id);let pending=null,working=false;
  $('delete-project').onclick=async()=>{
    const project=getProject();if(!project||working)return;
    $('delete-project').disabled=true;
    try{const value=await api('delete-preview',{root:project.root,vod_id:project.vod_id});if(getProject()?.path!==project.path)return;pending={...value,root:project.root};$('delete-description').textContent=`${value.title} · VOD ${value.vod_id} · 약 ${(value.bytes/1e6).toFixed(1)}MB`;$('delete-path').textContent=value.path;$('delete-confirmation').value='';$('delete-confirmation').placeholder=value.vod_id;$('delete-error').textContent='';beforeOpen();$('delete-dialog').showModal();$('delete-confirmation').focus();}
    catch(error){$('notice').hidden=false;$('notice').textContent=error.message;}
    finally{$('delete-project').disabled=!!getProject()?.locked;}
  };
  $('delete-cancel').onclick=()=>{pending=null;$('delete-dialog').close();};
  $('delete-dialog').addEventListener('cancel',event=>{if(working)event.preventDefault();else pending=null;});
  $('delete-form').onsubmit=async event=>{
    event.preventDefault();if(!pending||working)return;
    if(pending.path!==getProject()?.path)return $('delete-error').textContent='선택한 VOD가 바뀌었습니다. 다시 확인하세요.';
    if($('delete-confirmation').value!==pending.vod_id)return $('delete-error').textContent='표시된 VOD 번호를 입력하세요.';
    working=true;$('delete-confirm').disabled=true;$('delete-cancel').disabled=true;
    try{const value=await api('delete-project',{root:pending.root,vod_id:pending.vod_id,token:pending.token,confirmation:$('delete-confirmation').value});const removed=pending;pending=null;$('delete-dialog').close();await onDeleted(removed,value);}
    catch(error){$('delete-error').textContent=error.message;}
    finally{working=false;$('delete-confirm').disabled=false;$('delete-cancel').disabled=false;}
  };
}
