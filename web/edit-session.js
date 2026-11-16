// 저장 대상 스냅샷을 비교해 미저장 편집의 이탈을 보호한다.
export function createEditSession({read,save,status}){
  let baseline=null,saving=null,failure='',pending=null,departing=false,savedAt='';
  const snapshot=()=>JSON.stringify(read());
  const dirty=()=>baseline!==null&&snapshot()!==baseline;
  const render=()=>{status.textContent=failure|| (saving?'저장 중…':dirty()?'저장하지 않은 변경 있음':'저장됨'+(savedAt?' · '+savedAt:''));status.dataset.state=failure?'error':dirty()?'changed':'saved';};
  async function persist(){
    if(saving)return saving;
    const key=snapshot(),value=JSON.parse(key);failure='';
    saving=Promise.resolve().then(()=>save(value)).then(()=>{baseline=key;savedAt=new Date().toLocaleTimeString('ko-KR');}).catch(e=>{failure='저장 실패 · '+e.message;throw e;}).finally(()=>{saving=null;render();});render();return saving;
  }
  const dialog=document.createElement('dialog');dialog.className='edit-leave-dialog';
  const title=document.createElement('h2');title.textContent='변경 내용을 저장할까요?';
  const note=document.createElement('p');note.textContent='저장에 실패하면 현재 편집 화면에 머뭅니다.';
  dialog.setAttribute('aria-label','편집 내용 저장 확인');dialog.append(title,note);
  for(const [label,choice] of [['저장하고 이동','save'],['변경 버리고 이동','discard'],['계속 편집','cancel']]){
    const b=document.createElement('button');b.textContent=label;b.type='button';
    b.onclick=async()=>{
      const resolve=pending;
      if(!resolve)return;
      if(choice==='save'){
        const buttons=dialog.querySelectorAll('button');
        for(const button of buttons)button.disabled=true;
        try{await persist();}catch(e){note.textContent='저장에 실패했습니다. '+e.message;return;}
        finally{for(const button of buttons)button.disabled=false;}
      }
      if(pending===resolve){pending=null;resolve(choice!=='cancel');}
    };
    dialog.append(b);
  }
  dialog.addEventListener('cancel',event=>{if(departing){event.preventDefault();return;}const resolve=pending;pending=null;resolve?.(false);});document.body.append(dialog);
  async function allow({leaveDocument=false}={}){
    if(saving){try{await saving;}catch{/* 저장 실패 시 확인 창에서 재시도할 수 있다. */}}
    if(!dirty())return true;if(pending||departing)return false;
    dialog.showModal();const accepted=await new Promise(resolve=>pending=resolve);
    // 문서 이동을 승인하면 다음 문서가 열릴 때까지 편집기 위에 확인창을 유지한다.
    if(!accepted||!leaveDocument)dialog.close();
    return accepted;
  }
  function resetDeparture(){if(departing&&dialog.open)dialog.close();departing=false;}
  document.addEventListener('click',async event=>{
    const link=event.target.closest?.('a[href]');
    if(!link||event.defaultPrevented||event.button>0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||link.hasAttribute?.('download')||link.download||(link.target&&link.target!=='_self'))return;
    const here=new URL(location.href),next=new URL(link.href,here);
    if(next.hash&&next.origin===here.origin&&next.pathname===here.pathname&&next.search===here.search)return;
    if(!dirty()&&!saving)return;
    event.preventDefault();
    if(!await allow({leaveDocument:true}))return;
    departing=true;
    try{location.assign(next.href);}catch(e){resetDeparture();failure='화면 이동에 실패했습니다. '+e.message;render();}
  });
  globalThis.addEventListener('pageshow',resetDeparture);
  globalThis.navigation?.addEventListener('navigateerror',resetDeparture);
  globalThis.addEventListener('beforeunload',event=>{if(!departing&&(dirty()||saving)){event.preventDefault();event.returnValue='';}});
  return {changed:render,dirty,save:persist,allow,accept(at,value=read()){baseline=JSON.stringify(value);failure='';if(at&&!Number.isNaN(Date.parse(at)))savedAt=new Date(at).toLocaleString('ko-KR');render();}};
}
