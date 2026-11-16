// 편집값과 별개인 오른쪽 상세 패널 상태. 영상 영역의 너비는 바꾸지 않는다.
import {enterView} from './workspace-motion.js';
import {studioSteps} from './studio-workspace.js';
const $=id=>document.getElementById(id);
const sections={sources:['range','구간 추가'],layout:['frame','비율·화면 구성'],image:['frame','PNG 이미지'],effects:['frame','색감·효과'],volume:['frame','음량'],'caption-content':['caption','자막 내용'],'caption-appearance':['caption','글꼴·색상'],transcript:['caption','사용할 전사'],captions:['caption','자막 내용 수정'],font:['caption','자막 스타일·글꼴'],'caption-position':['caption','크기·위치']};
const parents={transcript:'caption-content',captions:'caption-content',font:'caption-appearance',effects:'layout',volume:'layout'};
// 미리보기와 같은 내용/디자인 진입점에서 실제 기능을 바로 표시한다.
const embedded={'caption-content':['transcript','captions'],'caption-appearance':['font']};
const aliases={transcript:'caption-content',captions:'caption-content',font:'caption-appearance'};
export function createStudioInspector(){
  let tab='range',active='',stack=[];
  const body=document.querySelector('.inspector-body');
  const text=(id,value)=>{if($(id)&&$(id).textContent!==value)$(id).textContent=value;};
  const option=id=>$(id).selectedOptions?.[0]?.textContent||'선택 없음';
  function update(){
    text('summary-layout',`${document.querySelector('[data-ratio][aria-pressed=true]')?.dataset.ratio==='original'?'원본':document.querySelector('[data-ratio][aria-pressed=true]')?.dataset.ratio||'원본'} · ${option('frame-layout')}`);
    text('summary-image',$('image-controls').hidden?'없음':`${$('image-name').textContent} · 너비 ${$('image-width').value}%`);
    text('summary-effects',['brightness','contrast','saturation','effect-fade'].some((id,i)=>Number($(id).value)!==[0,1,1,0][i])?'효과 조정됨':'기본값');
    text('summary-volume',$('volume').value+'%');
    text('summary-transcript',option('caption-version'));text('summary-captions',$('caption-count').textContent||'자막 준비 전');
    text('summary-style',option('caption-style')+($('caption-design-state').textContent.startsWith('맞춤')?' · 맞춤 설정':''));text('summary-font',$('font-selected').textContent||'글꼴 준비 중');
    text('summary-caption-position',`${$('caption-size').value} · ${option('caption-position')} · 가로 ${$('caption-x').value}% / 세로 ${$('caption-y').value}%`);
    const split=$('frame-layout').value==='split';$('single-fit-controls').hidden=split;$('frame-position-controls').hidden=split||$('frame-fit').value!=='cover';
    const sources=[['caption-position','caption-size-error'],['font','caption-design-error'],['font','caption-font-note'],['font','decoration-state'],['transcript','caption-load-state'],['image','image-preview-state'],['image','image-status']];
    const errors=sources.filter(([,id])=>{const value=$(id).textContent.trim();return value&&(id.endsWith('-error')||(id==='decoration-state'&&$(id).classList.contains('error'))||/실패|없습니다|못했|지원하지|확인 필요|확인되지|초과/.test(value));});
    for(const [key] of Object.entries(sections))document.querySelector(`[data-inspector-open="${key}"]`)?.classList.toggle('needs-attention',errors.some(([k])=>k===key||parents[k]===key));
    const alert=$('inspector-alert');alert.hidden=!errors.length;
    const message=errors.map(([,id])=>$(id).textContent).join(' · ');
    if(alert.dataset.message!==message){alert.dataset.message=message;alert.replaceChildren();if(errors.length){const p=document.createElement('p');p.textContent=message;const b=document.createElement('button');b.textContent='설정 확인';b.type='button';b.onclick=()=>{$('tab-'+sections[errors[0][0]][0]).click();open(errors[0][0]);};alert.append(p,b);}}
  }
  function render(direction=1){
    $('inspector-heading').hidden=!active;
    if(active)text('inspector-back',active==='sources'?'← 구간 다듬기':'← 설정 목록');
    for(const name of ['range','frame','caption'])$('overview-'+name).hidden=Boolean(active)&&sections[active][0]===name;
    const visible=new Set([active,...embedded[active]||[]]);
    for(const panel of document.querySelectorAll('[data-inspector]'))panel.hidden=!visible.has(panel.dataset.inspector);
    for(const button of document.querySelectorAll('[data-inspector-open]'))button.setAttribute('aria-expanded',String(button.dataset.inspectorOpen===active));
    if(active)text('inspector-title',sections[active][1]);
    const sample=$('caption-sample-dock');
    if(['font','caption-position','caption-appearance'].includes(active))$('inspector-'+active).prepend(sample);
    else $('overview-caption').insertBefore(sample,$('overview-caption').querySelector('.inspector-cards'));
    body.scrollTop=0;document.dispatchEvent(new CustomEvent('studio-inspector-change',{detail:{tab,panel:active}}));update();
    if(direction)enterView(body,direction);
  }
  function open(key){
    if(!sections[key])return;
    key=aliases[key]||key;
    if(active&&active!==key)stack.push(active);active=key;render();
    $('inspector-title').focus({preventScroll:true});
  }
  function close(){const previous=stack[0]||active;active='';stack=[];render(-1);document.querySelector(`[data-inspector-open="${previous}"]`)?.focus({preventScroll:true});}
  function back(){if(stack.length){const previous=active;active=stack.pop();render(-1);document.querySelector(`[data-inspector-open="${previous}"]`)?.focus({preventScroll:true});}else close();}
  for(const button of document.querySelectorAll('[data-inspector-open]'))button.onclick=()=>open(button.dataset.inspectorOpen);
  $('inspector-close').onclick=close;
  $('inspector-back').onclick=back;
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!event.defaultPrevented&&!event.isComposing&&!document.querySelector('dialog[open]')&&active){event.preventDefault();$('inspector-back').click();}});
  for(const kind of ['input','change','click'])document.addEventListener(kind,()=>queueMicrotask(update));
  const observer=new MutationObserver(update);
  for(const id of ['caption-count','caption-load-state','caption-font-note','caption-size-error','caption-design-error','caption-design-state','font-selected','image-name','image-status','decoration-state','image-preview-state'])observer.observe($(id),{childList:true,characterData:true,subtree:true});
  document.addEventListener('studio-profile-change',update);
  update();
  return {open,setTab(name,animate=true){
    const direction=name===tab?(active?-1:0):Math.sign(studioSteps.indexOf(name)-studioSteps.indexOf(tab));
    tab=name;active='';stack=[];render(animate?direction:0);
  }};
}
