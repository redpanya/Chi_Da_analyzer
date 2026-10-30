// 자막은 서버와 같은 글꼴로, PNG는 즉시 조절 가능한 별도 층에 그린다.
import {studioImageEditor} from './studio-image-editor.js';
import {studioFonts} from './studio-fonts-ui.js';
const $=id=>document.getElementById(id);
export function studioDecorations({api,identity,video,read,onChange}){
  let image=null,ready=false,busy=false,uploading=false,timer=null;
  let wanted=0,sampleWanted=0,last='',sampleLast='',checked='',sampleChecked='';
  const canvas=$('decoration-canvas'),sample=$('caption-sample');
  const editor=studioImageEditor({api,identity,read,size,locked:()=>busy||uploading,onChange});
  function imageOptions(){return image?{asset:image.asset,name:image.name,...Object.fromEntries(['x','y','width','opacity'].map(k=>[k,Number($('image-'+k).value)]))}:null;}
  function controls(){
    $('image-controls').hidden=!image;$('image-name').textContent=image?image.name:'선택한 PNG가 없습니다.';
    $('image-remove').disabled=!image||busy||uploading;$('image-file').disabled=busy||uploading;
    for(const k of ['x','y','width','opacity'])$('image-'+k+'-value').textContent=$('image-'+k).value+'%';
    for(const k of ['x','y','width','opacity'])$('image-'+k).disabled=busy||uploading;
    if(ready)editor.sync();
  }
  const fonts=studioFonts({api,identity,onChange:()=>{wanted++;sampleWanted++;last=sampleLast=checked=sampleChecked='';schedule();onChange();}});
  function size(o){
    const sw=video.videoWidth||1920,sh=video.videoHeight||1080;
    const ratio=o.ratio==='original'?sw/sh:Number(o.ratio.split(':')[0])/Number(o.ratio.split(':')[1]);
    const edge=Math.min(1080,o.size==='source'?Math.min(sw,sh):Number(o.size));
    let [w,h]=ratio>=1?[edge*ratio,edge]:[edge,edge/ratio];
    const scale=Math.min(1,4096/Math.max(w,h),Math.sqrt(4_200_000/(w*h)));
    return [Math.max(2,Math.round(w*scale/2)*2),Math.max(2,Math.round(h*scale/2)*2)];
  }
  async function draw(target,payload,valid){
    const result=await api('studio-decoration-preview',{...identity(),...payload});
    if(!valid())return;
    const bytes=Uint8Array.from(atob(result.png),c=>c.charCodeAt(0));
    const bitmap=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
    if(valid()){target.width=bitmap.width;target.height=bitmap.height;target.getContext('2d').drawImage(bitmap,0,0);}
    bitmap.close();
  }
  const captionOptions=o=>Object.fromEntries(['caption','style','caption_design','font','caption_language','font_size','position','caption_x','caption_y'].map(k=>[k,o[k]]));
  function payload(o=read()){
    return {options:{...captionOptions(o),image:null},text:o.caption?$('caption-text').textContent:'',size:size(o)};
  }
  function example(o=read()){
    return {options:{...captionOptions(o),caption:true,image:null,font_size:40,caption_x:0,caption_y:0,position:'center'},text:fonts.sample(),size:[660,180]};
  }
  async function preview(){
    if(!ready)return;
    const o=read(),current=payload(o),key=JSON.stringify(current),pending=[];
    if(key!==last){
      const serial=++wanted;
      last=key;checked='';canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);
      $('decoration-state').classList.toggle('error',false);
      $('decoration-state').textContent=o.caption&&current.text.trim()?'자막 문장 렌더링 검사 중…':'';
      pending.push(draw(canvas,current,()=>serial===wanted).then(()=>{if(serial===wanted){checked=key;$('decoration-state').textContent=o.caption&&current.text.trim()?'현재 자막 문장 렌더링 확인 완료':'';}})
        .catch(e=>{if(serial===wanted){$('decoration-state').classList.toggle('error',true);$('decoration-state').textContent='이미지·자막 미리보기: '+e.message;}})
        .finally(onChange));
    }
    const samplePayload=example(o),sampleKey=JSON.stringify(samplePayload);
    if(sampleKey!==sampleLast){
      const serial=++sampleWanted;
      sampleLast=sampleKey;sampleChecked='';
      sample.getContext('2d').clearRect(0,0,sample.width,sample.height);
      $('caption-sample-status').textContent='자막 예시 확인 중…';
      $('caption-sample-status').classList.toggle('error',false);
      pending.push(draw(sample,samplePayload,()=>serial===sampleWanted)
        .then(()=>{if(serial===sampleWanted){sampleChecked=sampleKey;$('caption-sample-status').textContent='';}})
        .catch(e=>{if(serial===sampleWanted){$('caption-sample-status').classList.toggle('error',true);$('caption-sample-status').textContent='자막 예시 렌더링 실패 · '+e.message;}}).finally(onChange));
    }
    await Promise.all(pending);
  }
  function schedule(){
    if(!ready)return;
    editor.sync();
    // 전사 모듈이 같은 대사를 다시 통지해도 진행 중인 동일 요청을 무효화하지 않는다.
    clearTimeout(timer);timer=setTimeout(preview,100);
  }
  $('image-file').onchange=async()=>{
    const file=$('image-file').files?.[0];if(!file)return;
    uploading=true;controls();$('image-status').textContent='PNG를 편집용으로 준비하고 있습니다…';onChange();
    try{
      if(file.size>10*1024**2)throw new Error('PNG는 10MB 이하로 선택하세요.');
      const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(new Error('파일을 읽지 못했습니다.'));reader.onload=()=>resolve(reader.result);reader.readAsDataURL(file);});
      image=await api('studio-image-add',{...identity(),png:String(data).split(',')[1],name:file.name});
      for(const [k,v] of Object.entries({x:50,y:50,width:30,opacity:100}))$('image-'+k).value=v;
      $('image-status').textContent=`${image.width_px} × ${image.height_px}px · 전체 선택 구간에 적용됩니다.`;
    }catch(e){$('image-status').textContent='PNG 준비 실패 · '+e.message;}
    finally{uploading=false;$('image-file').value='';controls();schedule();onChange();}
  };
  $('image-remove').onclick=()=>{image=null;$('image-status').textContent='현재 편집에서 제거했습니다.';controls();schedule();onChange();};
  document.addEventListener('input',()=>{controls();schedule();});
  document.addEventListener('change',schedule);
  document.addEventListener('click',schedule);
  let textLast='';new MutationObserver(()=>{const text=$('caption-text').textContent;if(text!==textLast){textLast=text;schedule();}}).observe($('caption-text'),{childList:true,characterData:true,subtree:true});
  video.addEventListener('loadedmetadata',schedule);
  window.addEventListener('pagehide',()=>{clearTimeout(timer);wanted++;sampleWanted++;sampleLast='';});
  window.addEventListener('pageshow',()=>{last=sampleLast='';schedule();});
  return {imageOptions,blocked:()=>uploading||editor.blocked()||((read().caption||(read().sidecar&&$('caption-version').value))&&fonts.blocked())||
      (read().caption&&(checked!==JSON.stringify(payload())||sampleChecked!==JSON.stringify(example()))),
    busy(value){busy=value;controls();},async init(options={}){
      await fonts.init(options);image=options.image||null;
      if(image)for(const k of ['x','y','width','opacity'])$('image-'+k).value=image[k];
      controls();ready=true;schedule();
    }};
}
