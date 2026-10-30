// 편집값과 별개인 오른쪽 상세 패널 상태. 영상 영역의 너비는 바꾸지 않는다.
const $=id=>document.getElementById(id);
const sections={layout:['frame','비율·화면 구성'],image:['frame','PNG 이미지'],effects:['frame','색감·효과'],volume:['frame','음량'],transcript:['caption','사용할 전사'],captions:['caption','자막 내용 수정'],font:['caption','자막 스타일·글꼴'],'caption-position':['caption','크기·위치']};
const hints={
  layout:['전체 보이기는 원본 전체를, 화면 채우기는 선택한 위치를 확대해 보여줍니다.','세로 2단은 원본의 게임·얼굴 영역을 나눠 배치합니다. 자동 추적은 하지 않습니다.'],
  image:['PNG 한 장을 모든 담은 구간에 공통으로 올립니다. 자막은 이미지 위에 표시합니다.','이 패널에서 영상 위 PNG를 끌거나 모서리로 크기를 조절할 수 있습니다. 닫아도 이미지는 유지됩니다.'],
  effects:['밝기·대비·채도는 미리보기에 즉시 적용합니다. 시작·끝 페이드는 저장 영상에 반영됩니다.'],
  volume:['저장할 영상의 음량입니다. 가운데 플레이어의 소리 켜짐·꺼짐은 미리보기만 조절합니다.'],
  transcript:['완료된 전사를 선택합니다. 원전사·화자 배정은 변경하지 않습니다.'],
  captions:['시간 버튼을 누르면 해당 자막의 영상 시각부터 재생합니다.','담은 구간의 문장만 표시합니다. 교정은 이 편집 초안에만 저장하며 전사 버전마다 따로 보존합니다.'],
  font:['기본 자막·박스 자막을 고르고 색상·효과를 직접 조절할 수 있습니다. 템플릿을 다시 선택하면 저장한 색상·효과로 돌아가며 글꼴·굵기는 유지합니다.','색상·효과 영역 아래의 템플릿 저장을 누르고 이름을 입력하면 다른 영상에서도 사용할 수 있습니다. 글꼴·크기·위치는 포함하지 않습니다.','내 템플릿을 선택하면 제거 버튼이 나타납니다. 제거해도 현재 적용한 디자인과 저장한 초안·출력 영상은 바뀌지 않습니다.','효과 두께·거리·여백은 글자 크기 22 기준으로 비례합니다. 외곽선·그림자·박스는 화면 경계에서 잘릴 수 있습니다.','글꼴 예시를 눌러 선택하고 설치된 굵기·스타일을 고르세요. 선택 언어를 지원하는 글꼴만 표시합니다.','실제 문장에 없는 글자가 있거나 렌더링에 실패하면 저장 전 안내합니다. 설치 글꼴의 사용 범위는 해당 라이선스를 확인하세요.'],
  'caption-position':['글자 크기는 슬라이더 또는 숫자로 14~40 사이의 정수만 지정합니다. 이전 초안의 소수 크기는 가장 가까운 정수로 적용하고, 저장할 때 반영합니다.','가로·세로 미세 조정은 화면 크기 기준 %입니다. 오른쪽·아래가 + 방향이며 화면 밖 글자는 잘릴 수 있습니다.'],
};
export function createStudioInspector(){
  let tab='range',active='',help=false;
  const body=document.querySelector('.inspector-body');
  const text=(id,value)=>{if($(id).textContent!==value)$(id).textContent=value;};
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
    for(const [key] of Object.entries(sections))document.querySelector(`[data-inspector-open="${key}"]`).classList.toggle('needs-attention',errors.some(([k])=>k===key));
    const alert=$('inspector-alert');alert.hidden=!errors.length;
    const message=errors.map(([,id])=>$(id).textContent).join(' · ');
    if(alert.dataset.message!==message){alert.dataset.message=message;alert.replaceChildren();if(errors.length){const p=document.createElement('p');p.textContent=message;const b=document.createElement('button');b.textContent='설정 확인';b.type='button';b.onclick=()=>{$('tab-'+sections[errors[0][0]][0]).click();open(errors[0][0]);};alert.append(p,b);}}
  }
  function render(){
    $('inspector-heading').hidden=!active;
    for(const name of ['frame','caption'])$('overview-'+name).hidden=Boolean(active)&&sections[active][0]===name;
    for(const panel of document.querySelectorAll('[data-inspector]'))panel.hidden=panel.dataset.inspector!==active||help;
    for(const button of document.querySelectorAll('[data-inspector-open]'))button.setAttribute('aria-expanded',String(button.dataset.inspectorOpen===active));
    $('inspector-help-content').hidden=!help;
    if(active)text('inspector-title',help?sections[active][1]+' 도움말':sections[active][1]);
    $('inspector-help').hidden=help;
    const sample=$('caption-sample-dock');
    if(['font','caption-position'].includes(active)&&!help)$('inspector-'+active).prepend(sample);
    else $('overview-caption').insertBefore(sample,$('overview-caption').querySelector('.inspector-cards'));
    body.scrollTop=0;document.dispatchEvent(new CustomEvent('studio-inspector-change',{detail:{tab,panel:help?'':active}}));update();
  }
  function open(key){active=key;help=false;render();$('inspector-title').focus({preventScroll:true});}
  function close(){const previous=active;active='';help=false;render();document.querySelector(`[data-inspector-open="${previous}"]`)?.focus({preventScroll:true});}
  for(const button of document.querySelectorAll('[data-inspector-open]'))button.onclick=()=>open(button.dataset.inspectorOpen);
  $('inspector-close').onclick=close;
  $('inspector-back').onclick=()=>{if(help){help=false;render();$('inspector-title').focus({preventScroll:true});}else close();};
  $('inspector-help').onclick=()=>{if(!active)return;help=true;$('inspector-help-content').replaceChildren(...hints[active].map(line=>{const p=document.createElement('p');p.textContent=line;return p;}));render();$('inspector-title').focus({preventScroll:true});};
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!event.defaultPrevented&&!event.isComposing&&!document.querySelector('dialog[open]')&&active){event.preventDefault();$('inspector-back').click();}});
  for(const kind of ['input','change','click'])document.addEventListener(kind,()=>queueMicrotask(update));
  const observer=new MutationObserver(update);
  for(const id of ['caption-count','caption-load-state','caption-font-note','caption-size-error','caption-design-error','caption-design-state','font-selected','image-name','image-status','decoration-state','image-preview-state'])observer.observe($(id),{childList:true,characterData:true,subtree:true});
  update();
  return {setTab(name){tab=name;active='';help=false;render();}};
}
