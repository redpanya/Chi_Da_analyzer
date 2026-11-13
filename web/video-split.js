import {enterView} from './workspace-motion.js';
import {bindDesktopPanels} from './desktop-panels.js';
import {clock,parseTime,validPoints,intervals} from './video-split-model.js';
import {connectSplitAudio} from './video-split-audio.js';
export function createVideoSplit({root,workQueue}){
const $=id=>root.querySelector('#'+id),video=$('split-video');
const el=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
let source=null,sourceId=null,points=[],job=null,dirty=true,requesting=false,refreshing=false,pointDrafts={},queuedTask=null;
const active=()=>!!job&&['planning','running'].includes(job.state);
const splitLayout=bindDesktopPanels({container:root.querySelector('.split-grid'),panels:[root.querySelector('.preview-panel'),root.querySelector('.boundaries-panel')],key:'video-split',initial:[760,240],minWidths:[340,220],flexIndex:0});
$('split-layout-reset').onclick=()=>splitLayout.reset();
const error=e=>{$('split-error').textContent=e?.message||String(e);$('split-error').hidden=false;};
async function api(action,data={}){
  const response=await fetch('api/split-'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const value=await response.json();if(!response.ok)throw Error(value.error||'요청을 처리하지 못했습니다.');
  if(value.queued)queuedTask=value.queued;
  return workQueue.accept(value);
}
const splitAudio=connectSplitAudio({video,api,changed:invalidate,error});

// 초안 파일을 새로 저장하지 않고 화면에 입력한 분할점의 이탈만 확인한다.
let baseline='';
const snapshot=()=>JSON.stringify({sourceId,points,pointDrafts,folder:$('split-folder').value,pending:$('split-time').value,audio:splitAudio.selection()});
const edits={accept(){baseline=snapshot();},dirty(){return baseline!==snapshot();},async allow(){return !this.dirty()||confirm('현재 입력한 분할 설정을 버리고 이동하시겠습니까?');}};
window.addEventListener('beforeunload',event=>{if(edits.dirty()){event.preventDefault();event.returnValue='';}});
async function action(fn){
  if(requesting)return;requesting=true;$('split-error').hidden=true;controls();
  try{await fn();}catch(e){error(e);}finally{requesting=false;controls();}
}
function controls(){
  const locked=requesting||active()||!!queuedTask;
  for(const id of ['split-load','split-path'])$(id).disabled=locked;
  for(const id of ['split-add-current','split-time','split-minutes','split-interval','split-clear'])$(id).disabled=locked||!source;
  for(const input of root.querySelectorAll('#split-point-form button,#split-points button,#split-points input'))input.disabled=locked;
  splitAudio.lock(locked);
  $('split-plan').disabled=locked||!points.length||!splitAudio.valid();
  $('split-start').disabled=locked||dirty||!job?.plan||['complete','deleting'].includes(job.state);
  $('split-stop').hidden=!active();$('split-stop').disabled=requesting||job?.stopping;
  $('split-resume').hidden=!job||!['paused','error'].includes(job.state)||dirty;
  $('split-resume').disabled=locked;
  $('split-resume-note').hidden=$('split-resume').hidden;
  $('split-folder').disabled=$('split-folder-pick').disabled=locked||!!job?.folder;
  $('split-open-folder').hidden=!job?.folder;
}
function setSource(id,value,audioSelection=null){
  const firstShow=$('split-workspace').hidden;
  sourceId=id;source=value;$('split-workspace').hidden=false;$('split-path').value=value.path;
  $('split-duration').textContent='/ '+clock(value.duration);
  root.classList.add('split-has-source');$('source-heading').textContent=value.name;$('source-heading').title=value.name;$('split-load').textContent='파일 변경';
  $('split-source-info').textContent=`${clock(value.duration)} · ${value.width}×${value.height} · ${value.fps.toFixed(2)}fps · ${(value.identity.bytes/1024**3).toFixed(2)}GiB · 오디오 ${value.audio_count}개`;
  $('split-format-note').textContent=value.preview_note||'브라우저의 재생 지원은 파일 코덱에 따라 다릅니다.';
  splitAudio.reset(id,value,audioSelection);
  video.pause();video.src='split-file?'+new URLSearchParams({source:id});video.load();
  $('split-folder').value=value.path.replace(/[/\\][^/\\]+$/,'')||'/';
  draw();controls();if(firstShow)enterView($('split-workspace'),0);
}
function invalidate(){dirty=true;$('split-plan-panel').hidden=true;controls();}
function renderPoints(){
  const list=$('split-points');list.replaceChildren();
  for(const [i,value] of points.entries()){
    const row=el('div');row.className='split-point';
    const input=el('input');input.value=pointDrafts[value]??clock(value);input.oninput=()=>{pointDrafts[value]=input.value;};input.setAttribute('aria-label',`${i+1}번 분할 시각`);
    const save=el('button','✓');save.className='secondary';save.title='분할 시각 수정 적용';save.setAttribute('aria-label',`${i+1}번 분할 시각 수정 적용`);save.onclick=()=>{
      try{const updated=validPoints(points.map((v,n)=>n===i?parseTime(input.value):v),source.duration);delete pointDrafts[value];points=updated;invalidate();renderPoints();}catch(e){error(e);}
    };
    const view=el('button','▶');view.className='secondary';view.title='해당 시각 보기';view.setAttribute('aria-label',`${clock(value)} 시각 보기`);view.onclick=()=>seek(value);
    const remove=el('button','×');remove.className='secondary';remove.setAttribute('aria-label',`${clock(value)} 분할점 삭제`);
    remove.onclick=()=>{delete pointDrafts[value];points.splice(i,1);invalidate();renderPoints();};row.append(input,save,view,remove);list.append(row);
  }
  if(!points.length)list.append(el('p','아직 분할점이 없습니다.'));
  draw();controls();
}
function add(value){points=validPoints([...points,value],source.duration);invalidate();renderPoints();}
function seek(at){if(!source)return;video.currentTime=Math.max(0,Math.min(source.duration,at));}
function draw(){
  if(!source)return;
  const canvas=$('split-canvas'),box=$('split-timeline'),width=Math.min(30000,Math.max(300,box.clientWidth)*Number($('split-zoom').value));
  const tokens=getComputedStyle(document.documentElement),color=(key,fallback)=>tokens.getPropertyValue(key).trim()||fallback;
  canvas.width=width;const ctx=canvas.getContext('2d');ctx.fillStyle=color('--ds-chart-bg','#1c1d1f');ctx.fillRect(0,0,width,72);
  ctx.strokeStyle=color('--ds-chart-grid','#2e3033');ctx.fillStyle=color('--ds-chart-label','#9da5b6');ctx.font='11px system-ui';
  const ticks=Math.max(2,Math.floor(width/130));
  for(let i=0;i<=ticks;i++){const x=width*i/ticks;ctx.beginPath();ctx.moveTo(x,30);ctx.lineTo(x,55);ctx.stroke();ctx.fillText(clock(source.duration*i/ticks).slice(0,-4),Math.max(3,Math.min(width-60,x+3)),22);}
  for(const t of points){const x=t/source.duration*width;ctx.fillStyle=color('--ds-chart-reaction','#cf9a12');ctx.fillRect(x-1,30,2,36);}
  ctx.fillStyle=color('--ds-chart-label','#9da5b6');ctx.fillRect(video.currentTime/source.duration*width-1,0,3,72);
}
$('split-canvas').onclick=e=>{const rect=e.currentTarget.getBoundingClientRect();seek((e.clientX-rect.left)/rect.width*source.duration);};
$('split-zoom').onchange=()=>{draw();$('split-follow').click();};
$('split-follow').onclick=()=>{$('split-timeline').scrollLeft=video.currentTime/source.duration*$('split-canvas').width-$('split-timeline').clientWidth/2;};
window.addEventListener('resize',draw);document.addEventListener('chida-themechange',draw);root.querySelector('.split-grid').addEventListener('chida-panelresize',draw);
new ResizeObserver(draw).observe($('split-timeline'));
video.addEventListener('timeupdate',()=>{$('split-clock').textContent=clock(video.currentTime);draw();});
video.addEventListener('play',()=>$('split-play').textContent='일시정지');video.addEventListener('pause',()=>$('split-play').textContent='재생');
video.addEventListener('error',()=>{$('split-preview-note').textContent='브라우저에서 미리보기를 재생하지 못했습니다. 파일 검사 결과와는 별개이며, 시각을 직접 입력해 분할할 수 있습니다.';});
$('split-play').onclick=()=>{if(video.paused)video.play().catch(e=>{if(e.name!=='AbortError')error(e);});else video.pause();};
$('split-back').onclick=()=>seek(video.currentTime-3);$('split-forward').onclick=()=>seek(video.currentTime+3);
$('split-seek-form').onsubmit=e=>{e.preventDefault();try{seek(parseTime($('split-seek-time').value));}catch(e){error(e);}};
$('split-point-form').onsubmit=e=>{e.preventDefault();try{add(parseTime($('split-time').value));}catch(e){error(e);}};
$('split-add-current').onclick=()=>{try{add(Math.round(video.currentTime*1000)/1000);}catch(e){error(e);}};
$('split-interval').onclick=()=>{try{const next=intervals(Number($('split-minutes').value),source.duration);if(points.length&&!confirm('입력한 분할점을 이 간격으로 바꿀까요?'))return;points=next;pointDrafts={};invalidate();renderPoints();}catch(e){error(e);}};
$('split-clear').onclick=()=>{if(points.length&&!confirm('분할점을 모두 지울까요?'))return;points=[];pointDrafts={};invalidate();renderPoints();};
async function load(path){
  if(!await edits.allow())return;
  const value=await api('register',{path});job=null;points=[];pointDrafts={};$('split-time').value='';dirty=true;setSource(value.source_id,value.source);
  $('split-job-panel').hidden=true;$('split-plan-panel').hidden=true;renderPoints();edits.accept();
}
$('split-source-form').onsubmit=e=>{e.preventDefault();action(async()=>{const value=await api('pick');if(value.path)await load(value.path);});};
$('split-folder-pick').onclick=()=>action(async()=>{const value=await api('pick',{folder:true});if(value.path){$('split-folder').value=value.path;}});
function planView(){
  if(!job?.plan||dirty){$('split-plan-panel').hidden=true;return;}
  const panel=$('split-plan-panel'),firstShow=panel.hidden;panel.hidden=false;const body=$('split-boundaries');body.replaceChildren();
  for(const [i,c] of job.plan.cuts.entries()){const tr=el('tr');for(const text of [i+1,clock(c.requested),clock(c.actual),`+${c.difference.toFixed(3)}초`])tr.append(el('td',text));body.append(tr);}
  const parts=$('split-parts');parts.replaceChildren();for(const part of job.plan.parts)parts.append(el('p',`${part.index+1}. ${clock(part.start)} → ${clock(part.end)} · ${clock(part.duration)} · ${part.name}`));
  $('split-space').textContent=`${job.plan.parts.length}개 파일 · 출력 합계 약 ${(source.identity.bytes/1024**3).toFixed(2)}GiB + 여유 공간 필요 · ${job.folder?'이 작업의 출력 폴더입니다.':'선택 폴더 안에 새 작업 폴더를 만듭니다.'}`;
  const kept=job.audio_selection?.tracks||source.streams.filter(s=>s.codec_type==='audio').map(s=>s.index);
  const audioTracks=source.streams.filter(s=>s.codec_type==='audio');
  $('split-plan-audio').textContent=`저장 오디오: ${kept.length?kept.map(n=>'트랙 '+(audioTracks.findIndex(s=>s.index===n)+1)).join(', '):'없음'} · 재인코딩 없음`;
  if(job.folder)$('split-folder').value=job.folder;
  if(firstShow)enterView(panel,0);
}
function stateView(){
  if(!job)return;const panel=$('split-job-panel'),firstShow=panel.hidden;panel.hidden=false;
  $('split-state').textContent=job.message;$('split-state').dataset.state=job.state;
  $('split-progress').value=job.progress||0;
  $('split-elapsed').textContent=`${job.state==='complete'?'완료까지 소요':'누적 실행'} 시간 ${clock(job.elapsed_seconds||0)} · 완료 파일 ${Object.keys(job.outputs).length}/${job.plan?.parts.length||'—'}`;
  const list=$('split-outputs');list.replaceChildren();
  for(const [index,out] of Object.entries(job.outputs)){
    const row=el('p'),a=el('a',out.name);a.href='split-file?'+new URLSearchParams({run:job.id,index});a.download=out.name;
    row.append(a,el('span',` · 오디오 ${out.audio_tracks}개 · ${out.check}`));list.append(row);
  }
  controls();
  if(firstShow)enterView(panel,0);
}
function restoreCurrent(value){
  job=value;pointDrafts={};$('split-time').value='';setSource(job.source_id,job.source,job.audio_selection);points=[...job.requested];dirty=false;renderPoints();planView();stateView();edits.accept();
}
$('split-plan').onclick=()=>action(async()=>{job=await api('plan',{source_id:sourceId,points,audio_selection:splitAudio.selection()});dirty=false;planView();stateView();edits.accept();});
$('split-start').onclick=()=>action(async()=>{job=await api('start',{id:job.id,folder:$('split-folder').value});planView();stateView();edits.accept();});
$('split-resume').onclick=()=>action(async()=>{job=await api('resume',{id:job.id,folder:$('split-folder').value});planView();stateView();edits.accept();});
$('split-stop').onclick=()=>action(async()=>{job=await api('stop',{id:job.id});job.stopping=true;stateView();});
$('split-open-folder').onclick=()=>action(()=>api('open-folder',{id:job.id}));
async function refresh(){
  if(refreshing||requesting)return;
  if(queuedTask){
    if(queuedTask.run){
      refreshing=true;
      try{const next=await api('status',{id:queuedTask.run});queuedTask=null;$('split-error').hidden=true;restoreCurrent(next);}
      catch(e){error(e);}finally{refreshing=false;controls();}
    }else if(['cancelled','error'].includes(queuedTask.state)){
      error(queuedTask.message);queuedTask=null;controls();
    }
    return;
  }
  if(!job||!active())return;refreshing=true;const id=job.id;
  try{const next=await api('status',{id});if(job?.id!==id)return;const old=job.state;job=next;stateView();if(old!==job.state){planView();edits.accept();}}catch(e){error(e);}finally{refreshing=false;}
}
document.addEventListener('work-queue-change',({detail:item})=>{
  if(item.id===queuedTask?.id||(item.action.startsWith('split-')&&(!sourceId||item.source_id===sourceId)&&['queued','starting','running'].includes(item.state))){
    queuedTask=item;controls();refresh();
  }
});
// 같은 탭에서 이동했다 돌아오면 브라우저가 보존한 타이머도 재개한다.
setInterval(refresh,1000);window.addEventListener('pagehide',()=>video.pause());
window.addEventListener('pageshow',()=>refresh());
action(async()=>{
  edits.accept();
  const {run}=await api('current');if(run)restoreCurrent(run);
});
return {pause(){video.pause();splitAudio.stop();}};
}
