import {createEditSession} from './edit-session.js';
import {clock,parseTime,validPoints,intervals} from './video-split-model.js';
import {connectSplitDeletion} from './video-split-delete.js';
import {connectSplitAudio} from './video-split-audio.js';
const $=id=>document.getElementById(id),video=$('split-video');
const el=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
let source=null,sourceId=null,points=[],job=null,dirty=true,requesting=false,refreshing=false,historyLimit=30,draftRevision=0,pointDrafts={};
const active=()=>!!job&&['planning','running'].includes(job.state);
const error=e=>{$('split-error').textContent=e?.message||String(e);$('split-error').hidden=false;};
async function api(action,data={}){
  const response=await fetch('api/split-'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const value=await response.json();if(!response.ok)throw Error(value.error||'요청을 처리하지 못했습니다.');return value;
}
const splitAudio=connectSplitAudio({video,api,changed:invalidate,error});
const draftStatus=el('p');draftStatus.id='split-draft-state';draftStatus.setAttribute('role','status');document.querySelector('.source-panel').append(draftStatus);
const draftButton=el('button','분할 초안 저장'),restoreDraftButton=el('button','저장한 초안 불러오기');document.querySelector('.source-panel').append(draftButton,restoreDraftButton);
const edits=createEditSession({status:draftStatus,read:()=>source?{source_id:sourceId,points:[...points],folder:$('split-folder').value,point_drafts:pointDrafts,pending_point:$('split-time').value,audio_selection:splitAudio.selection()}:null,
  save:async draft=>{const value=await api('draft-save',{revision:draftRevision,draft});draftRevision=value.revision;}});
draftButton.onclick=()=>action(()=>edits.save());
restoreDraftButton.onclick=()=>action(async()=>{
  if(!await edits.allow())return;
  const saved=await api('draft-get');draftRevision=saved.revision;
  if(!saved.draft){$('split-notice').textContent='저장한 분할 초안이 없습니다.';$('split-notice').hidden=false;return;}
  const value=await api('register',{path:saved.draft.source.path});
  if(JSON.stringify(value.source.identity)!==JSON.stringify(saved.draft.source.identity))throw Error('초안의 원본이 변경됐습니다. 원본 파일을 확인하세요.');
  job=null;pointDrafts=saved.draft.point_drafts||{};$('split-time').value=saved.draft.pending_point||'';points=saved.draft.points;dirty=true;setSource(value.source_id,value.source,saved.draft.audio_selection);$('split-folder').value=saved.draft.folder;renderPoints();$('split-plan-panel').hidden=$('split-job-panel').hidden=true;history.replaceState(null,'',location.pathname);edits.accept(saved.updated_at);
});
$('split-folder').addEventListener('input',()=>edits.changed());
const historySearch=el('input');historySearch.type='search';historySearch.placeholder='작업 이름·날짜 검색';historySearch.setAttribute('aria-label','영상 나누기 작업 검색');$('split-history').before(historySearch);
historySearch.oninput=()=>{historyLimit=30;historyView().catch(error);};
async function action(fn){
  if(requesting)return;requesting=true;$('split-error').hidden=true;$('split-notice').hidden=true;controls();
  try{await fn();}catch(e){error(e);}finally{requesting=false;controls();}
}
function controls(){
  const locked=requesting||active();draftButton.disabled=locked||!source;restoreDraftButton.disabled=locked;
  for(const id of ['split-select-video','split-pick','split-load','split-path'])$(id).disabled=locked;
  for(const id of ['split-add-current','split-time','split-minutes','split-interval','split-clear'])$(id).disabled=locked||!source;
  for(const input of document.querySelectorAll('#split-point-form button,#split-points button,#split-points input'))input.disabled=locked;
  for(const b of document.querySelectorAll('#split-history button'))b.disabled=locked;
  splitAudio.lock(locked);
  $('split-plan').disabled=locked||!points.length||!splitAudio.valid();
  $('split-start').disabled=locked||dirty||!job?.plan||['complete','deleting'].includes(job.state);
  $('split-stop').hidden=!active();$('split-stop').disabled=requesting||job?.stopping;
  $('split-resume').hidden=!job||!['paused','error'].includes(job.state)||dirty;
  $('split-resume').disabled=locked;
  $('split-resume-note').hidden=$('split-resume').hidden;
  $('split-folder').disabled=$('split-folder-pick').disabled=locked||!!job?.folder;
  $('split-open-folder').hidden=!job?.folder;
  updateDeletion({busy:requesting});
}
function setSource(id,value,audioSelection=null){
  sourceId=id;source=value;$('split-workspace').hidden=false;$('split-path').value=value.path;
  $('split-source-info').textContent=`${value.name} · ${clock(value.duration)} · ${value.width}×${value.height} · ${value.fps.toFixed(2)}fps · ${(value.identity.bytes/1024**3).toFixed(2)}GiB · 오디오 ${value.audio_count}개`;
  splitAudio.reset(id,value,audioSelection);
  video.pause();video.src='split-file?'+new URLSearchParams({source:id});video.load();
  $('split-folder').value=value.path.replace(/[/\\][^/\\]+$/,'')||'/';
  draw();controls();
}
function invalidate(){edits.changed();dirty=true;$('split-plan-panel').hidden=true;controls();}
function renderPoints(){
  const list=$('split-points');list.replaceChildren();
  for(const [i,value] of points.entries()){
    const row=el('div');row.className='split-point';
    const input=el('input');input.value=pointDrafts[value]??clock(value);input.oninput=()=>{pointDrafts[value]=input.value;edits.changed();};input.setAttribute('aria-label',`${i+1}번 분할 시각`);
    const save=el('button','수정');save.className='secondary';save.onclick=()=>{
      try{const updated=validPoints(points.map((v,n)=>n===i?parseTime(input.value):v),source.duration);delete pointDrafts[value];points=updated;invalidate();renderPoints();}catch(e){error(e);}
    };
    const view=el('button','보기');view.className='secondary';view.onclick=()=>seek(value);
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
  canvas.width=width;const ctx=canvas.getContext('2d');ctx.fillStyle='#f7f5f2';ctx.fillRect(0,0,width,72);
  ctx.strokeStyle='#c9c2b9';ctx.fillStyle='#66625e';ctx.font='11px system-ui';
  const ticks=Math.max(2,Math.floor(width/130));
  for(let i=0;i<=ticks;i++){const x=width*i/ticks;ctx.beginPath();ctx.moveTo(x,30);ctx.lineTo(x,55);ctx.stroke();ctx.fillText(clock(source.duration*i/ticks).slice(0,-4),Math.max(3,Math.min(width-60,x+3)),22);}
  for(const t of points){const x=t/source.duration*width;ctx.fillStyle='#B7481F';ctx.fillRect(x-1,30,2,36);}
  ctx.fillStyle='#18181b';ctx.fillRect(video.currentTime/source.duration*width-1,0,3,72);
}
$('split-canvas').onclick=e=>{const rect=e.currentTarget.getBoundingClientRect();seek((e.clientX-rect.left)/rect.width*source.duration);};
$('split-zoom').onchange=()=>{draw();$('split-follow').click();};
$('split-follow').onclick=()=>{$('split-timeline').scrollLeft=video.currentTime/source.duration*$('split-canvas').width-$('split-timeline').clientWidth/2;};
window.addEventListener('resize',draw);
video.addEventListener('timeupdate',()=>{$('split-clock').textContent=clock(video.currentTime);draw();});
video.addEventListener('play',()=>$('split-play').textContent='일시정지');video.addEventListener('pause',()=>$('split-play').textContent='재생');
video.addEventListener('error',()=>{$('split-preview-note').textContent='브라우저에서 미리보기를 재생하지 못했습니다. 파일 검사 결과와는 별개이며, 시각을 직접 입력해 분할할 수 있습니다.';});
$('split-play').onclick=()=>{if(video.paused)video.play().catch(error);else video.pause();};
$('split-back').onclick=()=>seek(video.currentTime-3);$('split-forward').onclick=()=>seek(video.currentTime+3);
$('split-seek-form').onsubmit=e=>{e.preventDefault();try{seek(parseTime($('split-seek-time').value));}catch(e){error(e);}};
$('split-time').addEventListener('input',()=>edits.changed());
$('split-point-form').onsubmit=e=>{e.preventDefault();try{add(parseTime($('split-time').value));}catch(e){error(e);}};
$('split-add-current').onclick=()=>{try{add(Math.round(video.currentTime*1000)/1000);}catch(e){error(e);}};
$('split-interval').onclick=()=>{try{const next=intervals(Number($('split-minutes').value),source.duration);if(points.length&&!confirm('입력한 분할점을 이 간격으로 바꿀까요?'))return;points=next;pointDrafts={};invalidate();renderPoints();}catch(e){error(e);}};
$('split-clear').onclick=()=>{if(points.length&&!confirm('분할점을 모두 지울까요?'))return;points=[];pointDrafts={};invalidate();renderPoints();};
async function load(path){
  if(!await edits.allow())return;
  const value=await api('register',{path});job=null;points=[];pointDrafts={};$('split-time').value='';dirty=true;setSource(value.source_id,value.source);
  $('split-job-panel').hidden=true;$('split-plan-panel').hidden=true;renderPoints();history.replaceState(null,'',location.pathname);edits.accept();
}
$('split-source-form').onsubmit=e=>{e.preventDefault();action(()=>load($('split-path').value));};
function resetSelection(){
  splitAudio.reset(null,null);video.pause();video.removeAttribute('src');video.load();
  source=null;sourceId=null;points=[];pointDrafts={};job=null;dirty=true;
  $('split-path').value='';$('split-time').value='';$('split-clock').textContent=clock(0);
  $('split-seek-time').value=clock(0);$('split-zoom').value='1';
  $('split-source-info').textContent='선택한 파일을 업로드하거나 복제하지 않습니다.';
  for(const id of ['split-workspace','split-plan-panel','split-job-panel','split-error'])$(id).hidden=true;
  for(const b of document.querySelectorAll('#split-history button'))b.classList.remove('active');
  history.replaceState(null,'',location.pathname);controls();
  document.querySelector('.source-panel').scrollIntoView({block:'start'});$('split-path').focus({preventScroll:true});
}
$('split-select-video').onclick=async()=>{
  if(requesting||active())return;
  if(!await edits.allow())return;
  $('split-notice').hidden=true;resetSelection();edits.accept();
};
$('split-pick').onclick=()=>action(async()=>{const value=await api('pick');if(value.path)await load(value.path);});
$('split-folder-pick').onclick=()=>action(async()=>{const value=await api('pick',{folder:true});if(value.path){$('split-folder').value=value.path;edits.changed();}});
function planView(){
  if(!job?.plan||dirty){$('split-plan-panel').hidden=true;return;}
  $('split-plan-panel').hidden=false;const body=$('split-boundaries');body.replaceChildren();
  for(const [i,c] of job.plan.cuts.entries()){const tr=el('tr');for(const text of [i+1,clock(c.requested),clock(c.actual),`+${c.difference.toFixed(3)}초`])tr.append(el('td',text));body.append(tr);}
  const parts=$('split-parts');parts.replaceChildren();for(const part of job.plan.parts)parts.append(el('p',`${part.index+1}. ${clock(part.start)} → ${clock(part.end)} · ${clock(part.duration)} · ${part.name}`));
  $('split-space').textContent=`${job.plan.parts.length}개 파일 · 출력 합계 약 ${(source.identity.bytes/1024**3).toFixed(2)}GiB + 여유 공간 필요 · ${job.folder?'이 작업의 출력 폴더입니다.':'선택 폴더 안에 새 작업 폴더를 만듭니다.'}`;
  const kept=job.audio_selection?.tracks||source.streams.filter(s=>s.codec_type==='audio').map(s=>s.index);
  const audioTracks=source.streams.filter(s=>s.codec_type==='audio');
  $('split-plan-audio').textContent=`저장 오디오: ${kept.length?kept.map(n=>'트랙 '+(audioTracks.findIndex(s=>s.index===n)+1)).join(', '):'없음'} · 재인코딩 없음`;
  if(job.folder)$('split-folder').value=job.folder;
}
function stateView(){
  if(!job)return;$('split-job-panel').hidden=false;
  $('split-state').textContent=job.message;$('split-state').dataset.state=job.state;
  $('split-progress').value=job.progress||0;
  $('split-elapsed').textContent=`${job.state==='complete'?'완료까지 소요':'누적 실행'} 시간 ${clock(job.elapsed_seconds||0)} · 완료 파일 ${Object.keys(job.outputs).length}/${job.plan?.parts.length||'—'}`;
  const list=$('split-outputs');list.replaceChildren();
  for(const [index,out] of Object.entries(job.outputs)){
    const row=el('p'),a=el('a',out.name);a.href='split-file?'+new URLSearchParams({run:job.id,index});a.download=out.name;
    row.append(a,el('span',` · 오디오 ${out.audio_tracks}개 · ${out.check}`));list.append(row);
  }
  controls();
}
async function historyView(){
  const query=historySearch.value,value=await api('list',{query,limit:30}),list=$('split-history');
  while(value.runs.length<Math.min(historyLimit,value.total)){const next=await api('list',{query,offset:value.runs.length,limit:30});if(!next.runs.length)break;value.runs.push(...next.runs);}
  if(query!==historySearch.value)return [];list.replaceChildren();
  for(const r of value.runs){const b=el('button',`${r.name} · ${new Date(r.created_at).toLocaleString('ko-KR')} · ${{planning:'경계 확인',ready:'저장 전',running:'분할 중',paused:'중단',error:'확인 필요',complete:'완료',deleting:'삭제 정리 필요'}[r.state]||r.state}`);b.className='secondary'+(r.id===job?.id?' active':'');b.disabled=requesting||active();b.onclick=()=>action(()=>restore(r.id));list.append(b);}
  if(value.total>value.runs.length){const more=el('button',`더 보기 (${value.runs.length}/${value.total})`);more.onclick=()=>{historyLimit+=30;historyView().catch(error);};list.append(more);}
  if(!value.runs.length)list.append(el('p','아직 작업 기록이 없습니다.'));return value.runs;
}
async function restore(id){
  if(!await edits.allow())return;
  job=await api('status',{id});pointDrafts={};$('split-time').value='';setSource(job.source_id,job.source,job.audio_selection);points=[...job.requested];dirty=false;renderPoints();planView();stateView();history.replaceState(null,'','#'+job.id);edits.accept();await historyView();
}
$('split-plan').onclick=()=>action(async()=>{await edits.save();job=await api('plan',{source_id:sourceId,points,audio_selection:splitAudio.selection()});dirty=false;planView();stateView();history.replaceState(null,'','#'+job.id);await historyView();});
$('split-start').onclick=()=>action(async()=>{job=await api('start',{id:job.id,folder:$('split-folder').value});stateView();await historyView();});
$('split-resume').onclick=()=>action(async()=>{job=await api('resume',{id:job.id,folder:$('split-folder').value});stateView();});
$('split-stop').onclick=()=>action(async()=>{job=await api('stop',{id:job.id});job.stopping=true;stateView();});
$('split-open-folder').onclick=()=>action(()=>api('open-folder',{id:job.id}));
async function refresh(){
  if(refreshing||requesting||!job||!active())return;refreshing=true;const id=job.id;
  try{const next=await api('status',{id});if(job?.id!==id)return;const old=job.state;job=next;stateView();if(old!==job.state){planView();await historyView();}}catch(e){error(e);}finally{refreshing=false;}
}
// 같은 탭에서 이동했다 돌아오면 브라우저가 보존한 타이머도 재개한다.
setInterval(refresh,1000);window.addEventListener('pagehide',()=>video.pause());
window.addEventListener('pageshow',()=>refresh());
$('split-help-open').onclick=()=>$('split-help').showModal();$('split-help-close').onclick=()=>$('split-help').close();
const updateDeletion=connectSplitDeletion({api,getJob:()=>job,beforeDelete:()=>video.pause(),onDeleted:async()=>{
  resetSelection();edits.accept();
  $('split-notice').textContent='작업 기록과 생성 파일을 휴지통으로 이동했습니다. 원본 영상은 보존했습니다.';$('split-notice').hidden=false;
  try{await historyView();}catch(e){error(e);}
}});
action(async()=>{const saved=await api('draft-get');draftRevision=saved.revision;edits.accept();if(saved.draft){draftStatus.textContent='복구할 분할 초안이 있습니다. 저장한 초안 불러오기를 누르세요.';}const runs=await historyView();const id=location.hash.slice(1)||runs.find(r=>['planning','running'].includes(r.state))?.id;if(id)await restore(id);});
