// 템플릿은 앱 공용 저장소에, 적용한 디자인은 편집 초안에 값으로 남긴다.
const $=id=>document.getElementById(id);
export function captionTemplates({api,design}){
  const dialog=$('caption-template-dialog'),form=$('caption-template-form'),name=$('caption-template-name');
  const save=$('caption-template-save'),remove=$('caption-template-delete'),retry=$('caption-template-retry');
  const state=$('caption-template-state'),error=$('caption-template-error');
  let ready=false,busy=false,snapshot=null;
  function controls(){
    save.disabled=!ready||busy||!design.savable();save.title=design.savable()?'':'기본·박스 자막을 선택하거나 색상·효과를 조절한 뒤 저장하세요.';
    remove.hidden=!design.selected();remove.disabled=busy||!ready;
    $('caption-template-submit').disabled=busy;$('caption-template-cancel').disabled=busy;name.disabled=busy;
  }
  function message(text,failed=false){state.textContent=text;state.classList.toggle('error',failed);}
  async function load(){
    busy=true;controls();
    try{const data=await api('studio-template-list',{});design.templates(data.templates);ready=true;retry.hidden=true;message('');}
    catch(e){ready=false;retry.hidden=false;message(e.message,true);}
    finally{busy=false;controls();}
  }
  retry.onclick=load;
  save.onclick=()=>{if(!design.savable()||busy)return;snapshot=design.snapshot();name.value='';error.textContent='';dialog.showModal();name.focus();};
  $('caption-template-cancel').onclick=()=>dialog.close();
  dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
  form.onsubmit=async event=>{
    event.preventDefault();if(busy)return;busy=true;controls();error.textContent='';
    try{
      const data=await api('studio-template-save',{name:name.value,design:snapshot});
      design.templates(data.templates,data.id);dialog.close();message('템플릿을 저장했습니다. 다른 영상에서도 선택할 수 있습니다.');
      document.dispatchEvent(new Event('input'));
    }catch(e){error.textContent=e.message;}
    finally{busy=false;controls();if(!dialog.open)save.focus({preventScroll:true});}
  };
  remove.onclick=async()=>{
    const chosen=design.selected();if(!chosen||busy)return;busy=true;controls();
    try{
      const data=await api('studio-template-delete',{id:chosen.id});design.templates(data.templates);
      message('템플릿을 제거했습니다. 현재 적용한 색상·효과는 유지합니다.');
      document.dispatchEvent(new Event('input'));$('caption-style').focus({preventScroll:true});
    }catch(e){retry.hidden=false;message(e.message,true);}
    finally{busy=false;controls();}
  };
  for(const kind of ['input','change'])$('inspector-font').addEventListener(kind,controls);
  controls();return {load};
}
