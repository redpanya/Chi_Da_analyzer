import {timecode} from './player.js';
import {bindClipOrder} from './clip-order.js';

const $=id=>document.getElementById(id);
export function mixStudioURL(root,key,entry,step='range'){
  const page=entry==='mix-studio.html'?entry:'clip-studio.html';
  return page+'?'+new URLSearchParams({root,mix:key,step});
}

export function mixPresetRow(item,profiles){
  const options=profiles?.[item.key];
  // 이전 실행기는 현재 구간의 설정만 반환하고 여러 구간 저장을 지원하지 않는다.
  const problem=item.problem||(!options?'여러 구간에 프리셋을 적용하려면 실행기를 다시 시작하세요.':'');
  return {id:item.key,title:item.title,problem,options};
}

export function createMixPlayback(video,{items,source,changed,failed}){
  let ticket=0,frame=0,index=-1;
  function stop(){
    ticket++;index=-1;cancelAnimationFrame(frame);
    video.ontimeupdate=video.onended=video.onerror=null;
    if(video.hasAttribute('src')){video.pause();video.removeAttribute('src');video.load();}
    changed(null,-1);
  }
  function play(i,previousEnd=null){
    const item=items()[i];
    if(!item){stop();return;}
    cancelAnimationFrame(frame);
    const current=++ticket,start=(item.start_ms-item.origin)/1000,end=(item.end_ms-item.origin)/1000;
    const url=source(item.preview_key||item.key);
    const reuse=video.getAttribute('src')===url&&!video.error;
    index=i;changed(item,i);
    const next=()=>{if(current===ticket)play(i+1,item.end_ms);};
    const fail=()=>{if(current===ticket){stop();failed();}};
    const atEnd=()=>!video.seeking&&video.currentTime>=end;
    video.onended=()=>{if(video.ended)next();};video.onerror=()=>{if(video.error)fail();};
    video.ontimeupdate=()=>{if(atEnd())next();};
    if(!reuse)video.src=url;
    if(!reuse||previousEnd!==item.start_ms||video.ended||video.currentTime<start||video.currentTime>=end){
      video.currentTime=start;
    }
    function tick(){
      if(current!==ticket)return;
      if(atEnd())next();
      else frame=requestAnimationFrame(tick);
    }
    if(reuse&&!video.paused)tick();
    else video.play().then(tick).catch(fail);
  }
  return {play,stop,active:()=>index>=0};
}

export function createMixStudio(api,params,selectClip){
  const root=params.get('root');
  const context={library_root:root,key:params.get('mix')};
  const back=root?'./?'+new URLSearchParams({library_root:root})+'#mix':'./#mix';
  let data=null,moving=false,profiles,savedCurrent,savedEdits={};
  const otherRows=new Map();
  function syncLinks(){
    const step=document.body.dataset.studioStep;
    for(const card of $('mix-assembly').children){
      const link=card.querySelector('a');
      if(!link)continue;
      link.href=mixStudioURL(root,card.dataset.orderKey,data.editor_page,step);
      if(card.dataset.orderKey===context.key)link.setAttribute('aria-current','true');
      else link.removeAttribute('aria-current');
    }
    const url=new URL(location.href);
    url.searchParams.set('mix',context.key);url.searchParams.set('step',step);
    if(url.href!==location.href)history.replaceState(history.state,'',url);
  }
  function list(){
    const host=$('mix-assembly'),links=data.items.map((item,i)=>{
      const el=document.createElement(item.problem?'span':'a');
      el.className='assembly-select';
      const card=document.createElement('div');
      card.className='assembly-item';card.dataset.orderKey=item.key;
      if(data.items.length>1){
        el.dataset.clipGrip='';el.draggable=false;el.tabIndex=0;
        el.title='끌어서 순서 변경 (키보드 왼쪽 또는 오른쪽 화살표)';
        el.setAttribute('aria-keyshortcuts','ArrowLeft ArrowRight');
      }
      const name=document.createElement('strong'),source=document.createElement('small');
      name.textContent=`${i+1}. ${item.title}`;source.textContent=item.problem||item.broadcast;
      el.append(name,source);
      const label=document.createElement('label'),check=document.createElement('input');
      label.className='profile-check';check.type='checkbox';
      check.checked=profiles.checked(item.key);
      check.setAttribute('aria-label',item.title+' 프리셋 적용 대상');
      check.onchange=()=>profiles.check(item.key,check.checked);
      el.onclick=event=>{
        if(event.button||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
        event.preventDefault();
        if(moving)return;
        if(document.body.dataset.studioStep==='preset'&&$('profile-target').value==='checked'){
          check.click();
        }else if(!item.problem)selectClip(item.key);
      };
      label.append(check,'적용할 구간');card.append(el,label);return card;
    });
    const scroll=host.scrollLeft;
    host.replaceChildren(...links);host.scrollLeft=scroll;syncLinks();
    $('mix-order-play').disabled=moving||data.items.some(item=>item.problem);
    $('mix-order-state').textContent=`${data.items.length}개 구간 / 합계 ${timecode(data.items.reduce((n,r)=>n+r.end_ms-r.start_ms,0))}`;
  }
  document.addEventListener('studio-inspector-change',()=>{if(data)syncLinks();});
  async function move(itemKey,toIndex,session){
    if(moving||$('mix-assembly').hasAttribute('aria-busy'))return;
    moving=true;$('mix-order-play').disabled=true;
    try{
      if(session.dirty())await session.save();
      const changed=await api('mix-move',{...context,key:itemKey,revision:data.revision,to_index:toIndex});
      Object.assign(data,changed);
      for(const item of data.items){
        const row=otherRows.get(item.key);
        if(row)row.problem=mixPresetRow(item,data.profiles).problem;
      }
      $('mix-studio-open-folder').hidden=true;$('render-state').textContent='';
      $('mix-order-notice').textContent='구간 순서를 저장했습니다.';
    }catch(error){$('mix-order-notice').textContent=error.message;}
    finally{
      moving=false;list();profiles.labels();
      const index=data.items.findIndex(item=>item.key===itemKey);
      $('mix-assembly').children[index]?.querySelector('.assembly-select').focus();
    }
  }
  function configure(){
    document.body.classList.add('mix-studio');
    document.title='믹스클립 편집기';
    document.querySelector('.studio-step-rail > strong').textContent='믹스클립';
    document.querySelector('.preview-panel h1').textContent='믹스클립 편집기';
    for(const link of document.querySelectorAll('.studio-app-rail a')){
      const route=link.hash||'#split';
      link.href='./?'+new URLSearchParams({library_root:root})+route;
    }
    $('studio-return').href=back;$('studio-return').setAttribute('aria-label','믹스 목록으로 돌아가기');
    $('studio-return').textContent='← 믹스';
    document.querySelector('label[for="caption-version"]').textContent='현재 믹스 구간에 사용할 전사';
    $('mix-assembly-panel').hidden=false;
    $('mix-assembly-panel').querySelector('.button-row').append($('edit-undo'));
    $('render-start').textContent='믹스 전체를 한 영상으로 저장';
    $('draft-save').textContent='믹스 편집 저장';
    const single=document.querySelector('[name=output-mode][value=separate]');
    single.closest('fieldset').hidden=true;
    $('sidecar').closest('label').hidden=true;
    $('render-speed').closest('label').hidden=true;
    $('render-speed').closest('label').nextElementSibling.hidden=true;
    $('render-space-check').hidden=true;$('render-conflicts').nextElementSibling.hidden=true;
    $('profile-target').querySelector('[value=all]').textContent='믹스 전체';
    $('mix-order-play').disabled=true;
  }
  configure();
  return {
    get data(){return data;},back,
    get key(){return context.key;},
    read(key=context.key){
      if(!key||!root)throw Error('믹스 목록에서 편집할 구간을 선택하세요.');
      return api('mix-editor',{...context,key});
    },
    show(key,value){
      const rebuild=JSON.stringify(data?.items)!==JSON.stringify(value.items);
      context.key=key;data=value;otherRows.clear();savedEdits={};
      for(const item of data.items){
        if(item.key!==key)otherRows.set(item.key,mixPresetRow(item,data.profiles));
      }
      if(rebuild)list();else syncLinks();
    },
    presetRows(active){
      return (data?.items||[]).map(item=>item.key===context.key?active:otherRows.get(item.key)).filter(Boolean);
    },
    profileEdits(){
      const edits={};
      for(const [id,row] of otherRows){
        const initial=data.profiles?.[id];
        if(row.options!==initial&&JSON.stringify(row.options)!==JSON.stringify(initial))edits[id]=row.options;
      }
      return edits;
    },
    accept({mix_profiles,...request}){savedCurrent=JSON.stringify(request);savedEdits=mix_profiles;},
    bind(session,profileUI){
      profiles=profileUI;
      const dialog=$('mix-order-preview'),video=$('mix-order-video');
      const playback=createMixPlayback(video,{
        items:()=>data.items,source:key=>'mix-file?'+new URLSearchParams({root,key}),
        changed(item,i){$('mix-order-playing').textContent=item?`${i+1}. ${item.broadcast} / ${item.title}`:'재생 종료';},
        failed:()=>{$('mix-order-playing').textContent='원본 구간을 재생할 수 없습니다.';}
      });
      $('mix-order-play').onclick=async()=>{
        try{
          if(session.dirty())await session.save();
          $('studio-video').pause();dialog.showModal();playback.play(0);
        }catch(error){$('mix-order-notice').textContent=error.message;}
      };
      $('mix-order-close').onclick=()=>dialog.close();
      dialog.addEventListener('close',playback.stop);
      window.addEventListener('pagehide',playback.stop);
      const host=$('mix-assembly');
      bindClipOrder(host,(itemKey,index)=>move(itemKey,index,session),true);
      host.addEventListener('click',event=>{if(moving)event.preventDefault();});
      host.addEventListener('keydown',event=>{
        if(!event.target.closest('.assembly-select')||!['ArrowLeft','ArrowRight'].includes(event.key))return;
        const card=event.target.closest('[data-order-key]');
        if(!card)return;
        event.preventDefault();
        const index=data.items.findIndex(item=>item.key===card.dataset.orderKey);
        const to=index+(event.key==='ArrowLeft'?-1:1);
        if(index>=0&&to>=0&&to<data.items.length)move(card.dataset.orderKey,to,session);
      });
    },
    async save({mix_profiles:edits,...request}){
      const current=JSON.stringify(request),changes={};
      for(const id of new Set([...Object.keys(savedEdits),...Object.keys(edits)])){
        if(JSON.stringify(edits[id])!==JSON.stringify(savedEdits[id]))changes[id]=edits[id]||data.profiles[id];
      }
      const value=await api('mix-edit',{...context,revision:data.revision,profiles:changes,
        request:data.profiles&&current===savedCurrent?null:request});
      savedCurrent=current;savedEdits=edits;
      if(data.version!==value.version){$('mix-studio-open-folder').hidden=true;$('render-state').textContent='';}
      Object.assign(data,value);
      const row=data.items.find(item=>item.key===context.key),clip=request.clips[0];
      Object.assign(row,{title:clip.title,start_ms:clip.start_ms,end_ms:clip.end_ms});list();
      return value;
    },
    start:()=>api('mix-render',{...context,revision:data.revision}),
    async status(){
      const version=data.version,job=await api('mix-status',{library_root:root,version});
      if(version!==data.version)return null;
      const folder=$('mix-studio-open-folder');folder.hidden=job.state!=='complete';
      folder.onclick=()=>api('mix-open-folder',{library_root:root,version}).catch(error=>{$('render-state').textContent=error.message;});
      if(job.file||job.message)$('render-state').textContent=job.file||job.message;
      return job;
    },
    previewURL:()=> 'mix-file?'+new URLSearchParams({root,key:data.items.find(item=>item.key===context.key)?.preview_key||context.key}),
    total(local){
      return data.items.reduce((n,r)=>n+(r.key===context.key&&local?local.end_ms-local.start_ms:r.end_ms-r.start_ms),0);
    }
  };
}
