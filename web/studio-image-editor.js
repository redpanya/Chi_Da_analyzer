import {imageRect,imageGesture} from './studio-image-geometry.js';
const $=id=>document.getElementById(id);
export function studioImageEditor({api,identity,read,size,locked,onChange}){
  const frame=$('preview-frame'),canvas=document.createElement('canvas'),box=document.createElement('div');
  canvas.id='image-preview-canvas';canvas.setAttribute('aria-hidden','true');
  box.className='image-transform';box.hidden=true;box.setAttribute('role','group');box.setAttribute('aria-label','PNG 위치와 크기 조절');
  frame.append(canvas,box);
  let editing=false;
  let asset='',bitmap=null,aspect=1,serial=0,gesture=null,failed=false;
  const buttons=[];
  for(const [handle,label] of [['','PNG 이동'],['nw','PNG 왼쪽 위 크기 조절'],['ne','PNG 오른쪽 위 크기 조절'],['sw','PNG 왼쪽 아래 크기 조절'],['se','PNG 오른쪽 아래 크기 조절']]){
    const button=document.createElement('button');button.type='button';button.className=handle?'image-handle '+handle:'image-move';button.setAttribute('aria-label',label);button.title=label+' · 방향키로도 조절 (Shift: 크게)';
    button.dataset.handle=handle;buttons.push(button);box.append(button);
  }
  const value=()=>read().image;
  function write(next){
    for(const key of ['x','y','width'])$('image-'+key).value=next[key];
    // 슬라이더·초안 변경 감지·출력 요청이 모두 같은 값을 읽는다.
    $('image-x').dispatchEvent(new Event('input',{bubbles:true}));
  }
  function finish(cancel=false){
    if(!gesture)return;
    const old=gesture;gesture=null;box.classList.remove('dragging');
    if(old.target.hasPointerCapture(old.id))old.target.releasePointerCapture(old.id);
    if(cancel&&value()?.asset===old.start.asset)write(old.start);
  }
  function paint(){
    const o=read(),v=o.image,[w,h]=size(o);
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
    const ctx=canvas.getContext('2d');ctx.clearRect(0,0,w,h);
    const visible=Boolean(v&&bitmap&&v.asset===asset);
    box.hidden=!visible||!editing;
    $('image-drag-help').hidden=box.hidden||locked();
    if(!visible)return;
    const r=imageRect(v,{width:w,height:h},aspect);
    ctx.globalAlpha=v.opacity/100;ctx.drawImage(bitmap,r.x,r.y,r.width,r.height);ctx.globalAlpha=1;
    Object.assign(box.style,{left:100*r.x/w+'%',top:100*r.y/h+'%',width:100*r.width/w+'%',height:100*r.height/h+'%'});
    box.classList.toggle('locked',locked());for(const b of buttons)b.disabled=locked();
  }
  async function sync(){
    const next=value()?.asset||'';
    if(gesture&&(locked()||next!==asset))finish(true);
    if(next===asset){paint();return;}
    finish(true);asset=next;const request=++serial;bitmap?.close();bitmap=null;failed=false;
    $('image-preview-state').textContent=next?'PNG 미리보기 준비 중…':'';paint();
    if(!next)return;
    try{
      const result=await api('studio-image-preview',{...identity(),asset:next});
      if(request!==serial)return;
      const bytes=Uint8Array.from(atob(result.png),c=>c.charCodeAt(0));
      const loaded=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
      if(request!==serial){loaded.close();return;}
      bitmap=loaded;aspect=result.width_px/result.height_px;$('image-preview-state').textContent='';paint();
    }catch(e){if(request===serial){failed=true;$('image-preview-state').textContent='PNG 미리보기 실패 · '+e.message;}}
    finally{if(request===serial)onChange();}
  }
  box.addEventListener('pointerdown',event=>{
    const target=event.target.closest('button');if(!target||event.button!==0||!bitmap||locked()||!editing||gesture)return;
    const bounds=frame.getBoundingClientRect();if(!bounds.width||!bounds.height)return;
    event.preventDefault();target.focus({preventScroll:true});target.setPointerCapture(event.pointerId);
    gesture={id:event.pointerId,target,start:{...value()},frame:bounds,handle:target.dataset.handle,x:event.clientX,y:event.clientY};box.classList.add('dragging');
  });
  box.addEventListener('pointermove',event=>{
    if(!gesture||event.pointerId!==gesture.id)return;
    event.preventDefault();write(imageGesture(gesture.start,gesture.frame,aspect,gesture.handle,event.clientX-gesture.x,event.clientY-gesture.y));
  });
  box.addEventListener('pointerup',event=>{if(event.pointerId===gesture?.id)finish();});
  box.addEventListener('pointercancel',()=>finish(true));box.addEventListener('lostpointercapture',()=>finish(true));
  box.addEventListener('keydown',event=>{
    if(event.key==='Escape'){if(gesture){event.preventDefault();event.stopPropagation();finish(true);}return;}
    const target=event.target.closest('button'),v=value();
    if(!target||!v||locked()||!editing||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
    event.preventDefault();const change=(event.shiftKey?5:1)*(['ArrowLeft','ArrowUp'].includes(event.key)?-1:1);
    if(target.dataset.handle)write({...v,width:Math.max(1,Math.min(100,v.width+change))});
    else {const key=['ArrowLeft','ArrowRight'].includes(event.key)?'x':'y';write({...v,[key]:Math.max(0,Math.min(100,v[key]+change))});}
  });
  document.addEventListener('studio-inspector-change',event=>{if(gesture)finish(true);editing=event.detail.panel==='image';paint();});
  const observer=new ResizeObserver(()=>{finish(true);paint();});observer.observe(frame);
  window.addEventListener('blur',()=>finish(true));window.addEventListener('pagehide',()=>{finish(true);});
  return {sync,blocked:()=>Boolean(value())&&(!bitmap||failed)};
}
