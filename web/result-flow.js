import {bindSpeechResultLayout} from './results-layout.js';
import {enterView,animateUI,cancelMotion} from './workspace-motion.js';
import {bindOutsideDismiss} from './panel-dismiss.js';

export const resultModes=['transcript','detail','timestamps','clips'];
const labels={transcript:'전사 자막',detail:'상세 문맥',timestamps:'타임스탬프',clips:'클립 후보'};
const priority=['clips','timestamps','detail','transcript'];
const drawers=new WeakMap();

// 결과 설정·근거·댓글 편집은 같은 오른쪽 영역을 쓴다. 노드를 복제하거나 값을 저장하지 않는다.
export function resultDrawer(root=document){
  if(drawers.has(root))return drawers.get(root);
  const make=(tag,text='',cls='')=>{const el=root.createElement(tag);el.textContent=text;el.className=cls;return el;};
  const dialog=make('dialog','','result-drawer'),header=make('header','','result-drawer-header'),heading=make('h2'),close=make('button','×','result-drawer-close');
  dialog.id='result-drawer';heading.id='result-drawer-title';heading.tabIndex=-1;dialog.setAttribute('aria-labelledby',heading.id);
  close.type='button';close.setAttribute('aria-label','결과 패널 닫기');header.append(heading,close);
  const context=make('p','','result-drawer-context'),body=make('div','','result-drawer-body');dialog.append(header,context,body);
  (root.body||root.getElementById('analysis-results-nav')).append(dialog);
  let slots=[],trigger=null,closed=null,kind=null,key=null;
  function dismiss({focus=true}={}){
    if(!kind)return;cancelMotion(body);cancelMotion(dialog);dialog.inert=false;const done=closed,opener=trigger;closed=null;trigger=null;kind=null;key=null;
    if(dialog.open)dialog.close();
    for(const {node,anchor,hidden} of slots){if(anchor.isConnected!==false&&anchor.parentElement){anchor.before(node);node.hidden=hidden;}else node.remove();anchor.remove();}slots=[];
    delete root.body?.dataset?.resultDrawer;done?.();
    if(focus&&opener?.isConnected!==false&&opener?.getClientRects?.().length)opener.focus({preventScroll:true});
  }
  function closeAnimated(focus=true){if(!kind||dialog.inert)return;dialog.inert=true;animateUI(dialog,[{opacity:1,transform:'translateX(0)'},{opacity:0,transform:'translateX(20px)'}],{duration:180},()=>dismiss({focus}));}
  bindOutsideDismiss(dialog,()=>closeAnimated(false),{root});
  close.onclick=closeAnimated;dialog.addEventListener('cancel',event=>{event.preventDefault();closeAnimated();});
  dialog.addEventListener('close',()=>{if(!dialog.open)dismiss();});
  dialog.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();closeAnimated();}});
  const api={
    open({title,subtitle='',nodes,opener,type='scene',onClose,itemKey=null,restoreFocus=false}){
      const focused=restoreFocus?root.activeElement:null,focusKey=focused?.dataset?.draftKey||focused?.dataset?.reviewMemo||focused?.dataset?.reviewKey;
      const caret=focusKey?[focused.selectionStart,focused.selectionEnd]:null;
      dismiss({focus:false});if(root.querySelector?.('dialog[open]'))return false;
      heading.textContent=title;context.textContent=subtitle;context.hidden=!subtitle;trigger=opener;closed=onClose;kind=type;key=itemKey;
      for(const node of nodes){const anchor=make('span');anchor.hidden=true;node.before(anchor);slots.push({node,anchor,hidden:node.hidden});node.hidden=false;body.append(node);}
      if(root.body)root.body.dataset.resultDrawer='open';dialog.show();if(!restoreFocus){animateUI(dialog,[{opacity:0,transform:'translateX(24px)'},{opacity:1,transform:'translateX(0)'}],{duration:280});heading.focus();}
      if(focusKey){const field=[...body.querySelectorAll('input,textarea,select')].find(el=>(el.dataset.draftKey||el.dataset.reviewMemo||el.dataset.reviewKey)===focusKey);field?.focus({preventScroll:true});if(Number.isInteger(caret[0]))field?.setSelectionRange?.(...caret);}
      return true;
    },
    close(type){if(!type||kind===type)dismiss();},
    kind:()=>kind,
    key:()=>key,
    sync(){if(kind==='scene'&&slots.some(({anchor})=>anchor.isConnected===false))dismiss({focus:false});},
    dialog,
  };drawers.set(root,api);return api;
}
export function closeResultDrawer(type,root=document){drawers.get(root)?.close(type);}

export function bindSceneDetails(card,details,{title,subtitle='',actions=[],key=null,label='내용근거'}={}){
  const button=document.createElement('button');button.type='button';button.className='secondary scene-more';button.setAttribute('aria-label',title+' 내용근거 보기');
  button.textContent=label;
  if(actions.length){const bar=document.createElement('div');bar.className='play-actions scene-detail-actions';bar.append(...actions);details.append(bar);}
  const bar=document.createElement('div');bar.className='play-actions scene-actions';
  const selection=Array.from(card.children).find(node=>node.className?.split(' ').includes('scene-selection-button'));if(selection)bar.append(selection);
  bar.append(button);details.hidden=true;card.append(bar,details);
  const open=restoreFocus=>{details.open=true;resultDrawer().open({title,subtitle,nodes:[details],opener:button,type:'scene',itemKey:key,restoreFocus});};
  button.onclick=()=>open(false);
  // 폴링/검토 변경으로 같은 행을 다시 그려도 열린 패널과 교정 커서를 유지한다.
  if(key&&drawers.get(document)?.key()===key)queueMicrotask(()=>{if(drawers.get(document)?.key()===key&&card.isConnected!==false)open(true);});
  return button;
}
export function syncSceneDrawer(){queueMicrotask(()=>drawers.get(document)?.sync());}

// 서버가 돌려준 버전 목록만 읽는다. 모델 준비/영상 유무를 결과 유무로 추측하지 않는다.
export function availableResultModes(project){
  const runs=project?.context?.runs||[];
  const speech=project?.speech;
  const transcripts=speech?.versions||project?.context?.inputs?.transcripts||[];
  const readable=row=>!!row?.id&&(row.segment_count==null||Number(row.segment_count)>0);
  const hasTranscript=transcripts.some(readable)||readable(speech?.transcript);
  return resultModes.filter(mode=>mode==='transcript'?hasTranscript:runs.some(row=>row?.id&&(row.mode||'detail')===mode));
}
export function preferredResultMode(project,preferred){
  const available=availableResultModes(project);
  return available.includes(preferred)?preferred:priority.find(mode=>available.includes(mode))||null;
}

// 승인 미리보기처럼 버전·삭제·필터는 오른쪽 패널에서 바꾼다.
export function bindResultTools(host,{root=document,getMode,getProject}){
  const make=(tag,text,cls='')=>{const el=root.createElement(tag);el.textContent=text||'';el.className=cls;return el;};
  const actions=make('div','','result-primary-actions'),settings=make('button','결과 설정','secondary');
  settings.type='button';settings.setAttribute('aria-expanded','false');actions.append(settings);host.append(actions);
  const groups=new Map();
  for(const [mode,panelId,startId,readyId] of [['transcript','speech-panel','speech-new','speech-readiness'],['detail','context-view-panel','context-new','context-readiness'],['clips','context-clips-panel','clips-new','clips-readiness']]){
    const panel=root.getElementById(panelId),toolbar=panel?.querySelector(':scope > .result-toolbar');if(!toolbar)continue;
    const box=make('section','','result-options');box.id='result-options-'+mode;box.hidden=true;
    host.append(box);box.append(toolbar);const ready=root.getElementById(readyId);if(ready)box.append(ready);
    const launch=root.getElementById(startId);if(launch){(mode==='transcript'?box:actions).append(launch);launch.hidden=true;launch.textContent=mode==='transcript'?'＋ 새 전사':'＋ 새 분석';}
    const history=root.getElementById(mode==='clips'?'clips-job-history':mode==='detail'?'context-job-history':'');
    if(history)box.append(history);
    const notices={transcript:['speech-notice','speech-result-status'],detail:['context-notice','context-result-state'],clips:['context-clips-notice','context-clips-status','context-clips-guidance']};
    for(const id of notices[mode]){const notice=root.getElementById(id);if(notice)box.append(notice);}
    groups.set(mode,{box,launch});
  }
  let current=null;
  const group=()=>groups.get(getMode()==='timestamps'?'detail':getMode());
  settings.setAttribute('aria-haspopup','dialog');settings.setAttribute('aria-controls','result-drawer');
  settings.onclick=()=>{const active=group();if(active)resultDrawer(root).open({title:'결과 설정',subtitle:labels[getMode()]+' · '+(getProject()?.metadata?.title||''),nodes:[active.box],opener:settings,type:'settings',onClose:()=>settings.setAttribute('aria-expanded','false')});settings.setAttribute('aria-expanded',String(resultDrawer(root).kind()==='settings'));};
  function update(){
    const active=group();if(active!==current){closeResultDrawer('settings',root);current=active;}
    const primary=groups.get(getMode()==='clips'?'clips':'detail');
    for(const [mode,{box,launch}] of groups)if(launch){launch.hidden=!getProject()||(mode==='transcript'?box!==active?.box:launch!==primary?.launch);if(launch.disabled)launch.title='현재 작업 상태에서는 시작할 수 없습니다. 진행·대기 작업과 준비 상태를 확인하세요.';else launch.title=mode==='transcript'?'전사 설정과 처리 범위를 선택합니다.':'분석 종류와 사용할 자료를 선택합니다.';}
    settings.disabled=!active;
  }
  return {update};
}

// 전사/문맥 기존 화면을 공통 탐색막대로 연결한다. 결과 노드·입력·현재 버전은 복제하지 않는다.
export function createResultNavigation({getProject,navigate,context,root=document}){
  const make=(tag,text='')=>{const el=root.createElement(tag);el.textContent=text;return el;};
  const host=make('section');host.id='analysis-results-nav';host.className='analysis-results-nav';host.hidden=true;
  const tabs=make('div');tabs.className='review-tabs result-mode-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','분석 결과 종류');
  const empty=make('p','저장된 결과가 없습니다. 새 분석에서 시작하세요.');empty.className='hint result-navigation-empty';
  host.append(tabs,empty);
  const anchor=root.getElementById('speech-panel');anchor.before(host);anchor.setAttribute('role','tabpanel');anchor.setAttribute('aria-labelledby','result-tab-transcript');
  const legacy=root.getElementById('context-panel')?.querySelector(':scope > .review-tabs');if(legacy)legacy.hidden=true;
  bindSpeechResultLayout(root);
  const buttons=new Map(),remembered=new Map();let path=null,step=0,active=null,transitioning=false;
  const tools=bindResultTools(host,{root,getMode:()=>active,getProject});
  function syncProject(){
    const project=getProject();if(path!==project?.path){closeResultDrawer(null,root);path=project?.path||null;active=preferredResultMode(project,remembered.get(path));}
    return project;
  }
  function paint(){
    const project=syncProject(),available=availableResultModes(project);
    host.hidden=![3,6].includes(step)||!!root.body?.dataset?.usePage||!!root.body?.dataset?.taskFlow;empty.hidden=available.length>0;
    if(host.hidden)closeResultDrawer(null,root);
    const focusMode=available.includes(active)?active:preferredResultMode(project);
    for(const [mode,button] of buttons){
      button.disabled=!available.includes(mode);button.setAttribute('aria-selected',String(mode===active));
      button.tabIndex=mode===focusMode?0:-1;button.title=button.disabled?'저장된 '+labels[mode]+' 결과가 없습니다.':labels[mode]+' 결과 보기';
    }
    tools.update();
  }
  function choose(mode,{remember=true,changePage=true}={}){
    const project=syncProject();if(!availableResultModes(project).includes(mode))return false;
    const target=mode==='transcript'?3:6,withinPage=step===target&&!host.hidden;
    const previous=active;
    if(changePage&&withinPage&&previous===mode)return true;
    if(previous!==mode)closeResultDrawer(null,root);active=mode;if(remember&&path)remembered.set(path,mode);
    transitioning=true;
    try{
      if(mode!=='transcript')context.selectMode(mode);
      if(changePage)navigate(target);
      context.mountUsage?.(mode==='transcript'?'speech-results-preview':mode==='clips'?'context-clips-preview':'context-preview');
    }finally{transitioning=false;}
    paint();
    if(changePage&&withinPage&&previous!==mode){const panel=root.getElementById(mode==='clips'?'context-clips-panel':'context-view-panel');enterView(panel,resultModes.indexOf(mode)<resultModes.indexOf(previous)?-1:1);}
    return true;
  }
  for(const mode of resultModes){
    const button=make('button',labels[mode]);button.id='result-tab-'+mode;button.type='button';button.setAttribute('role','tab');
    button.setAttribute('aria-controls',mode==='transcript'?'speech-panel':mode==='clips'?'context-clips-panel':'context-view-panel');
    button.onclick=()=>choose(mode);
    button.onkeydown=event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();
      const available=availableResultModes(getProject());if(!available.length)return;
      const index=available.indexOf(mode),next=event.key==='Home'?available[0]:event.key==='End'?available.at(-1):available[(index+(event.key==='ArrowRight'?1:available.length-1))%available.length];
      if(choose(next))buttons.get(next).focus();
    };
    tabs.append(button);buttons.set(mode,button);
  }
  root.addEventListener('context-mode-change',event=>{
    if(transitioning||step!==6)return;
    const mode=event.detail?.mode;if(!availableResultModes(getProject()).includes(mode))return;
    active=mode;if(path)remembered.set(path,mode);paint();
  });
  return {
    update:paint,
    enter(mode){const project=syncProject(),chosen=preferredResultMode(project,mode||active);if(chosen)return choose(chosen);navigate(6);return false;},
    navigate(value,{use=false}={}){
      if(step!==value)closeResultDrawer(null,root);
      step=value;const project=syncProject();
      if(step===3){active='transcript';if(availableResultModes(project).includes(active)&&path)remembered.set(path,active);context.mountUsage?.('speech-results-preview');}
      else if(step===6&&!use&&!transitioning){
        const chosen=preferredResultMode(project,active);
        if(chosen==='transcript'){choose(chosen,{remember:false});return;}
        if(chosen)choose(chosen,{remember:false,changePage:false});
      }
      paint();
    },
    mode:()=>active,
  };
}
