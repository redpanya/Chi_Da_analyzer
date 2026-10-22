import {createContextInputs} from './context-inputs.js';
import {timecode} from './player.js';
const $=id=>document.getElementById(id);
const node=(tag,text)=>{const el=document.createElement(tag);el.textContent=text;return el;};
export function createExternal({api,onResult}){
  let project=null,busy=false,preview=null,upload=null,serial=0;
  const inputs=createContextInputs(controls,'external');
  const identity=()=>({root:project.root,vod_id:project.vod_id});
  const call=(action,args={})=>api('context-exchange-'+action,{...identity(),...args});
  function controls(){
    const locked=!project||project.locked||busy;
    $('external-create').disabled=locked||!inputs.ready();
    $('external-preview').disabled=locked||(!upload&&!$('external-json').value.trim());
    $('external-import').disabled=locked||!preview?.accepted||(preview.errors.length>0&&!$('external-partial').checked);
    $('external-chat').disabled=locked||$('external-mode').value!=='detail';
    $('external-mode').disabled=$('external-file').disabled=$('external-json').disabled=locked;
    $('external-offset').disabled=locked||!$('external-chat').checked;
  }
  function status(text){$('external-status').textContent=$('external-import-status').textContent=text;}
  function invalidate(){preview=null;$('external-partial').checked=false;$('external-partial-label').hidden=true;$('external-preview-result').replaceChildren();controls();}
  async function perform(fn){
    if(!project||busy)return;busy=true;controls();const path=project.path;
    status('처리 중…');
    try{await fn(path);}catch(e){if(project?.path===path)status(e.message);}
    finally{busy=false;controls();}
  }
  function download(name,text,type='text/plain;charset=utf-8'){
    const url=URL.createObjectURL(new Blob([text],{type}));
    const a=node('a','');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function showBundle(value){
    const box=$('external-downloads');box.replaceChildren();$('external-prompt').value=value.prompt;
    box.append(node('p',`저장된 ${value.mode==='detail'?'상세 문맥':'타임스탬프'} 자료 · 전사 ${value.speech_count}개 · 채팅 ${value.chat_count}개 · ${value.files.length}묶음 · 형식 확인 필요 ${value.rejected_count}개`));
    const owner=project.path,zip=node('button','분할 JSON + 작업서 ZIP 저장');zip.className='primary';
    zip.onclick=()=>{if(project?.path!==owner)return;perform(async path=>{
      const packed=await call('archive',{export_id:value.id});if(project?.path!==path)return;
      download(packed.name,Uint8Array.from(atob(packed.base64),c=>c.charCodeAt(0)),'application/zip');
      $('external-prompt').value=packed.work_order;status('자료 ZIP을 저장했습니다. 작업서.txt를 읽고 파일별 결과 JSON을 만들도록 요청하세요.');
    });};
    box.append(zip,node('p','ZIP 안에는 작업서.txt와 자료 폴더의 분할 JSON이 있습니다. 외부 AI가 ZIP을 읽지 못하면 압축을 풀어 첨부하세요. 완료한 결과 JSON만 모아 ZIP으로 가져오세요.'));
    if(value.cancelled)box.append(node('p','취소된 작업의 자료입니다. 결과를 가져오기 전에 아래 목록에서 작업 재개를 누르세요.'));
    const legacy=node('details',''),summary=node('summary','기존 TXT 방식으로 저장');legacy.append(summary);
    const all=node('button','전체 자료 TXT 저장');all.className='secondary';
    all.onclick=()=>download(`chida-${value.id.slice(0,8)}-all.txt`,value.files.map(f=>`\n===== ${f.name} =====\n${f.text}`).join('\n'));
    legacy.append(all,node('p','파일 크기는 외부 AI 서비스의 토큰 한도 보장이 아닙니다.'));
    for(const f of value.files){const row=node('div','');row.className='external-row';row.append(node('span',f.name+` · ${(new Blob([f.text]).size/1024).toFixed(1)}KB`));const b=node('button','자료 저장');b.className='subtle';b.onclick=()=>download(f.name,f.text);row.append(b);legacy.append(row);}
    box.append(legacy);
  }
  async function refresh(){
    if(!project)return;const request=++serial,path=project.path;
    try{
      const rows=await call('list');if(request!==serial||project?.path!==path)return;
      const box=$('external-list');box.replaceChildren();
      if(!rows.length)box.append(node('p','아직 내보낸 자료가 없습니다.'));
      for(const r of rows){
        const row=node('div','');row.className='external-row';
        row.append(node('span',`${r.created_at.slice(0,16).replace('T',' ')} · ${r.mode==='timestamps'?'타임스탬프':'상세 문맥'} · ${r.received}/${r.chunks.length}묶음 · ${r.cancelled?'취소됨':r.received===r.chunks.length?'가져오기 완료':'외부 결과 대기'} · ${r.input_label}`));
        const files=node('button','자료 다시 열기');files.className='subtle';files.onclick=()=>perform(async()=>{const v=await call('bundle',{export_id:r.id});if(project?.path===path){showBundle(v);status(v.cancelled?'취소된 자료입니다. 작업 재개 후 결과를 가져올 수 있습니다.':'저장한 내보내기 자료입니다.');}});row.append(files);
        if(r.latest_run){const open=node('button','결과 보기');open.className='secondary';open.onclick=()=>onResult(r.latest_run,r.mode);row.append(open);}
        if(!r.cancelled&&r.received<r.chunks.length){const cancel=node('button','외부 작업 취소');cancel.className='subtle';cancel.disabled=project.locked;
          cancel.onclick=()=>{if(confirm('외부 결과 대기를 취소할까요? 원본과 가져온 결과는 유지됩니다.'))perform(async()=>{await call('cancel',{export_id:r.id});if(project?.path===path){invalidate();await refresh();status('외부 작업을 취소했습니다. 저장한 결과는 유지됩니다.');}});};row.append(cancel);}
        if(r.cancelled){const resume=node('button','작업 재개');resume.className='secondary';resume.disabled=project.locked;
          resume.onclick=()=>perform(async()=>{await call('resume',{export_id:r.id});if(project?.path===path){invalidate();await refresh();status('원래 입력이 유지된 작업을 재개했습니다. 결과 파일을 다시 검사하세요.');}});row.append(resume);}
        box.append(row);
      }
    }catch(e){if(request===serial)status(e.message);}
  }
  $('external-mode').onchange=()=>{if($('external-mode').value==='timestamps')$('external-chat').checked=false;controls();};
  $('external-chat').onchange=controls;
  $('external-create').onclick=()=>perform(async path=>{
    const offset=$('external-offset').valueAsNumber;
    if(!Number.isFinite(offset)||Math.abs(offset)>600)throw Error('채팅 시각 보정은 -600~600초입니다.');
    const value=await call('create',{options:{selection:inputs.selection(),mode:$('external-mode').value,include_chat:$('external-chat').checked,chat_offset_ms:Math.round(offset*1000)}});
    if(project?.path!==path)return;showBundle(value);await refresh();status('자료를 만들었습니다. ZIP을 저장해 확인한 뒤 외부 AI에 직접 전달하세요.');
  });
  $('external-copy').onclick=async()=>{try{await navigator.clipboard.writeText($('external-prompt').value);status('요청문을 복사했습니다.');}catch{$('external-prompt').focus();$('external-prompt').select();status('선택한 요청문을 직접 복사하세요.');}};
  $('external-json').oninput=()=>{upload=null;$('external-file').value='';$('external-file-info').textContent='붙여넣은 JSON을 검사합니다.';invalidate();};
  $('external-partial').onchange=controls;
  $('external-file').onchange=()=>perform(async path=>{
    const file=$('external-file').files[0];if(!file)return;
    upload=null;$('external-json').value='';$('external-file-info').textContent='';invalidate();
    if(file.size>10*1024**2)throw Error('결과 파일은 10MiB 이내로 선택하세요.');
    const bytes=new Uint8Array(await file.arrayBuffer());if(project?.path!==path)return;
    if(/\.zip$/i.test(file.name)){
      const parts=[];for(let i=0;i<bytes.length;i+=32768)parts.push(String.fromCharCode(...bytes.subarray(i,i+32768)));
      upload={archive:btoa(parts.join(''))};
    }else if(/\.json$/i.test(file.name)){
      try{$('external-json').value=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{throw Error('UTF-8 JSON 파일로 저장하세요.');}
    }else throw Error('결과 JSON 또는 ZIP을 선택하세요.');
    $('external-file-info').textContent=`${file.name} · ${(file.size/1024).toFixed(1)}KB · ${upload?'ZIP 안의 결과를 파일별로 검사합니다.':'JSON을 검사합니다.'}`;
    status('파일을 읽었습니다. 결과 검사를 진행하세요.');
  });
  $('external-preview').onclick=()=>perform(async path=>{
    invalidate();const payload=upload||{text:$('external-json').value},value=await call('check-files',payload);
    if(project?.path!==path)return;
    preview={...value,payload};const box=$('external-preview-result');
    box.append(node('p',`이번 입력 정상 ${value.accepted}묶음 · 수정 필요 ${value.errors.length}건 · 기존 결과 포함 ${value.received}/${value.total}묶음 · ${value.complete?'전체 범위':'일부 범위'}. 형식 검사이며 요약의 사실성을 보증하지 않습니다.`));
    for(const error of value.errors){const row=node('p',`${error.file}${error.chunk?' · 묶음 '+error.chunk:''}: ${error.message}`);row.className='external-error';box.append(row);}
    if(value.missing.length)box.append(node('p',`아직 받지 않은 묶음 ${value.missing.length}개: ${value.missing.slice(0,30).join(', ')}${value.missing.length>30?' …':''}`));
    $('external-partial-label').hidden=!(value.accepted&&value.errors.length);
    for(const topic of value.topics)box.append(node('p',timecode(topic.start_ms)+' '+topic.title));
    status(!value.accepted?'저장 가능한 새 결과가 없습니다. 아래 검사 오류를 확인하세요.':value.errors.length?'오류 위치를 확인하세요. 정상 결과만 저장하려면 부분 저장에 체크하세요.':'형식을 확인했습니다. 새 결과 버전으로 저장할 수 있습니다.');
  });
  $('external-import').onclick=()=>perform(async path=>{
    if(!preview?.accepted)throw Error('현재 결과 파일을 먼저 검사하세요.');
    const value=await call('import-files',{...preview.payload,token:preview.token,allow_partial:$('external-partial').checked});
    if(project?.path!==path)return;invalidate();await refresh();status(value.duplicate?'이미 저장한 동일 결과입니다.':'새 결과 버전으로 저장했습니다.');await onResult(value.run,value.mode);
  });
  return {refresh,setProject(value){const changed=project?.path!==value?.path;project=value;inputs.setProject(value);
    $('external-title').textContent=value?.metadata.title||'';
    if(changed){serial++;upload=null;invalidate();$('external-json').value='';$('external-file').value='';$('external-file-info').textContent='';status('');$('external-downloads').replaceChildren();$('external-list').replaceChildren();$('external-prompt').value='';}
    controls();
  }};
}
