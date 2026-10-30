// VOD 공통 방송 상황과 모드별 요청. 실행/외부 작업서에는 별도 스냅샷을 저장한다.
const listeners=new Set();
const labels={detail:'상세 문맥 정리',timestamps:'타임스탬프',clips:'클립 후보'};
export function createBackground({api,message,onChange=()=>{},onLoad=()=>{},onEdit=()=>{},prefix='context',mode=()=> 'detail'}){
  const $=id=>document.getElementById(prefix+'-'+id);
  let project=null,serial=0,loaded=false,busy=false,active='detail',settings={text:'',custom_requests:{}},backgroundDirty=false,snapshot=false,edits=0;
  const drafts=new Map();
  const selectedMode=()=>labels[mode()]?mode():'detail';
  const values=()=>({background:$('background').value,custom_request:$('custom').value});
  const identity=()=>({root:project.root,vod_id:project.vod_id});
  function controls(){
    for(const id of ['background','custom','background-save'])$(id).disabled=!project||project.locked||busy||!loaded;
    onChange();
  }
  function render(){
    $('background').value=settings.text;
    $('custom').value=drafts.has(active)?drafts.get(active):settings.custom_requests[active]||'';
    $('background-status').textContent=loaded?`${labels[active]} 요청 · 방송 상황은 이 VOD의 세 모드에 공통 적용됩니다.`:'';
    controls();
  }
  listeners.add((path,value)=>{
    if(project?.path!==path||!loaded||busy)return;
    if(!backgroundDirty)settings.text=value.text;
    settings.custom_requests=value.custom_requests||{};if(snapshot)return;render();onLoad();
  });
  async function save(){
    if(!project||project.locked||!loaded||busy)return false;
    const owner=project.path,request=serial,selected=active,revision=edits,input=values();busy=true;controls();
    try{
      const saved=await api('context-background-save',{...identity(),text:input.background,mode:selected,custom_request:input.custom_request});
      for(const listener of listeners)listener(owner,saved);
      if(request!==serial||project?.path!==owner||selected!==active||revision!==edits)return false;
      settings=saved;drafts.delete(selected);backgroundDirty=false;snapshot=false;
      $('background-status').textContent='저장됨 · 다음 새 분석·내보내기에 적용';return input;
    }catch(error){if(request===serial)message(error.message);return false;}
    finally{busy=false;controls();}
  }
  $('background-form').onsubmit=e=>{e.preventDefault();save();};
  for(const id of ['background','custom'])$(id).oninput=()=>{
    edits++;snapshot=false;
    if(id==='background'){settings.text=$('background').value;backgroundDirty=true;}
    else drafts.set(active,$('custom').value);
    $('background-status').textContent='미저장 · 새 분석·자료 생성을 시작하면 함께 저장합니다';onEdit();
  };
  return {save,values,ready:()=>loaded&&!busy,
    selectMode(){const next=selectedMode();if(next===active)return;active=next;snapshot=false;render();return onLoad();},
    useSnapshot(value){active=selectedMode();snapshot=true;$('background').value=value.background||'';$('custom').value=value.custom_request||'';$('background-status').textContent='저장 당시 설정 · 기존 작업서는 그대로 유지됩니다';controls();},
    async setProject(value){
      const changed=value?.path!==project?.path;project=value;if(!changed){controls();return;}
      const request=++serial;loaded=false;active=selectedMode();settings={text:'',custom_requests:{}};drafts.clear();backgroundDirty=false;snapshot=false;edits++;render();
      if(!value)return;
      $('background-status').textContent='방송 상황·추가 요청 확인 중…';
      try{const result=await api('context-background',identity());if(request!==serial)return;settings={text:result.text||'',custom_requests:result.custom_requests||{}};loaded=true;render();onLoad();}
      catch(error){if(request===serial)message(error.message);}finally{controls();}
    }};
}
