import {createStepWorkspace,routeSteps} from './step-workspace.js';
import {createResultNavigation} from './result-flow.js';
import {moveResultTimeline} from './results-layout.js';
import {createProductWorkspace} from './product-workspace.js';
import {createWorkQueue} from './work-queue.js';
import {createMixPage} from './mix-clips.js';
import {mixMenuURL} from './studio-workspace.js';
import {createVideoSplitPage} from './video-split-page.js';
import {createErrorLogUI} from './error-log-ui.js';
import {showPreviewToast} from './preview-toast.js';
import {createAnalysisScopePreview} from './analysis-scope-preview.js';
import {createWorkspaceLayout} from './workspace-layout.js';
import {createWorkspaceStatus} from './workspace-status.js';
import {createExternal} from './context-external.js';
import {vodLabel} from './vod-label.js';
import {createQueue} from './queue.js';
import {createReports} from './reports.js';
import {createPlayer} from './player.js';
import {createMiniPlayer} from './mini-player.js';
import {createReactions} from './reactions.js';
import {createSpeech} from './speech.js';
import {createVoices} from './voices.js';
import {createExplorer} from './explore.js';
import {createContext} from './context.js';
import {connectDeletion} from './project-delete.js';
import {createFolders} from './folders.js';
import {elapsedText} from './task-timing.js';
import {setupVideoQuality,transferMessage,rangeProgressText} from './video-quality.js';
const $=id=>document.getElementById(id);
const active=new Set(['queued','running','downloading','verifying','exporting','stopping']);
const finished=new Set(['complete','empty','unavailable']);
const labels={idle:'준비 전',queued:'준비 중',running:'수집 중',downloading:'수신 중',verifying:'검사 중',exporting:'정리·검사 중',stopping:'중단 중',paused:'중단됨',error:'조치 필요',review:'검증 필요',complete:'완료',empty:'제공 없음',unavailable:'미제공'};
let current=null,page=null,busy=false,polling=false,shell=null,stepWorkspace=null,resultNavigation=null,deletion=null;
const workQueue=createWorkQueue();
const splitPage=createVideoSplitPage({root:$('video-split-page'),workQueue});
$('open-video-split').onclick=event=>{if(event.button||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();go(11);};
const mixPage=createMixPage({api,getRoot:()=>$('root').value});
function setLibraryRoot(root){
 $('root').value=root;
 $('open-mix').href=mixMenuURL(root);
}
const layout=createWorkspaceLayout();
const analysisScope=createAnalysisScopePreview({api,onOpen:(root,vod)=>perform(async()=>{stopPlayback();current=await api('state',{root,vod_id:vod});render();go(3);})});
const workspace=createWorkspaceStatus(layout);
const player=createPlayer();
const context=createContext({api,player,onProject:value=>{current=value;render();},onExternal:()=>{go(8);external.selectMode('clips');}});
const external=createExternal({api,onResult:async(id,mode)=>{if(!current)return;const selected=current.path;const fresh=await api('state',{root:current.root,vod_id:current.vod_id});if(current?.path!==selected)return;current=fresh;render();go(6);await context.openRun(id,mode);}});
const explorer=createExplorer({api,player});
function showExplore(row){go(5);explorer.focus(row);}
const miniPlayer=createMiniPlayer({player,onExplore:showExplore});
const reactions=createReactions({api,onDone:()=>{explorer.refresh();context.refresh();}});
const voices=createVoices({api,player,showExplore,showVideo:()=>go(5),onProject:value=>{current=value;render();}});
const speech=createSpeech({api,player,sceneUsage:context.sceneUsage,showPreview:row=>miniPlayer.open(row),showVoices:range=>{voices.chooseRange(range);go(4);},onProject:value=>{current=value;render();}});
const folders=createFolders({api,onApplied:async()=>{if(current){current=await api('state',{root:current.root,vod_id:current.vod_id});render();}}});
const errorLogs=createErrorLogUI({api,getProject:()=>current});
const reports=createReports({api,getProject:()=>current});
const queue=createQueue({api,onStatus:workspace.setQueue,getRoot:()=>$('root').value,onOpen:(root,vod)=>perform(async()=>{stopPlayback();current=await api('state',{root,vod_id:vod});render();go(2);}),onChanged:()=>list().catch(()=>{}),onLock:locked=>{for(const id of ['root','load-library'])$(id).disabled=locked;}});
const videoQuality=setupVideoQuality({api,getProject:()=>current,onChanged:async value=>{current=value;render();await queue.refresh();await list();}});
shell=createProductWorkspace({api,getRoot:()=>$('root').value,getProject:()=>current,navigate:go,openProject:(project,step)=>perform(async()=>{stopPlayback();current=await api('state',{root:project.root,vod_id:project.vod_id});render();go(step??shell.initialPage(current));}),openJobResult,refreshLibrary:()=>perform(list),onDelete:project=>deletion?.open(project)});
resultNavigation=createResultNavigation({getProject:()=>current,navigate:go,context});
stepWorkspace=createStepWorkspace({layout,getProject:()=>current,navigate:go,enterAnalysis:()=>resultNavigation.enter(),context});
$('open-clip-studio').onclick=()=>{
 if(!current)return;
 const url=new URL('clip-studio.html',location.href),run=$(context.mode()==='clips'?'context-clips-version':'context-version').value;
 const returnPage=document.body.dataset.usePage==='true'?'use':Object.keys(routeSteps).find(key=>routeSteps[key]===page)||'use';
 url.search=new URLSearchParams({root:current.root,library_root:current.library_root||$('root').value||current.root,vod_id:current.vod_id,return_page:returnPage,...(run?{run}:{})});
 stopPlayback();
 location.assign(url.href);
};
function notice(text=''){$('notice').textContent=text;$('notice').hidden=!text;}
async function api(action,data){
 const response=await fetch(`api/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 let value;try{value=await response.json();}catch{throw Error('실행기 응답을 읽지 못했습니다. 실행 중인 주소로 다시 연결하세요');}
 if(!response.ok)throw Error(value.error||'작업 요청에 실패했습니다');return action==='job-resume'?value:workQueue.accept(value);
}
// 상세 조회와 달리 사용자가 결과 보기를 눌렀을 때만 VOD와 결과 버전을 선택한다.
async function openJobResult(request,result,isCurrent){
 const target={root:result.root||request.root,vod_id:result.vod_id||request.vod_id};
 if(!target.root||!target.vod_id)throw Error('이 작업의 결과 위치를 확인할 수 없습니다.');
 let fresh=await api('state',target);if(!isCurrent())return;
 if(result.run&&result.step===3){
  if(!(fresh.speech.versions||[]).some(v=>v.id===result.run))throw Error('이 작업의 전사 결과를 찾을 수 없습니다. 다른 버전은 열지 않았습니다.');
  if(fresh.speech.run!==result.run)fresh=await api('speech-edit',{...target,action:'select',run:result.run});
 }else if(result.run&&result.step===4){
  if(!(fresh.voices.versions||[]).some(v=>v.id===result.run))throw Error('이 작업의 화자 결과를 찾을 수 없습니다. 다른 버전은 열지 않았습니다.');
  if(fresh.voices.run!==result.run)fresh=await api('voices-edit',{...target,action:'select',options:{run:result.run}});
 }else if(result.run&&result.step===6){
  if(!(fresh.context.runs||[]).some(v=>v.id===result.run&&(v.mode||'detail')===result.mode))throw Error('이 작업의 분석 결과를 찾을 수 없습니다. 다른 버전은 열지 않았습니다.');
 }
 if(!isCurrent())return;current=fresh;render();
 if(result.run&&result.step===6){resultNavigation.enter(result.mode);await context.openRun(result.run,result.mode);}
 else go(result.step);
}
function bytes(value){if(!Number.isFinite(value))return '크기 미확인';return value>=1e9?`${(value/1e9).toFixed(2)} GB`:`${(value/1e6).toFixed(1)} MB`;}
function duration(seconds){if(!Number.isFinite(seconds))return '길이 미확인';const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),s=Math.floor(seconds%60);return `${h?`${h}시간 `:''}${m}분 ${s}초`;}
function stopPlayback(){
 miniPlayer.close(false);player.reset();voices.stopPreview();splitPage.pause();mixPage.stop();
 for(const media of document.querySelectorAll('video,audio'))media.pause();
}
window.addEventListener('pagehide',stopPlayback);
document.addEventListener('context-mode-change',stopPlayback);
function go(step,{use=false}={}){delete document.body.dataset.openingWorkspace;step=Math.min(12,Math.max(0,step));stopPlayback();if(step===0&&$('root').value)list().catch(error=>notice(error.message));if(page!==step){window.scrollTo({top:0,left:0,behavior:"instant"});}page=step;['import-panel','download-panel','speech-panel','voices-panel','explore-panel','context-panel','report-panel','external-panel','settings-page'].forEach((id,i)=>$(id).hidden=i===0?![1,2].includes(step):i===1?!current:i+1!==step);[1,2,3,4,5,6,7,8,9].forEach(n=>$(`step${n}`).classList.toggle('current',(n===1&&step===2)||step===n));workspace.navigate(step);$('heading').textContent=['보관함','VOD 등록','자료 관리','전사 검토','화자 검토 · 선택','영상·시간축','장면 탐색','작업 기록','외부 AI 파일 분석','설정','작업센터','영상 나누기','믹스클립'][step];
 player.previewMode(step===3||step===6);if(step!==7)reports.clear();
 if(step===3||step===5||step===6){const target=$(step===3?'speech-video':step===5?'explore-video':context.videoTarget());for(const id of ['video-result','video-unready'])if($(id).parentElement!==target)target.append($(id));}
 if(step===7||step===9)errorLogs.refresh();
 moveResultTimeline(step===6?(context.mode()==='clips'?'context-clips-preview':'context-preview'):null);
 explorer.open(step===3||step===5||step===6);if(step===6)context.refresh();if(step===7)reports.refresh();if(step===8)external.refresh();if(step===9)folders.refresh();shell?.navigate(step);resultNavigation?.navigate(step,{use});splitPage.show(step===11);mixPage.show(step===12);if(page===step)stepWorkspace?.navigate(step,{use});resultNavigation?.update();}
let listRequest=0;
async function list(){const ticket=++listRequest,requested=$('root').value,value=await api('library-catalog',{root:requested});if(ticket!==listRequest||requested!==$('root').value)return;shell.setCatalog(value);$('projects').replaceChildren();if(!value.projects.length){const p=document.createElement('p');p.className='muted';p.textContent=value.message||'저장한 VOD가 없습니다.';$('projects').append(p);}for(const project of value.projects.slice(0,8)){const button=document.createElement('button');button.dataset.path=project.path;button.className='project-item'+(current?.path===project.path?' selected':'');const title=document.createElement('strong'),summary=document.createElement('small');title.textContent=vodLabel(project);summary.textContent=`영상 ${labels[project.tasks.video.state]} · 채팅 ${labels[project.tasks.chat.state]}`;button.append(title,summary);button.onclick=()=>perform(async()=>{stopPlayback();current=await api('state',{root:project.root,vod_id:project.vod_id});render();go(shell.initialPage(current));});const row=document.createElement('div');row.className='project-row';row.append(button);$('projects').append(row);}if(value.projects.length>8){const all=document.createElement('button');all.textContent=`보관함 전체 ${value.projects.length}개 보기`;all.onclick=()=>go(0);$('projects').append(all);}}
async function perform(fn){if(busy)return;busy=true;notice();try{await fn();}catch(error){notice(error.message);}finally{busy=false;}}
function fileURL(kind,key){return `file?${new URLSearchParams({root:current.root,vod_id:current.vod_id,kind,key,...(kind==='video'?{version:current.video_generation||'original'}:{})})}`;}
function render(){
 errorLogs.setProject();
 videoQuality.render(current);
 analysisScope.setProject(current);
 miniPlayer.setProject(current);
 if(current)sessionStorage.setItem('project',JSON.stringify({root:current.root,library_root:$('root').value,vod_id:current.vod_id}));
 for(const [name,state] of [['video',current?.video_replacement?.task||current?.tasks.video],['chat',current?.tasks.chat],['speech',current?.speech],['voices',current?.voices],['context',current?.context]])$(name+'-elapsed').textContent=elapsedText(state);
 $('open-clip-studio').disabled=!current||current.tasks?.video?.state!=='complete';$('delete-project').hidden=!current;$('delete-project').disabled=!!current?.locked;
 if(!current)workspace.update(null);
 if(!current){shell?.update();resultNavigation?.update();stepWorkspace?.update();return;}for(const button of $('projects').querySelectorAll('.project-item')){const selected=button.dataset.path===current.path;button.classList.toggle('selected',selected);if(selected)button.querySelector('small').textContent=`영상 ${labels[current.tasks.video.state]} · 채팅 ${labels[current.tasks.chat.state]}`;}reactions.setProject(current);speech.setProject(current);voices.setProject(current);explorer.setProject(current);context.setProject(current);external.setProject(current);$('step8').disabled=false;$('step6').disabled=false;$('step5').disabled=false;$('step4').disabled=false;$('step2').disabled=false;$('step3').disabled=false;$('project-title').textContent=current.metadata.title;$('project-meta').textContent=`${current.metadata.channel} · ${current.input?(current.input.kind==='range'?'선택 범위 ':'내 영상 ')+duration(current.tasks.video.verification?.duration || 0)+' · VOD '+duration(current.metadata.duration)+' · 시작 '+duration(current.input.start_vod_ms/1000):duration(current.metadata.duration)} · VOD ${current.vod_id}`;$('project-path').textContent=current.path;
 $('lock-note').textContent=current.locked?'사용 중인 자료와 충돌하는 작업만 대기합니다. 독립 작업은 함께 진행할 수 있습니다.':'저장된 프로젝트입니다. 미완료 작업만 이어받을 수 있습니다.';
 const transfers={...current.tasks,video:current.video_replacement?.task||current.tasks.video};
 for(const kind of ['video','chat']){const task=transfers[kind],p=task.progress||{};$(`${kind}-state`).textContent=labels[task.state]||'확인 필요';$(`${kind}-state`).dataset.state=task.state;$(`${kind}-message`).textContent=transferMessage(task);const progress=$(`${kind}-progress`);if(finished.has(task.state))progress.value=100;else if(kind==='video'&&Number.isFinite(p.percent)){progress.value=Math.max(0,Math.min(99,p.percent));}else if(kind==='video'&&(p.total_bytes||p.total_bytes_estimate)){progress.value=Math.min(99,100*(p.downloaded_bytes||p.bytes||0)/(p.total_bytes||p.total_bytes_estimate));}else if(active.has(task.state))progress.removeAttribute('value');else progress.value=0;
  $(`${kind}-detail`).textContent=kind==='video'&&current.download_range&&Number.isFinite(p.percent)&&!finished.has(task.state)?rangeProgressText(p):kind==='video'?`${bytes(p.downloaded_bytes||p.bytes||0)}${p.total_bytes?' / '+bytes(p.total_bytes):p.total_bytes_estimate?' / 약 '+bytes(p.total_bytes_estimate):''}${p.speed?' · '+bytes(p.speed)+'/초':''}${p.fragment_count?' · '+(p.fragment_index||0)+'/'+p.fragment_count+'조각':''}`:`${(p.messages||0).toLocaleString()}건 · ${p.pages||0}페이지${p.last_ms!=null?' · 마지막 '+duration(p.last_ms/1000):''}`;
  $(`${kind}-resume`).disabled=active.has(task.state)||finished.has(task.state)||busy;$(`${kind}-resume`).textContent=task.state==='error'||task.state==='review'?'다시 시도':task.state==='idle'?'시작하기':'이어받기';$(`${kind}-stop`).disabled=!current.owned||!active.has(task.state)||task.state==='stopping';
 }
 $('stop-all').disabled=!current.owned;$('resume-all').disabled=Object.values(transfers).every(t=>finished.has(t.state)||active.has(t.state));
 const ready=current.tasks.video.state==='complete';$('video-result').hidden=!ready;$('video-unready').hidden=ready;
 if(ready){const url=new URL(fileURL('video','playback'),location.href).href;if($('player').src!==url){player.reset();$('player').src=url;}$('original').href=fileURL('video','original');}else if($('player').getAttribute('src')){$('player').removeAttribute('src');$('player').load();}
 const task=current.tasks.chat;$('export-state').textContent=task.message+(task.state==='paused'||task.state==='error'?' · 내보내기가 있으면 마지막으로 보존한 일부 결과입니다.':'');$('export-links').replaceChildren();for(const key of ['json','csv','txt','jsonl'])if(task.assets?.[key]){const a=document.createElement('a');a.href=fileURL('chat',key);a.className='text-link';a.textContent=key.toUpperCase()+' 저장';$('export-links').append(a);}
 workspace.update(current);shell?.update();resultNavigation?.update();stepWorkspace?.update();
}
async function start(kind){if(!current)throw Error('프로젝트를 먼저 열어주세요');if(current.input&&!current.download_range&&current.tasks.video.state!=='complete'&&kind!=='chat'){go(1);notice('이전 로컬 영상의 가져오기가 미완료입니다. 기존 파일은 보존됩니다. 완료된 로컬 영상은 계속 분석할 수 있습니다.');return;}current=await api('start',{root:current.root,vod_id:current.vod_id,format_id:current.format_id,kind});render();go(2);await list();}
$('root').oninput=()=>queue.rootChanged();
$('refresh').onclick=()=>perform(async()=>{await list();await queue.refresh();});
$('load-library').onclick=()=>perform(async()=>{
  const value=await api('pick-path',{kind:'folder'});if(!value.path)return;
  setLibraryRoot(value.path);queue.rootChanged();await list();await queue.refresh();
});
function clearProject(){reports.clear();notice();current=null;errorLogs.setProject();analysisScope.setProject(null);sessionStorage.removeItem('project');for(const i of [2,3,4,5,6,8])$(`step${i}`).disabled=true;player.reset();$('player').removeAttribute('src');$('player').load();reactions.setProject(null);speech.setProject(null);voices.setProject(null);explorer.setProject(null);context.setProject(null);external.setProject(null);workspace.update(null);$('open-clip-studio').disabled=true;$('delete-project').hidden=true;go(1);$('queue-inputs').querySelector('input')?.focus();}
$('new').onclick=()=>{go(1);$('queue-inputs').querySelector('input')?.focus();};
$('queue-add-project').onclick=()=>{if(!current||busy)return;const project=current;go(1);queue.selectSaved(project);};
deletion=connectDeletion({api,beforeOpen:()=>{layout.closeMore();},getProject:()=>current,onDeleted:async removed=>{sessionStorage.removeItem('explore:'+removed.path);if(current?.path===removed.path){stopPlayback();for(const media of document.querySelectorAll("video[src],audio[src]")){media.pause();media.removeAttribute("src");media.load();}clearProject();}await list();go(0);notice('VOD 관련 자료를 모두 휴지통으로 이동했습니다. 공용 모델과 다른 VOD는 유지됩니다.');}});
for(const kind of ['video','chat']){$(`${kind}-resume`).onclick=()=>perform(()=>start(kind));$(`${kind}-stop`).onclick=()=>perform(async()=>{current=await api('stop',{root:current.root,vod_id:current.vod_id,kind});render();});}
$('resume-all').onclick=()=>perform(()=>start('all'));$('stop-all').onclick=()=>perform(async()=>{current=await api('stop',{root:current.root,vod_id:current.vod_id,kind:'all'});render();});
$('step1').onclick=()=>go(current?2:1);$('step2').onclick=()=>go(2);
$('step3').onclick=$('show-speech').onclick=()=>go(3);
$('step4').onclick=()=>go(4);
$('step5').onclick=$('show-results').onclick=()=>go(5);
$('voices-next-step').onclick=()=>go(5);
$('step6').onclick=()=>go(6);$('step7').onclick=()=>go(7);$('step8').onclick=()=>{if(page===6)external.selectMode(context.mode());go(8);};$('step9').onclick=()=>go(9);
setInterval(()=>queue.refresh(),2000);
setInterval(async()=>{if(page===9)await folders.refresh();if(!current||polling||busy)return;polling=true;const selected=current.path;try{const fresh=await api('state',{root:current.root,vod_id:current.vod_id});if(current?.path===selected){const changed=JSON.stringify(current.tasks)!==JSON.stringify(fresh.tasks);current=fresh;render();if(changed)await list();}}catch(error){notice(error.message);}finally{polling=false;}},1000);
const entryQuery=new URLSearchParams(location.search);
const entryStep=routeSteps[location.hash.slice(1)];
const globalEntry=[0,1,9,10,11,12].includes(entryStep);
(async()=>{
 try{
  const menuRoot=globalEntry&&entryQuery.get('library_root');
  const saved=menuRoot?null:entryQuery.has('root')&&entryQuery.has('vod_id')
   ?{root:entryQuery.get('root'),library_root:entryQuery.get('library_root'),vod_id:entryQuery.get('vod_id')}:JSON.parse(sessionStorage.getItem('project')||'null');
  const needsLibraryLookup=globalEntry&&saved&&!saved.library_root;
  const knownRoot=menuRoot||saved?.library_root||saved?.root;
  if(knownRoot)setLibraryRoot(knownRoot);
  if(globalEntry&&knownRoot&&!needsLibraryLookup)go(entryStep);
  else if(location.hash==='#use'&&saved?.vod_id)stepWorkspace.previewUse(saved.vod_id);
  else document.body.dataset.openingWorkspace='true';

  const config=await (await fetch('api/config')).json();
  showPreviewToast(config.annotation_preview===true);folders.set(config.folders);
  if(!$('root').value)setLibraryRoot(config.root);
  if(page===null&&globalEntry&&!needsLibraryLookup)go(entryStep);
  if(page===null&&saved&&(!globalEntry||needsLibraryLookup)){
   const library=$('root').value;
   let project;
   try{project=await api('state',saved);}catch(error){if(page===null)throw error;}
   if(page===null&&project&&!current&&library===$('root').value){
    if(!saved.library_root&&project.library_root)setLibraryRoot(project.library_root);
    if(!globalEntry){
     current=project;render();
     if(page===null&&!applyRoute())go(shell.initialPage(current));
    }
   }
  }
  if(page===null&&!applyRoute())go(0);
  if(page!==0)await list();
  await queue.refresh();
  if(!config.media_tools)notice('FFmpeg와 ffprobe를 찾지 못했습니다. 영상 다운로드 전 설치 경로를 확인하세요.');
 }catch(error){
  if(page===null)go(0);
  notice('실행기에 연결하지 못했습니다. '+error.message);
 }
})();

function applyRoute(){
 const route=location.hash.slice(1);
 if(route==='use'&&current){stepWorkspace.showUse();return true;}
 const step=routeSteps[route];
 if(step==null||!current&&![0,1,9,10,11,12].includes(step))return false;
 go(step);return true;
}
window.addEventListener('hashchange',applyRoute);
