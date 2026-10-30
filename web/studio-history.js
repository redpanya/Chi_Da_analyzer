import {timecode} from './player.js';
import {latestResponse} from './page-lifecycle.js';
const el=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
export function studioHistory({host,api,identity,refresh,onError}){
  let runs=[],page=0,signature='';const responses=latestResponse();
  const tools=el('div');tools.className='play-actions';const search=el('input');search.type='search';search.placeholder='작업 날짜·상태·제목 검색';search.setAttribute('aria-label','클립 작업 검색');
  const prev=el('button','이전'),next=el('button','다음'),count=el('span');tools.append(search,prev,count,next);host.before(tools);
  search.oninput=()=>{page=0;draw();};prev.onclick=()=>{page--;draw();};next.onclick=()=>{page++;draw();};
  const dialog=el('dialog'),title=el('h2'),note=el('p'),error=el('p'),cancel=el('button','취소'),confirm=el('button','휴지통으로 이동');dialog.setAttribute('aria-label','클립 작업 정리 확인');dialog.append(title,note,error,cancel,confirm);document.body.append(dialog);cancel.onclick=()=>dialog.close();let pending=null,busy=false;
  dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});
  async function preview(run,mode){const current=responses.begin();pending=null;title.textContent=mode==='delete'?'작업 기록과 출력 파일을 삭제할까요?':'완료 영상의 중간 파일을 정리할까요?';note.textContent='파일 확인 중…';error.textContent='';confirm.disabled=true;dialog.showModal();
    try{const value=await api('studio-clean-preview',{...identity(),run:run.id,mode});if(!dialog.open||!current())return;pending={...value,run:run.id};note.textContent=`${mode==='delete'?'기록·생성 파일':'중간 영상·자막 이미지·로그'} ${(value.bytes/1024**2).toFixed(1)}MiB · ${value.folder}\n${value.scope|| (mode==='delete'?'원본과 분석 결과는 유지합니다.':'완성 영상·자막은 유지합니다.')}`;confirm.disabled=false;}catch(e){if(dialog.open&&current())error.textContent=e.message;}}
  confirm.onclick=async()=>{if(!pending||busy)return;busy=true;cancel.disabled=confirm.disabled=true;try{await api('studio-clean',{...identity(),...pending});dialog.close();signature='';await refresh();}catch(e){error.textContent=e.message+' 창을 닫고 다시 확인하세요.';}finally{busy=false;cancel.disabled=false;}};
  function draw(){
    const filtered=runs.filter(r=>JSON.stringify([r.created_at,r.message,r.outputs]).toLowerCase().includes(search.value.toLowerCase()));page=Math.max(0,Math.min(page,Math.ceil(filtered.length/10)-1));
    prev.disabled=page===0;next.disabled=(page+1)*10>=filtered.length;count.textContent=`${filtered.length?page+1:0}/${Math.ceil(filtered.length/10)}쪽 · ${filtered.length}개`;host.replaceChildren();
    for(const r of filtered.slice(page*10,(page+1)*10)){
      const item=el('article');item.append(el('strong',`${r.kind==='start'?'영상 저장':'범위 분석'} · ${new Date(r.created_at).toLocaleString('ko-KR')}`),el('p',r.message||r.state));
      const progress=el('progress');progress.max=1;progress.value=r.progress||0;item.append(progress,el('p',`전체 ${Math.round((r.progress||0)*100)}% · ${r.phase_name||''}${r.state==='running'&&r.phase_progress!=null?' · 현재 단계 '+Math.round(r.phase_progress*100)+'%':''} · 실행 시간 ${timecode((r.elapsed_seconds||0)*1000)}`));
      item.append(el('p',`완성 영상 ${(r.output_bytes/1024**2||0).toFixed(1)}MiB · ${r.folder||''}`));
      if(r.state==='running'){const b=el('button','작업 중단');b.onclick=()=>api('studio-stop',identity()).then(refresh).catch(onError);item.append(b);}
      else if(r.state!=='complete'){const b=el('button','완료 자료에서 이어하기');b.onclick=()=>api('studio-resume',{...identity(),run:r.id}).then(refresh).catch(onError);item.append(b);}
      for(const [key,out] of Object.entries(r.outputs||{}))for(const [kind,name] of Object.entries(out.assets)){const a=el('a',`${out.title} · ${kind.toUpperCase()}`);a.href='file?'+new URLSearchParams({...identity(),kind:'studio',run:r.id,key:key+':'+kind});a.className='back-button';a.download=name;item.append(a);}
      if(r.kind==='start'&&r.state!=='running'){
        if(r.state==='complete'){const b=el('button','중간 파일 정리');b.disabled=!!r.intermediates_cleaned_at;b.onclick=()=>preview(r,'intermediate');item.append(b);}
        const b=el('button','작업 삭제');b.onclick=()=>preview(r,'delete');item.append(b);
      }else if(r.project){const a=el('a','이 범위 결과 열기');a.href='./?'+new URLSearchParams({root:r.project.root,vod_id:r.project.vod_id});item.append(a);if(r.state!=='running'){const b=el('button','범위 작업 삭제');b.onclick=()=>preview(r,'delete');item.append(b);}}
      host.append(item);
    }
  }
  return {set(value){runs=value;const key=JSON.stringify(value);if(key!==signature){signature=key;draw();}}};
}
