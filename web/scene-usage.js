import {collectRanges,sortedRanges} from './clip-studio-model.js';
import {timecode} from './player.js';
import {resultDrawer,closeResultDrawer} from './result-flow.js';
import {enterView} from './workspace-motion.js';

// 편집기와 같은 ID·VOD 절대 시각 계약을 쓴다. 기존 수동 편집은 깊은 복사로 유지한다.
export function prepareBasketAdd({result,run,indices,project,draft}){
  if(result.stale)throw Error('현재 입력과 다른 이전 결과입니다. 영상·분석 버전을 확인하세요.');
  const origin=Number(project.input?.start_vod_ms)||0;
  const duration=Math.round((project.tasks?.video?.verification?.duration||project.metadata?.duration||0)*1000);
  const ranges=collectRanges(result,run,origin,duration).rows;
  const request=structuredClone(draft?.request||{clips:[]}),existing=new Set(request.clips.map(row=>row.id));
  let added=0;
  for(const index of [...new Set(indices)]){
    const id=JSON.stringify([run,index]),row=ranges.find(row=>row.id===id);
    if(!row||row.end_ms-row.start_ms<100)throw Error('저장 영상 안의 0.1초 이상 구간만 담을 수 있습니다.');
    if(existing.has(id))continue;
    request.clips.push({id,title:row.title,start_ms:row.start_ms,end_ms:row.end_ms});existing.add(id);added++;
  }
  if(request.clips.length>100)throw Error('담은 구간은 최대 100개입니다. 클립 만들기에서 목록을 정리하세요.');
  request.clips=sortedRanges(request.clips);
  return {request,revision:draft?.revision||0,added};
}

export function createSceneUsage({api,player,comments,onOpenEditor}){
  const node=(tag,text='')=>{const el=document.createElement(tag);el.textContent=text;return el;};
  const panel=node('section');panel.className='scene-usage';
  panel.setAttribute('aria-label','선택 구간 활용');
  const tabs=node('div');tabs.className='review-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','결과 활용');
  const commentTab=node('button','댓글 목록'),basketTab=node('button','담은 클립');
  for(const button of [commentTab,basketTab]){button.type='button';button.setAttribute('role','tab');tabs.append(button);}
  const basket=node('section');basket.className='scene-clip-basket';
  const actions=node('div');actions.className='play-actions';
  const reload=node('button','다시 불러오기'),editor=node('button','클립 편집기 열기');
  reload.type=editor.type='button';reload.className='subtle';editor.className='secondary';actions.append(reload,editor);
  const list=node('div'),notice=node('p');notice.className='hint';notice.setAttribute('role','status');
  // ID로 댓글 자식 노드를 찾는 기존 처리보다 먼저 문서에 연결한다.
  // 분리된 panel에 먼저 옮기면 첫 VOD를 여는 동안 getElementById가 null이 된다.
  comments.before(panel);
  const summary=node('section');summary.className='scene-comment-selection';
  const selectedList=node('div');selectedList.className='scene-selection-list';selectedList.setAttribute('aria-label','선택한 댓글 구간');
  const commentActions=node('div');commentActions.className='play-actions';
  const editComments=node('button','댓글 다듬기');editComments.type='button';editComments.className='secondary';
  for(const id of ['context-copy','context-list-play']){const control=document.getElementById(id);if(control)commentActions.append(control);}
  const count=document.getElementById('context-copy-count');if(count)summary.append(count);
  summary.append(selectedList,commentActions,editComments);
  // 저장·충돌 안내와 복사 실패 대체 입력은 패널 밖에도 항상 보인다.
  for(const id of ['context-draft-state','context-comment-retry','context-comment-reload','context-list-playing','context-copy-fallback','context-copy-notice']){const control=document.getElementById(id);if(control)summary.append(control);}
  list.className='scene-clip-list';basket.append(actions,list);panel.append(tabs,notice,summary,comments,basket);comments.hidden=true;
  let project=null,draft=null,mode='comments',generation=0,loadId=0,busy=false,reading=false,commentSnapshot={scope:null,blocked:true,rows:[]};
  const identity=()=>({root:project.root,vod_id:project.vod_id});
  function syncSelection(){
    for(const input of document.querySelectorAll?.('.scene-selection-button')||[])input.sceneUpdate?.();
  }
  function render(){
    syncSelection();
    summary.hidden=mode!=='comments';basket.hidden=mode!=='clips';
    commentTab.setAttribute('aria-selected',String(mode==='comments'));basketTab.setAttribute('aria-selected',String(mode==='clips'));
    commentTab.tabIndex=mode==='comments'?0:-1;basketTab.tabIndex=mode==='clips'?0:-1;
    basketTab.textContent='담은 클립'+(draft?` ${draft.request.clips.length}`:'');
    reload.disabled=!project||busy;editor.disabled=!project;
    editComments.disabled=commentSnapshot.blocked||!commentSnapshot.rows.length;
    list.replaceChildren();
    const rows=draft?.request?.clips||[],origin=Number(project?.input?.start_vod_ms)||0;
    if(!rows.length)list.append(node('p',draft?'담은 구간이 없습니다. 후보에서 클립에 담기를 누르세요.':'저장된 편집 초안을 불러오세요.'));
    for(const row of rows){
      const item=node('article'),play=node('button'),clock=node('time',timecode(row.start_ms)),title=node('span',row.title);play.append(clock,title);play.type='button';play.className='subtle scene-basket-play';play.title=row.title;
      play.disabled=project?.tasks?.video?.state!=='complete';
      play.onclick=()=>player.seek(row.start_ms-origin,true,row.end_ms-origin);
      const remove=node('button','×');remove.type='button';remove.className='scene-selected-remove';remove.setAttribute('aria-label',row.title+' 클립에서 제거');remove.disabled=busy||project?.locked;remove.onclick=()=>mutateClip({id:row.id},false);
      item.append(play,remove,node('small',`${timecode(row.end_ms-row.start_ms)} · ${row.options?'개별 화면·자막 설정':'공통 화면·자막 설정'}`));list.append(item);
    }
  }
  function updateComments(value){
    if(value.scope!==commentSnapshot.scope)closeResultDrawer('comments');commentSnapshot=value;
    selectedList.replaceChildren();
    for(const row of value.rows){
      const item=node('div');item.className='scene-selected-row';
      const play=node('button');play.className='scene-selected-copy';play.type='button';play.append(node('time',row.time),node('span',row.title));play.title=row.title;play.disabled=value.blocked||!row.playable;play.onclick=row.play;
      const remove=node('button','×');remove.className='scene-selected-remove';remove.type='button';remove.disabled=value.blocked;remove.setAttribute('aria-label',row.time+' 댓글에서 제거');remove.onclick=row.remove;item.append(play,remove);selectedList.append(item);
    }
    if(!value.rows.length)selectedList.append(node('p','목록에서 댓글에 포함할 구간을 선택하세요.'));
    editComments.disabled=value.blocked||!value.rows.length;syncSelection();
  }
  editComments.onclick=()=>resultDrawer().open({title:'댓글 다듬기',subtitle:project?.metadata?.title||'',nodes:[comments],opener:editComments,type:'comments'});
  async function load(){
    if(!project||busy||reading)return;reading=true;
    const token=generation,ticket=++loadId,target=identity();notice.textContent='담은 클립을 불러오는 중…';
    try{const value=await api('studio-info',target);if(token!==generation||ticket!==loadId)return;draft=value.draft||{revision:0,request:{clips:[]}};notice.textContent='';render();}
    catch(error){if(token===generation&&ticket===loadId)notice.textContent='클립 목록을 불러오지 못했습니다: '+error.message;}finally{if(token===generation)reading=false;}
  }
  function choose(value,read=true){const changed=mode!==value;if(changed)closeResultDrawer('comments');mode=value;render();if(changed)enterView(mode==='clips'?basket:summary,mode==='clips'?1:-1);if(mode==='clips'&&read)void load();}
  document.addEventListener?.('studio-draft-changed',event=>{
    const target=event.detail;
    if(project&&target?.root===project.root&&String(target.vod_id)===String(project.vod_id))void load();
  });
  commentTab.onclick=()=>choose('comments');basketTab.onclick=()=>choose('clips');reload.onclick=load;editor.onclick=onOpenEditor;
  tabs.onkeydown=event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();choose(event.key==='Home'?'comments':event.key==='End'?'clips':mode==='clips'?'comments':'clips');(mode==='clips'?basketTab:commentTab).focus();}};
  function clipBlocked(source){return !project||busy||project.locked||project.tasks?.video?.state!=='complete'||!draft||!!source.stale;}
  function checkbox(comment,source){
    if(!comment)return null;
    const input=comment.querySelector('input'),commentChange=input.onchange;
    const button=node('button');button.type='button';button.className='secondary scene-selection-button';
    button.sceneUpdate=()=>{
      const commentState=input.commentState();
      const selected=mode==='clips'?!!draft?.request.clips.some(row=>row.id===source.id):commentState.checked;
      button.disabled=mode==='clips'?clipBlocked(source):commentState.disabled;
      button.textContent=mode==='clips'?(selected?'클립에서 제거':'클립 담기'):(selected?'댓글에서 제거':'댓글 담기');
      button.setAttribute('aria-pressed',String(selected));
      button.setAttribute('aria-label',`${button.textContent}: ${source.title}`);
    };
    button.onclick=()=>{
      if(button.disabled)return;
      if(mode==='comments'){input.checked=!input.commentState().checked;commentChange();button.sceneUpdate();}
      else return mutateClip(source,!draft?.request.clips.some(row=>row.id===source.id));
    };
    button.sceneUpdate();return button;
  }
  async function mutateClip(source,include){
    if(clipBlocked(source))return;
    const token=generation,target=identity(),snapshot=project;busy=true;loadId++;render();notice.textContent=include?'클립에 담는 중…':'클립에서 제거하는 중…';
    try{
      const value=await api('studio-info',target);if(token!==generation)return;
      const previous=value.draft||{revision:0,request:{clips:[]}};let saved;
      if(!include){
        const request=structuredClone(previous.request);request.clips=request.clips.filter(row=>row.id!==source.id);
        if(request.clips.length!==previous.request.clips.length)saved=await api('studio-draft',{...target,revision:previous.revision,request});else saved=previous;
      }else if(source.segment!=null){
        await api('studio-transcript-add',{...target,run:source.run,segment:source.segment});
        if(token!==generation)return;saved=(await api('studio-info',target)).draft;
      }else{
        const next=prepareBasketAdd({result:source.result,run:source.run,indices:[source.index],project:snapshot,draft:previous});
        saved=next.added?await api('studio-draft',{...target,revision:next.revision,request:next.request}):previous;
      }
      if(token!==generation)return;draft=saved;
      notice.textContent=include?'클립 목록에 담았습니다.':'클립 목록에서 제거했습니다.';
    }catch(error){if(token===generation)notice.textContent='클립 목록 변경 실패: '+error.message;}
    finally{busy=false;render();}
  }
  render();
  return {
    mount(host){if(panel.parentElement!==host)host.append(panel);if(!draft)void load();},
    refresh:load,
    checkbox,
    remove:id=>mutateClip({id},false),
    mode:()=>mode,
    updateComments,
    selectMode(value){if(['comments','clips'].includes(value)&&value!==mode)choose(value);},
    setProject(value){const changed=project?.path!==value?.path;project=value;if(changed){closeResultDrawer('comments');generation++;loadId++;reading=false;draft=null;mode='comments';notice.textContent='';}render();},
    async add(result,run,indices){
      if(!project||busy)return;
      if(project.locked||project.tasks?.video?.state!=='complete'){notice.textContent='이 VOD의 영상 처리가 끝난 뒤 클립을 담을 수 있습니다.';return;}
      if(!indices.length){notice.textContent='채택한 후보가 없습니다. 후보 검토에서 채택을 선택하세요.';return;}
      const token=generation,target=identity(),snapshot=project;busy=true;loadId++;notice.textContent='기존 편집 초안에 구간을 추가하는 중…';render();
      try{
        const value=await api('studio-info',target);if(token!==generation)return;
        const next=prepareBasketAdd({result,run,indices,project:snapshot,draft:value.draft});
        const saved=next.added?await api('studio-draft',{...target,revision:next.revision,request:next.request}):value.draft;
        if(token!==generation)return;
        draft=saved||{revision:0,request:{clips:[]}};choose('clips',false);
        notice.textContent=next.added?`${next.added}개 구간을 담았습니다. 기존 구간 설정·자막 교정은 유지됩니다.`:'이미 담은 구간입니다. 편집한 제목·시각·설정을 유지했습니다.';
      }catch(error){if(token===generation)notice.textContent='구간을 담지 못했습니다 · '+error.message+' · 다시 불러온 뒤 확인하세요.';}
      finally{busy=false;render();}
    }
  };
}
