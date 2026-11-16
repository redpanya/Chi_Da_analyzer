// 하나의 재생 시계를 사용해 게임/얼굴 두 영역을 그린다.
import {animateUI,cancelMotion,reducedMotion} from './workspace-motion.js';
import {frameErrors} from './studio-frame-validation.js';
export function createFramePreview(video,read,canDraw){
  const canvas=document.createElement('canvas');canvas.id='render-preview';video.after(canvas);
  const message=document.getElementById('media-empty');
  const source=document.createElement('canvas');source.id='crop-source';source.width=480;source.height=270;
  document.getElementById('split-controls').append(source);
  let frame=null,last='',running=false;
  let guides=[],previous=null,awaitingFrame=false;
  function clearPrevious(){
    awaitingFrame=false;
    if(previous){cancelMotion(previous);previous.remove();previous=null;}
  }
  function holdFrame(){
    if(!last||reducedMotion?.matches)return;
    if(!previous){
      previous=document.createElement('canvas');previous.className='mix-previous-frame';previous.setAttribute('aria-hidden','true');
      previous.width=canvas.width;previous.height=canvas.height;
      const ctx=previous.getContext('2d');
      ctx.filter=canvas.style.filter||'none';ctx.drawImage(canvas,0,0);ctx.filter='none';
      for(const id of ['image-preview-canvas','decoration-canvas']){
        const layer=document.getElementById(id);
        if(layer?.width&&layer.height)ctx.drawImage(layer,0,0,previous.width,previous.height);
      }
      document.getElementById('preview-stage').append(previous);
    }else{
      previous.style.opacity=getComputedStyle(previous).opacity;
      cancelMotion(previous);
    }
    awaitingFrame=true;last='';
  }
  function guideColors(){const theme=getComputedStyle(document.documentElement);guides=[['game',theme.getPropertyValue('--ds-chart-chat').trim()||'#00FFA3'],['face',theme.getPropertyValue('--ds-chart-clip').trim()||'#A99DFF']];last='';}
  guideColors();document.addEventListener('chida-themechange',guideColors);
  function draw(){
    if(!running)return;frame=requestAnimationFrame(draw);
    if(canDraw()&&!video.error&&video.readyState>=2&&!video.seeking){
      const o=read(),sw=video.videoWidth,sh=video.videoHeight,ratio=o.ratio==='original'?sw/sh:Number(o.ratio.split(':')[0])/Number(o.ratio.split(':')[1]);
      if(!sw||!sh||!Number.isFinite(ratio)||ratio<=0)return;
      const invalid=frameErrors(o,sw,sh);
      const safe=key=>invalid[key]?[0,0,100,100]:o[key];
      const key=JSON.stringify([video.currentTime,sw,sh,o]);if(video.paused&&key===last)return;
      const w=540,h=Math.round(w/ratio);if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
      const ctx=canvas.getContext('2d');ctx.fillStyle='black';ctx.fillRect(0,0,w,h);
      function region(rect,dy,dh,fit,x=50,y=50){
        let [sx,sy,rw,rh]=rect.map((v,i)=>v*(i%2?sh:sw)/100);
        let dw=w,hh=dh,dx=0;
        if(fit==='contain'){const scale=Math.min(w/rw,dh/rh);dw=rw*scale;hh=rh*scale;dx=(w-dw)/2;dy+=(dh-hh)/2;}
        else{const r=w/dh;if(rw/rh>r){const width=rh*r;sx+=(rw-width)*x/100;rw=width;}else{const height=rw/r;sy+=(rh-height)*y/100;rh=height;}}
        ctx.drawImage(video,sx,sy,rw,rh,dx,dy,dw,hh);
      }
      if(o.layout==='split'){const split=h*o.split/100;region(safe('game'),0,split,'cover');region(safe('face'),split,h-split,'cover');}
      else region([0,0,100,100],0,h,o.fit,o.x,o.y);
      canvas.style.filter=`brightness(${1+o.brightness}) contrast(${o.contrast}) saturate(${o.saturation})`;
      last=key;
      if(!message.hidden)message.hidden=true;
      if(awaitingFrame){
        awaitingFrame=false;
        animateUI(previous,[{opacity:previous.style.opacity||1},{opacity:0}],{duration:180},clearPrevious);
      }
      if(o.layout==='split'){
        source.height=Math.round(source.width*sh/sw);const g=source.getContext('2d');g.drawImage(video,0,0,source.width,source.height);g.lineWidth=3;
        for(const [key,color] of guides){g.strokeStyle=color;const r=o[key];g.strokeRect(r[0]*source.width/100,r[1]*source.height/100,r[2]*source.width/100,r[3]*source.height/100);}
      }
    }
  }
  function start(){if(running)return;running=true;last='';draw();}
  video.addEventListener('loadeddata',()=>{last='';});
  video.addEventListener('error',clearPrevious);
  window.addEventListener('pagehide',()=>{clearPrevious();running=false;cancelAnimationFrame(frame);frame=null;});
  window.addEventListener('pageshow',start);start();
  return {holdFrame};
}
