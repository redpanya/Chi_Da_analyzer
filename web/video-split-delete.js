export function connectSplitDeletion({api,getJob,beforeDelete,onDeleted}){
  const $=id=>document.getElementById(id),dialog=$('split-delete-dialog');
  let pending=null,working=false,request=0;
  const update=({busy=false}={})=>{
    const job=getJob();$('split-delete').hidden=!job;
    $('split-delete').disabled=busy||working||['planning','running'].includes(job?.state);
    $('split-delete').title=['planning','running'].includes(job?.state)?'작업을 중단한 뒤 삭제할 수 있습니다.':'';
  };
  $('split-delete').onclick=async()=>{
    const job=getJob();if(!job||working||$('split-delete').disabled)return;
    const ticket=++request;pending=null;
    $('split-delete-name').textContent=job.source.name;
    $('split-delete-scope').textContent='';$('split-delete-error').textContent='삭제할 파일을 확인하고 있습니다…';
    $('split-delete-confirm').disabled=true;dialog.showModal();$('split-delete-cancel').focus();
    try{
      const value=await api('delete-preview',{id:job.id});
      if(ticket!==request||getJob()?.id!==job.id||!dialog.open)return;
      pending=value;
      $('split-delete-name').textContent=`${value.name} · ${new Date(value.created_at).toLocaleString('ko-KR')}`;
      $('split-delete-scope').textContent=`작업 기록·로그와 분할 파일 ${value.output_count}개 (약 ${(value.bytes/1024**2).toFixed(1)}MiB)${value.folder?'\n'+value.folder:''}`;
      $('split-delete-error').textContent='';$('split-delete-confirm').disabled=false;
    }catch(e){if(ticket===request&&dialog.open)$('split-delete-error').textContent=e.message;}
  };
  $('split-delete-cancel').onclick=()=>dialog.close();
  dialog.addEventListener('cancel',e=>{if(working)e.preventDefault();});
  dialog.addEventListener('close',()=>{request++;pending=null;update();});
  $('split-delete-confirm').onclick=async()=>{
    if(!pending||working||getJob()?.id!==pending.id)return;
    working=true;update();$('split-delete-confirm').disabled=$('split-delete-cancel').disabled=true;
    $('split-delete-error').textContent='휴지통으로 이동하고 있습니다…';
    try{
      beforeDelete();await api('delete',{id:pending.id,token:pending.token});
      dialog.close();await onDeleted();
    }catch(e){$('split-delete-error').textContent=e.message+' 삭제 창을 닫고 다시 확인해 주세요.';}
    finally{working=false;$('split-delete-cancel').disabled=false;update();}
  };
  return update;
}
