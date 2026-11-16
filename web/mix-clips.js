import {mixStudioURL,createMixPlayback} from './mix-studio.js';
import {timecode} from './player.js';
import {bindClipOrder} from './clip-order.js';

export function createMixPage({api,getRoot}){
  const $=id=>document.getElementById(id);
  const page=$('mix-page'),list=$('mix-list'),video=$('mix-video'),preview=$('mix-preview'),save=$('mix-save');
  const status=$('mix-status'),playing=$('mix-playing'),result=$('mix-result');
  let draft=null,library='',view=0,busy=false,poll=0;
  const clock=ms=>timecode(ms)+(ms%1000?'.'+String(ms%1000).padStart(3,'0'):'');
  const file=params=>'mix-file?'+new URLSearchParams({root:library,...params});
  const button=(label,aria,fn)=>{
    const el=document.createElement('button');
    el.type='button';el.className='subtle';el.textContent=label;el.setAttribute('aria-label',aria);el.onclick=fn;
    return el;
  };

  const playback=createMixPlayback(video,{
    items:()=>draft?.items||[],source:key=>file({key}),
    changed(item,index){
      list.querySelector('[aria-current]')?.removeAttribute('aria-current');
      if(item)list.children[index].setAttribute('aria-current','true');
      video.hidden=!item;video.controls=false;
      preview.textContent=item?'미리보기 중지':'순서 미리보기';
      playing.textContent=item?`원본 구간 ${index+1}/${draft.items.length}  ${item.broadcast} / ${item.title}`:'';
    },
    failed:()=>{status.textContent='원본 구간을 재생할 수 없습니다. 믹스클립을 다시 열어 원본 상태를 확인하세요.';}
  });
  const stop=playback.stop;
  preview.onclick=()=>playback.active()?stop():playback.play(0);
  bindClipOrder(list,(key,to_index)=>edit('move',draft.items.find(row=>row.key===key),{to_index}));
  $('mix-clear').onclick=()=>{
    if(!busy&&draft?.items.length){
      $('mix-clear-title').textContent=`믹스클립 목록의 ${draft.items.length}개 구간을 비울까요?`;
      $('mix-clear-dialog').showModal();
    }
  };
  $('mix-clear-confirm').onclick=()=>edit('clear');

  function controls(){
    const blocked=busy||!draft?.items.length||draft.items.some(row=>row.problem);
    preview.disabled=blocked;save.disabled=blocked||draft?.job?.state==='running';
    $('mix-clear').disabled=busy||!draft?.items.length;
    $('mix-open-folder').disabled=$('mix-watch').disabled=busy;
    for(const el of list.querySelectorAll('button'))el.disabled=busy;
  }
  function draw(){
    list.replaceChildren();
    const rows=draft?.items||[];
    $('mix-count').textContent=rows.length?`${rows.length}개 구간 / 합계 ${clock(rows.reduce((n,r)=>n+r.end_ms-r.start_ms,0))}`:'';
    const entry=$('mix-editor-open'),first=rows.find(row=>!row.problem);
    entry.hidden=!first;if(first)entry.href=mixStudioURL(library,first.key,draft.editor_page);else entry.removeAttribute('href');
    if(draft&&!rows.length){
      const empty=document.createElement('li');empty.textContent='각 VOD의 담은 클립에서 믹스클립 보내기를 누르세요.';list.append(empty);
    }
    rows.forEach((row,i)=>{
      const li=document.createElement('li'),name=document.createElement('strong'),meta=document.createElement('small'),actions=document.createElement('div');
      li.dataset.orderKey=row.key;
      const grip=document.createElement('div');grip.className='mix-card-heading';
      if(rows.length>1){
        grip.dataset.clipGrip='';grip.tabIndex=0;
        grip.title='끌어서 순서 변경 (키보드 위 또는 아래 화살표)';
        grip.setAttribute('aria-keyshortcuts','ArrowUp ArrowDown');
        grip.onkeydown=e=>{
          if(e.key!=='ArrowUp'&&e.key!=='ArrowDown')return;
          e.preventDefault();
          const to_index=i+(e.key==='ArrowUp'?-1:1);
          if(to_index>=0&&to_index<rows.length)edit('move',row,{to_index});
        };
      }
      name.textContent=`${i+1}. ${row.title}`;
      meta.textContent=`${row.broadcast} (VOD ${row.vod_id}) / ${clock(row.start_ms)} → ${clock(row.end_ms)}`;
      grip.append(name,meta);li.append(grip);
      if(row.problem){const msg=document.createElement('span');msg.className='error';msg.textContent=row.problem;li.append(msg);}
      actions.className='play-actions';
      if(!row.problem){
        const edit=document.createElement('a');edit.className='secondary';edit.textContent='편집';
        edit.setAttribute('aria-label',row.title+' 편집');edit.href=mixStudioURL(library,row.key,draft.editor_page);actions.append(edit);
      }
      actions.append(button('제거',row.title+' 믹스에서 제거',()=>edit('remove',row)));li.append(actions);list.append(li);
    });
    controls();
  }

  async function edit(action,row=null,change={}){
    if(busy)return;
    const ticket=view,rowIndex=draft.items.indexOf(row);
    stop();busy=true;controls();status.textContent='';
    try{
      const value=await api('mix-'+action,{library_root:library,revision:draft.revision,key:row?.key,...change});
      if(ticket!==view)return;
      draft=value;result.hidden=true;clearTimeout(poll);busy=false;draw();
      const next=list.children[action==='move'?draft.items.findIndex(item=>item.key===row.key):Math.min(rowIndex,list.children.length-1)];
      next?.querySelector('[data-clip-grip], a, button:not(:disabled)')?.focus();
      if(action==='clear'){status.textContent='믹스클립 목록을 비웠습니다.';$('mix-heading').focus();}
    }catch(error){
      if(ticket===view)await load(ticket,error.message);
    }finally{if(ticket===view){busy=false;controls();}}
  }

  function jobState(job){
    draft.job=job;controls();
    result.hidden=job.state!=='complete';clearTimeout(poll);
    if(job.state==='complete'){
      $('mix-file').textContent=job.file;
      status.textContent='믹스클립을 저장했습니다.';
    }else if(job.state==='running'){
      status.textContent=job.message;
      const ticket=view,version=draft.version;
      poll=setTimeout(async()=>{
        try{
          const value=await api('mix-status',{library_root:library,version});
          if(ticket===view&&version===draft?.version)jobState(value);
        }catch(error){if(ticket===view) {status.textContent=error.message;draft.job=null;controls();}}
      },650);
    }else status.textContent=job.message||'';
  }
  $('mix-open-folder').onclick=()=>api('mix-open-folder',{library_root:library,version:draft.version}).catch(error=>{status.textContent=error.message;});
  $('mix-watch').onclick=()=>{
    stop();video.hidden=false;video.controls=true;video.src=file({version:draft.version});
    video.play().catch(()=>{status.textContent='플레이어에서 재생을 누르세요.';});
  };
  save.onclick=async()=>{
    if(save.disabled)return;
    const ticket=view;
    busy=true;controls();status.textContent='저장 준비 중';
    try{
      const job=await api('mix-render',{library_root:library,revision:draft.revision});
      if(ticket===view)jobState(job);
    }catch(error){if(ticket===view)await load(ticket,error.message);}
    finally{if(ticket===view){busy=false;controls();}}
  };
  async function load(ticket,message=''){
    try{
      const value=await api('mix-info',{library_root:library});
      if(ticket!==view)return;
      draft=value;draw();jobState(value.job);
      if(message)status.textContent=message;
    }catch(error){if(ticket===view){draft=null;result.hidden=true;draw();status.textContent=error.message;}}
  }
  return {
    stop,
    show(visible){
      if(visible&&!page.hidden&&busy&&library===getRoot())return;
      const ticket=++view;
      if($('mix-clear-dialog').open)$('mix-clear-dialog').close();
      clearTimeout(poll);page.hidden=!visible;busy=false;
      if(!visible)return;
      const root=getRoot();busy=true;status.textContent='목록을 불러오는 중';
      if(library!==root||!draft){library=root;draft=null;result.hidden=true;draw();}else controls();
      return load(ticket).finally(()=>{if(ticket===view){busy=false;controls();}});
    }
  };
}
