export function createLocalImport({api,onProject,onComplete}){
  const $=id=>document.getElementById(id);let cancelled=false,upload=null,running=false;
  function mode(){const local=$('import-local').checked;$('local-file-fields').hidden=!local;$('quality').hidden=local;$('quality-label').hidden=local;$('start').textContent=local?'비디오 복사·전체 채팅 받기 →':'영상·채팅 다운로드 시작 →';return local;}
  for(const id of ['import-local','import-online'])$(id).onchange=()=>{mode();$('url').dispatchEvent(new Event('input'));};
  $('local-file').onchange=()=>{const f=$('local-file').files[0];$('local-file-info').textContent=f?`${f.name} · ${(f.size/1024**2).toFixed(1)} MiB · 원래 파일은 유지합니다.`:'';};
  $('local-upload-stop').onclick=async()=>{cancelled=true;if(upload)try{await api('import-cancel',{upload});}catch{};};
  return {isLocal:mode,async start(meta,root){
    if(running)throw Error('이미 첨부 파일을 받고 있습니다.');
    const file=$('local-file').files[0],seconds=$('local-start').valueAsNumber;
    if(!file)throw Error('비디오 파일을 첨부하세요.');
    if(!Number.isFinite(seconds)||seconds<0)throw Error('내 영상 시작의 VOD 시각을 초로 입력하세요.');
    if(!$('local-confirm').checked)throw Error('같은 VOD의 연속 영상인지 확인하세요.');
    const input={name:file.name,size:file.size,start_vod_ms:Math.round(seconds*1000),confirmed:true};
    cancelled=false;running=true;$('local-upload-stop').hidden=false;
    const controls=['import-local','import-online','local-file','local-start','local-confirm','url'];
    for(const id of controls)$(id).disabled=true;
    try{
      const session=await api('import-start',{root,vod_id:meta.id,file:input});upload=session.upload;onProject(session.project);
      for(let index=0,start=0;start<file.size;index++,start+=session.chunk_size){
        if(cancelled)throw Error('파일 가져오기를 중단했습니다. 같은 파일을 다시 첨부하면 이어받습니다.');
        const bytes=await file.slice(start,start+session.chunk_size).arrayBuffer();
        const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
        if(index<session.chunks)await api('import-check',{upload,index,sha});
        else{
          const response=await fetch('api/import-chunk?'+new URLSearchParams({upload,index,sha}),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:bytes});
          const result=await response.json();if(!response.ok)throw Error(result.error||'파일 전송 실패');
        }
        $('local-file-info').textContent=`복사·기존 조각 확인 ${Math.min(100,Math.round((start+bytes.byteLength)/file.size*100))}% · ${file.name}`;
      }
      await api('import-finish',{upload});onComplete();
    }catch(error){if(upload)try{await api('import-cancel',{upload});}catch{};throw error;}
    finally{for(const id of controls)$(id).disabled=false;running=false;upload=null;$('local-upload-stop').hidden=true;}
  }};
}
