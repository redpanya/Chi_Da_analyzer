export function connectDeletion({api,getProject,onDeleted,beforeOpen=()=>{}}) {
  const $=id=>document.getElementById(id);let pending=null,working=false,request=0;
  $('delete-project').onclick=async()=>{
    const project=getProject();if(!project||working)return;
    const ticket=++request;pending=null;
    $('delete-project').disabled=true;
    $('delete-description').textContent=`${project.metadata.title} · VOD ${project.vod_id}`;
    $('delete-path').textContent=project.path;$('delete-confirmation').value='';
    $('delete-confirmation').placeholder=project.vod_id;$('delete-confirmation').disabled=true;
    $('delete-confirm').disabled=true;$('delete-error').textContent='삭제할 자료를 확인하고 있습니다…';
    beforeOpen();$('delete-dialog').showModal();$('delete-cancel').focus();
    try{
      const value=await api('delete-preview',{root:project.root,vod_id:project.vod_id});
      if(ticket!==request||getProject()?.path!==project.path||!$('delete-dialog').open)return;
      pending={...value,root:project.root};
      $('delete-description').textContent=`${value.title} · VOD ${value.vod_id} · 약 ${(value.bytes/1e6).toFixed(1)}MB`;
      $('delete-path').textContent=value.path;$('delete-error').textContent='';$('delete-confirmation').disabled=false;
    }catch(error){if(ticket===request&&$('delete-dialog').open)$('delete-error').textContent=error.message;}
    finally{if(ticket===request)$('delete-project').disabled=!!getProject()?.locked;}
  };
  $('delete-confirmation').oninput=()=>{$('delete-confirm').disabled=working||!pending||$('delete-confirmation').value!==String(pending.vod_id);};
  $('delete-cancel').onclick=()=>$('delete-dialog').close();
  $('delete-dialog').addEventListener('cancel',event=>{if(working)event.preventDefault();});
  $('delete-dialog').addEventListener('close',()=>{request++;pending=null;$('delete-project').disabled=!!getProject()?.locked;});
  $('delete-form').onsubmit=async event=>{
    event.preventDefault();if(!pending||working)return;
    if(pending.path!==getProject()?.path)return $('delete-error').textContent='선택한 VOD가 바뀌었습니다. 다시 확인하세요.';
    if($('delete-confirmation').value!==String(pending.vod_id))return $('delete-error').textContent='표시된 VOD 번호를 입력하세요.';
    working=true;$('delete-confirm').disabled=true;$('delete-cancel').disabled=true;
    try{const value=await api('delete-project',{root:pending.root,vod_id:pending.vod_id,token:pending.token,confirmation:$('delete-confirmation').value});const removed=pending;pending=null;$('delete-dialog').close();await onDeleted(removed,value);}
    catch(error){$('delete-error').textContent=error.message;}
    finally{working=false;$('delete-confirm').disabled=false;$('delete-cancel').disabled=false;}
  };
}
