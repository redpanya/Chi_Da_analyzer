import {bindDesktopPanels} from './desktop-panels.js';

const bound=new WeakMap();
const timelines=new WeakMap();
const sharedLayouts=new WeakMap();

// 전사 결과만 두 열로 묶는다. 설정/작업 상태와 기존 전사 이벤트·교정 입력은 그대로 둔다.
export function bindSpeechResultLayout(root=document){
  const panel=root.getElementById('speech-panel'),rows=root.getElementById('transcript-rows'),search=root.getElementById('speech-search');
  if(!panel||!rows||!search)return null;
  const existing=root.getElementById('speech-results-workspace');if(existing)return existing;
  const make=(tag,id,cls)=>{const el=root.createElement(tag);el.id=id;el.className=cls;return el;};
  const workspace=make('div','speech-results-workspace','context-workspace speech-results-workspace');
  const list=make('div','speech-results-list','speech-results-list'),preview=make('div','speech-results-preview','context-preview');
  const video=make('div','speech-video','speech-video'),tools=make('div','speech-results-tools','speech-results-tools');
  const pages=root.getElementById('speech-prev')?.parentElement,follow=panel.querySelector('.speech-follow-tools');
  search.before(workspace);workspace.append(list,preview);preview.append(video);list.append(tools,rows);tools.append(search);
  if(pages)tools.append(pages);if(follow)tools.append(follow);
  bindResultLayouts(root);return workspace;
}

// 재생기와 마찬가지로 시간축도 한 DOM만 옮긴다. 선택 범위·확대·이벤트를 보존한다.
export function moveResultTimeline(targetId=null,root=document){
  let state=timelines.get(root);
  if(!state){
    const timeline=root.querySelector?.('.unified-timeline');if(!timeline)return;
    const rows=[timeline,root.getElementById('explore-notes'),root.getElementById('explore-message')].filter(Boolean);
    const slots=rows.map(node=>{const anchor=root.createElement('span');anchor.hidden=true;node.before(anchor);return {node,anchor};});
    const panel=root.createElement('details'),summary=root.createElement('summary');
    panel.className='scene-timeline';summary.textContent='공통 시간축 · 채팅 반응·AI 클립';panel.append(summary);
    state={panel,slots};timelines.set(root,state);
  }
  const target=targetId&&root.getElementById(targetId);
  if(target){
    // 댓글/담은 구간이 영상 바로 아래에 오고 시간축은 그 뒤에 둔다.
    // 탭 전환에서 공유 목록이 나중에 옮겨져도 같은 노드를 끝으로 재배치한다.
    if(target.children[target.children.length-1]!==state.panel)target.append(state.panel);
    for(const {node} of state.slots)if(node.parentElement!==state.panel)state.panel.append(node);
  }else{
    for(const {node,anchor} of state.slots)anchor.after(node);
    state.panel.remove();
  }
}

export function bindResultLayouts(root=document){
  const bindings=[];
  let shared=sharedLayouts.get(root);
  if(!shared){
    shared={bindings:new Map(),widths:null};sharedLayouts.set(root,shared);
  }
  for(const id of ['context-view-panel','context-clips-panel','speech-panel']){
    const key='scene-results';
    const container=root.getElementById(id)?.querySelector?.('.context-workspace');
    if(!container)continue;
    if(bound.has(container)){bindings.push(bound.get(container));continue;}
    const panels=Array.from(container.children).filter(child=>child.tagName==='DIV').slice(0,2);
    if(panels.length!==2)continue;
    panels[0].setAttribute('aria-label','결과 목록');panels[1].setAttribute('aria-label','영상과 활용 목록');
    const width=Math.max(620,(container.clientWidth||1010)-10);
    const binding=bindDesktopPanels({container,panels,key,initial:[width*.45,width*.55],minWidths:[320,300],flexIndex:1});
    bound.set(container,binding);bindings.push(binding);shared.bindings.set(container,binding);
    if(shared.widths)binding.apply(shared.widths);
    container.addEventListener('chida-panelresize',event=>{
      if(event.detail.key!==key)return;shared.widths=event.detail.widths;
      for(const [other,layout] of shared.bindings)if(other!==container)layout.apply(shared.widths);
    });
  }
  return bindings;
}
