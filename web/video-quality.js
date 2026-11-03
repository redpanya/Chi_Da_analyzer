export function transferMessage(task){
 const legacy=' · 직전 영상 기준 자막은';
 if(task.state==='complete' && task.verification?.replacement_timeline && task.message?.includes(legacy)){
   return task.message.split(legacy)[0]+' · 자막을 열면 선택한 전사와 영상의 음성을 대조합니다.';
 }
 return task.message;
}

export function setupVideoQuality({api,getProject,onChanged}) {
 const $=id=>document.getElementById('video-quality-'+id);
 const dialog=$('dialog'),select=$('select'),apply=$('apply'),note=$('note');
 let source=null,historyKey='';
 const complete=p=>p?.tasks.video.state==='complete';
 const eligible=p=>p && (!p.input || p.download_range) && (complete(p)?!p.locked:
   ['idle','paused','error'].includes(p.tasks.video.state) && (!p.locked || p.owned));
 function render(p){
   const format=p?.metadata.formats?.find(f=>f.id===p.format_id);
   $('current').textContent=[format && '현재 화질 · '+format.label,p?.video_replacement && '교체할 화질 · '+p.video_replacement.label].filter(Boolean).join(' / ');
   $('open').hidden=!p || !!(p.input && !p.download_range);
   $('open').textContent=complete(p)?'다른 화질로 다시 받기':'화질 변경';
   $('open').disabled=!eligible(p);
   $('cleanup').hidden=!p?.video_cleanup?.length;
   const versions=p?.saved_video_versions||[],key=JSON.stringify([p?.path,versions]);
   if(key!==historyKey){
     historyKey=key;$('history').hidden=!versions.length;$('links').replaceChildren();
     for(const v of versions)for(const type of ['original','playback']){
       if(type==='playback' && v.assets.playback===v.assets.original)continue;
       const a=document.createElement('a');a.className='text-link';a.download='';
       a.textContent=v.label+' · '+(type==='original'?'원본':'재생용')+' 저장';
       a.href='file?'+new URLSearchParams({root:p.root,vod_id:p.vod_id,kind:'saved-video',version:v.id,key:type});
       $('links').append(a);
     }
   }
   $('open').title=eligible(p)?'현재 제공 화질 확인':'영상 다운로드를 중단한 뒤 화질을 바꿀 수 있습니다';
   if(dialog.open && (p?.path!==source?.path || p?.format_id!==source?.format_id))dialog.close();
 }
 $('open').onclick=async()=>{
   const p=getProject();if(!eligible(p))return;
   source=p;select.replaceChildren();select.disabled=apply.disabled=true;
   $('existing').hidden=!complete(p);$('partial').hidden=complete(p);
   $('keep').checked=true;
   apply.textContent=complete(p)?'영상만 다시 받기':'화질 적용';
   $('title-vod').textContent=p.metadata.title;note.textContent='치지직에서 현재 제공하는 화질을 확인하고 있습니다.';
   dialog.showModal();
   try{
     const meta=await api('inspect',{url:'https://chzzk.naver.com/video/'+p.vod_id});
     if(!dialog.open || source!==p)return;
     for(const f of meta.formats.filter(f=>f.id!==p.format_id && f.height>0 && f.height<=1080))select.add(new Option(f.label,f.id));
     select.disabled=apply.disabled=!select.options.length;
     note.textContent=select.options.length?(complete(p)?'선택한 화질로 영상 다운로드를 시작합니다.':'적용한 뒤 영상 시작 또는 순차 작업 이어가기를 누르세요.'):'현재 선택할 수 있는 다른 화질이 없습니다.';
   }catch(error){if(dialog.open && source===p)note.textContent=error.message;}
 };
 $('close').onclick=()=>dialog.close();
 apply.onclick=async()=>{
   const p=source;apply.disabled=select.disabled=true;note.textContent='선택한 화질을 확인하고 있습니다.';
   try{
     const updated=await api('video-quality',{root:p.root,vod_id:p.vod_id,expected:p.format_id,format_id:select.value,
       ...(complete(p)?{existing:$('delete').checked?'delete':'keep'}:{})});
     dialog.close();if(getProject()?.path===p.path)await onChanged(updated);
   }catch(error){if(dialog.open && source===p){note.textContent=error.message;apply.disabled=select.disabled=false;}}
 };
 return {render};
}
