import {bindDesktopPanels} from './desktop-panels.js';
import {animateUI,cancelMotion,enterView} from './workspace-motion.js';
import {bindOutsideDismiss} from './panel-dismiss.js';

export const studioSteps=['range','preset','frame','caption','export'];
export const studioStepTitles={range:'구간 고르기',preset:'프리셋 적용',frame:'화면 꾸미기',caption:'자막 넣기',export:'저장 확인'};
export function studioReturnLinks(project,requested='use'){
  const pages={register:'VOD 등록',library:'보관함',jobs:'진행 상태',settings:'설정',prepare:'준비',speech:'전사 자막',voices:'화자 구분',explore:'영상 재생',context:'분석',report:'작업 기록',external:'외부 AI',use:'작업'};
  const page=Object.hasOwn(pages,requested)?requested:'use';
  const base='./?'+new URLSearchParams({root:project.root,vod_id:project.vod_id});
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

// 기존 조립 목록을 그대로 실행하는 표시용 목록. 구간/초안 자료의 두 번째 사본은 만들지 않는다.
export function bindStudioSelection(assembly,container,count){
  const render=()=>{
    const rows=[...assembly.querySelectorAll('.assembly-select')];
    count.textContent=`담은 구간 ${rows.length}개`;container.replaceChildren();
    for(const source of rows){
      const button=document.createElement('button');button.type='button';button.className='inspector-card studio-selected-clip';
      button.setAttribute('aria-pressed',source.getAttribute('aria-pressed')||'false');
      const icon=document.createElement('span');icon.className='studio-choice-icon';icon.textContent='▷';icon.setAttribute('aria-hidden','true');
      const title=document.createElement('span');title.className='studio-choice-title';title.textContent=source.querySelector('strong')?.textContent||'담은 구간';
      const time=document.createElement('small');time.textContent=source.querySelector('small')?.textContent||'';
      const arrow=document.createElement('span');arrow.className='card-arrow';arrow.textContent='›';arrow.setAttribute('aria-hidden','true');
      button.append(icon,title,time,arrow);button.onclick=()=>source.click();container.append(button);
    }
    if(!rows.length){const empty=document.createElement('p');empty.className='small';empty.textContent='분석 구간을 선택하거나 직접 추가하세요.';container.append(empty);container.closest?.('#overview-range')?.querySelector('.studio-range-tools')?.setAttribute('open','');}
  };
  const observer=new MutationObserver(render);observer.observe(assembly,{childList:true,subtree:true,attributes:true,attributeFilter:['aria-pressed']});render();
  return {render,destroy:()=>observer.disconnect()};
}

export function createStudioWorkspace({onStep}){
  const $=id=>document.getElementById(id),container=document.querySelector('.studio-grid'),panel=document.querySelector('.inspector');
  let current='range',layout=null,closed=false,closing=false;
  const bind=()=>bindDesktopPanels({container,panels:[document.querySelector('.preview-panel'),panel],key:'clip-studio-step-v2',initial:[720,320],minWidths:[400,280],flexIndex:0});
  layout=bind();
  if($('assembly-list')?.querySelectorAll)bindStudioSelection($('assembly-list'),$('studio-selected-clips'),$('studio-selected-count'));
  function reveal(){
    if(closing){cancelMotion(panel);closing=false;panel.inert=false;}
    if(!closed)return;
    closed=false;panel.hidden=false;document.body.classList.remove('studio-panel-closed');layout=bind();
    animateUI(panel,[{opacity:0,transform:'translateX(20px)'},{opacity:1,transform:'translateX(0)'}],{duration:260});
  }
  function close(focus=true){
    if(closed||closing)return;
    closing=true;panel.inert=true;
    animateUI(panel,[{opacity:1,transform:'translateX(0)'},{opacity:0,transform:'translateX(18px)'}],{duration:200},()=>{
      if(!closing)return;
      closing=false;closed=true;layout?.destroy();layout=null;panel.hidden=true;panel.inert=false;document.body.classList.add('studio-panel-closed');
      document.dispatchEvent(new CustomEvent('studio-inspector-change',{detail:{tab:current,panel:''}}));
    });
    if(focus)$('tab-'+current).focus({preventScroll:true});
  }
  bindOutsideDismiss(panel,()=>close(false),{isOpen:()=>!closed&&!closing});
  function setStep(name){
    const previous=current;current=name;document.body.dataset.studioStep=name;reveal();

    $('studio-step-prev').disabled=name===studioSteps[0];$('studio-step-prev').hidden=name===studioSteps[0];$('studio-step-next').hidden=name===studioSteps.at(-1);
    for(const step of studioSteps)$('tab-'+step).setAttribute('aria-current',step===name?'step':'false');
    if(previous!==name)enterView(document.querySelector('.inspector-body'),studioSteps.indexOf(name)>studioSteps.indexOf(previous)?1:-1);
  }
  $('studio-layout-reset').onclick=()=>{reveal();layout.reset();};
  $('studio-panel-close').onclick=close;
  $('studio-step-prev').onclick=()=>onStep(studioSteps[Math.max(0,studioSteps.indexOf(current)-1)],true);
  $('studio-step-next').onclick=()=>onStep(studioSteps[Math.min(studioSteps.length-1,studioSteps.indexOf(current)+1)],true);
  $('studio-theme-toggle').onclick=()=>window.ChidaTheme?.setPreference(window.ChidaTheme.resolved()==='dark'?'light':'dark');
  document.addEventListener('studio-open-presets',()=>onStep('preset'));
  document.addEventListener('studio-close-presets',()=>onStep('range'));
  setStep(current);
  return {setStep,reveal,close};
}
