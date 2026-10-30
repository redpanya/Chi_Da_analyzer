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
    b.onclick=async()=>{if(choice==='save'){for(const button of dialog.querySelectorAll('button'))button.disabled=true;try{await persist();}catch(e){note.textContent='저장 실패 · '+e.message;return;}finally{for(const button of dialog.querySelectorAll('button'))button.disabled=false;}}
      dialog.close();const resolve=pending;pending=null;resolve?.(choice!=='cancel');};dialog.append(b);
  }
  dialog.addEventListener('cancel',()=>{const resolve=pending;pending=null;resolve?.(false);});document.body.append(dialog);
  async function allow(){if(!dirty()&&!saving)return true;if(pending)return false;dialog.showModal();return new Promise(resolve=>pending=resolve);}
  document.addEventListener('click',async event=>{const link=event.target.closest?.('a[href]');if(!link||link.download||link.target==='_blank'||event.metaKey||event.ctrlKey||event.defaultPrevented)return;
    if(new URL(link.href,location.href).pathname===location.pathname&&link.hash)return;
    if(dirty()||saving){event.preventDefault();if(await allow()){departing=true;location.assign(link.href);}}});
  globalThis.addEventListener('beforeunload',event=>{if(!departing&&(dirty()||saving)){event.preventDefault();event.returnValue='';}});
  return {changed:render,dirty,save:persist,allow,accept(at,value=read()){baseline=JSON.stringify(value);failure='';if(at&&!Number.isNaN(Date.parse(at)))savedAt=new Date(at).toLocaleString('ko-KR');render();}};
}
