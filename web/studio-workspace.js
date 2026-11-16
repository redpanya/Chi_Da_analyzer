import {bindDesktopPanels} from './desktop-panels.js';
import {animateUI,cancelMotion} from './workspace-motion.js';

export const studioSteps=['range','preset','frame','caption','export'];
export const studioStepTitles={range:'구간 다듬기',preset:'프리셋 적용',frame:'화면 꾸미기',caption:'자막 넣기',export:'저장 확인'};
export function mixMenuURL(library){
  return library?'mix-studio.html?'+new URLSearchParams({root:library}):'mix-studio.html';
}
export function setStudioMenuLinks(links,scope){
  const base='./?'+new URLSearchParams(scope);
  for(const link of links)link.href=link.dataset?.mixMenu!==undefined?mixMenuURL(scope.library_root):base+link.hash;
}
export function studioReturnLinks(project,requested='use'){
  const pages={register:'VOD 등록',library:'보관함',jobs:'진행 상태',settings:'설정',prepare:'준비',speech:'전사 자막',voices:'화자 구분',explore:'영상 재생',context:'분석',report:'작업 기록',external:'외부 AI',use:'작업'};
  const page=Object.hasOwn(pages,requested)?requested:'use';
  const scope={root:project.root,vod_id:project.vod_id};
  if(project.library_root)scope.library_root=project.library_root;
  const base='./?'+new URLSearchParams(scope);
  return {back:base+'#'+page,label:'← 이전',aria:pages[page]+' 화면으로 돌아가기',prepare:base+'#prepare'};
}
export function nextStudioStep(name,key){
  const index=studioSteps.indexOf(name);
  if(index<0)return studioSteps[0];
  if(key==='Home')return studioSteps[0];
  if(key==='End')return studioSteps.at(-1);
  const delta=['ArrowUp','ArrowLeft'].includes(key)?-1:1;
  return studioSteps[(index+delta+studioSteps.length)%studioSteps.length];
}
// 화면에 맞추는 계산만 담당한다. 출력 해상도·이미지/자막 좌표는 변경하지 않는다.
export function previewFrameGeometry(availableWidth,viewportHeight,ratio,sourceAspect=16/9){
  const parts=String(ratio).split(':').map(Number),parsed=parts[0]/parts[1];
  const aspect=ratio==='original'?sourceAspect:parsed;
  const safeAspect=Number.isFinite(aspect)&&aspect>0?aspect:16/9;
  const maxHeight=Math.min(860,Math.max(220,viewportHeight-230));
  const width=Math.max(1,Math.min(Math.max(1,availableWidth),maxHeight*safeAspect));
  return {width,height:width/safeAspect};
}

export function createStudioWorkspace({onStep}){
  const $=id=>document.getElementById(id),container=document.querySelector('.studio-grid'),panel=document.querySelector('.inspector');
  let current='range',layout=null,closed=false,closing=false;
  const bind=()=>bindDesktopPanels({container,panels:[document.querySelector('.preview-panel'),panel],key:'clip-studio-step-v2',initial:[720,320],minWidths:[400,280],flexIndex:0});
  layout=bind();
  function reveal(){
    if(closing){cancelMotion(panel);closing=false;panel.inert=false;}
    if(!closed)return;
    closed=false;panel.hidden=false;document.body.classList.remove('studio-panel-closed');layout=bind();
    animateUI(panel,[{opacity:0,transform:'translateX(20px)'},{opacity:1,transform:'translateX(0)'}],{duration:260});
  }
  function close(){
    if(closed||closing)return;
    closing=true;panel.inert=true;
    animateUI(panel,[{opacity:1,transform:'translateX(0)'},{opacity:0,transform:'translateX(18px)'}],{duration:200},()=>{
      if(!closing)return;
      closing=false;closed=true;layout?.destroy();layout=null;panel.hidden=true;panel.inert=false;document.body.classList.add('studio-panel-closed');
      document.dispatchEvent(new CustomEvent('studio-inspector-change',{detail:{tab:current,panel:''}}));
    });
    $('tab-'+current).focus({preventScroll:true});
  }
  function setStep(name){
    current=name;document.body.dataset.studioStep=name;reveal();

    $('studio-step-prev').disabled=name===studioSteps[0];$('studio-step-prev').hidden=name===studioSteps[0];$('studio-step-next').hidden=name===studioSteps.at(-1);
    for(const step of studioSteps)$('tab-'+step).setAttribute('aria-current',step===name?'step':'false');
  }
  $('studio-layout-reset').onclick=()=>{reveal();layout.reset();};
  $('studio-panel-close').onclick=close;
  $('studio-step-prev').onclick=()=>onStep(studioSteps[Math.max(0,studioSteps.indexOf(current)-1)],true);
  $('studio-step-next').onclick=()=>onStep(studioSteps[Math.min(studioSteps.length-1,studioSteps.indexOf(current)+1)],true);
  $('studio-theme-toggle').onclick=()=>window.ChidaTheme?.setPreference(window.ChidaTheme.resolved()==='dark'?'light':'dark');
  document.addEventListener('studio-close-presets',()=>onStep('range'));
  setStep(current);
  return {setStep,reveal,close};
}
