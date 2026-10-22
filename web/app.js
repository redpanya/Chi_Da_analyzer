import {createExternal} from './context-external.js';
import {vodLabel} from './vod-label.js';
import {createQueue} from './queue.js';
import {createReports} from './reports.js';
import {connectHelp} from './help.js';
import {createPlayer} from './player.js';
import {createReactions} from './reactions.js';
import {createSpeech} from './speech.js';
import {createVoices} from './voices.js';
import {createExplorer} from './explore.js';
import {createContext} from './context.js';
import {connectDeletion} from './project-delete.js';
import {createFolders} from './folders.js';
import {elapsedText} from './task-timing.js';
const $=id=>document.getElementById(id);
const active=new Set(['queued','running','downloading','verifying','exporting','stopping']);
const finished=new Set(['complete','empty','unavailable']);
const labels={idle:'준비 전',queued:'준비 중',running:'수집 중',downloading:'수신 중',verifying:'검사 중',exporting:'정리·검사 중',stopping:'중단 중',paused:'중단됨',error:'조치 필요',review:'검증 필요',complete:'완료',empty:'제공 없음',unavailable:'미제공'};
let current=null,page=1,busy=false,polling=false;
const help=connectHelp();
const player=createPlayer();
const context=createContext({api,player,onProject:value=>{current=value;render();}});
const external=createExternal({api,onResult:async(id,mode)=>{if(!current)return;const selected=current.path;const fresh=await api('state',{root:current.root,vod_id:current.vod_id});if(current?.path!==selected)return;current=fresh;render();go(6);context.openRun(id,mode);}});
const explorer=createExplorer({api,player});
function showExplore(row){go(5);explorer.focus(row);}
const reactions=createReactions({api,onDone:()=>{explorer.refresh();context.refresh();}});
const voices=createVoices({api,player,showExplore,showVideo:()=>go(5),onProject:value=>{current=value;render();}});
const speech=createSpeech({api,player,showExplore,showVoices:range=>{voices.chooseRange(range);go(4);},showVideo:()=>go(5),onProject:value=>{current=value;render();}});
const folders=createFolders({api,onApplied:async()=>{if(current){current=await api('state',{root:current.root,vod_id:current.vod_id});render();}}});
const reports=createReports({api,getProject:()=>current});
const queue=createQueue({api,getRoot:()=>$('root').value,onOpen:(root,vod)=>perform(async()=>{current=await api('state',{root,vod_id:vod});render();go(2);}),onChanged:()=>list().catch(()=>{}),onLock:locked=>{for(const id of ['root','load-library'])$(id).disabled=locked;}});
function notice(text=''){$('notice').textContent=text;$('notice').hidden=!text;}
async function api(action,data){
 const response=await fetch(`api/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 let value;try{value=await response.json();}catch{throw Error('실행기 응답을 읽지 못했습니다. 실행 중인 주소로 다시 연결하세요');}
 if(!response.ok)throw Error(value.error||'작업 요청에 실패했습니다');return value;
}
function bytes(value){if(!Number.isFinite(value))return '크기 미확인';return value>=1e9?`${(value/1e9).toFixed(2)} GB`:`${(value/1e6).toFixed(1)} MB`;}
function duration(seconds){if(!Number.isFinite(seconds))return '길이 미확인';const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),s=Math.floor(seconds%60);return `${h?`${h}시간 `:''}${m}분 ${s}초`;}
function go(step){step=Math.min(8,Math.max(1,step));if(page!==step){player.clearRange();voices.stopPreview();}page=step;['import-panel','download-panel','speech-panel','voices-panel','explore-panel','context-panel','report-panel','external-panel'].forEach((id,i)=>$(id).hidden=i+1!==step);[1,2,3,4,5,6,7,8].forEach(n=>$(`step${n}`).classList.toggle('current',step===n));$('heading').textContent=['VOD 리스트 등록','가져오기 진행','음성 추출·전사','화자 구분 (선택)','통합 분석·재생','AI 문맥 정리','리포트','외부 AI 파일 분석'][step-1];
 help.setPage(step);if(step!==7)reports.clear();
 if(step===5||step===6){const target=$({5:'explore-video',6:'context-video'}[step]);for(const id of ['video-result','video-unready'])if($(id).parentElement!==target)target.append($(id));}
 explorer.open(step===5);if(step===6)context.refresh();if(step===7)reports.refresh();if(step===8)external.refresh();}
async function list(){const requested=$('root').value,projects=await api('projects',{root:requested});if(requested!==$('root').value)return;$('projects').replaceChildren();if(!projects.length){const p=document.createElement('p');p.className='muted';p.textContent='이 폴더에 저장한 VOD가 없습니다.';$('projects').append(p);}for(const project of projects){const button=document.createElement('button');button.dataset.path=project.path;button.className='project-item'+(current?.path===project.path?' selected':'');const title=document.createElement('strong'),summary=document.createElement('small');title.textContent=vodLabel(project);summary.textContent=`영상 ${labels[project.tasks.video.state]} · 채팅 ${labels[project.tasks.chat.state]}`;button.append(title,summary);button.onclick=()=>perform(async()=>{current=await api('state',{root:project.root,vod_id:project.vod_id});render();go(2);});const row=document.createElement('div');row.className='project-row';const add=document.createElement('button');add.className='subtle project-queue-add';add.textContent='목록 등록';add.setAttribute('aria-label',project.metadata.title+' 목록 등록');add.onclick=()=>{if(requested!==$('root').value){notice('보관함이 바뀌었습니다. 폴더 확인 후 다시 선택하세요.');return;}go(1);queue.selectSaved(project);};row.append(button,add);$('projects').append(row);}}
async function perform(fn){if(busy)return;busy=true;notice();try{await fn();}catch(error){notice(error.message);}finally{busy=false;}}
function fileURL(kind,key){return `file?${new URLSearchParams({root:current.root,vod_id:current.vod_id,kind,key})}`;}
function render(){
 help.setProject(current?.path);
 if(current)sessionStorage.setItem('project',JSON.stringify({root:current.root,vod_id:current.vod_id}));
 for(const [name,state] of [['video',current?.tasks.video],['chat',current?.tasks.chat],['speech',current?.speech],['voices',current?.voices],['context',current?.context]])$(name+'-elapsed').textContent=elapsedText(state);
 $('delete-project').hidden=!current;$('delete-project').disabled=!!current?.locked;
 if(!current)return;for(const button of $('projects').querySelectorAll('.project-item')){const selected=button.dataset.path===current.path;button.classList.toggle('selected',selected);if(selected)button.querySelector('small').textContent=`영상 ${labels[current.tasks.video.state]} · 채팅 ${labels[current.tasks.chat.state]}`;}reactions.setProject(current);speech.setProject(current);voices.setProject(current);explorer.setProject(current);context.setProject(current);external.setProject(current);$('step8').disabled=false;$('step6').disabled=false;$('step5').disabled=false;$('step4').disabled=false;$('step2').disabled=false;$('step3').disabled=false;$('project-title').textContent=current.metadata.title;$('project-meta').textContent=`${current.metadata.channel} · ${current.input?'내 영상 '+duration(current.tasks.video.verification?.duration || 0)+' · VOD '+duration(current.metadata.duration)+' · 시작 '+duration(current.input.start_vod_ms/1000):duration(current.metadata.duration)} · VOD ${current.vod_id}`;$('project-path').textContent=current.path;
 $('lock-note').textContent=current.analysis_running?'저장된 채팅을 분석 중입니다. 수집 자료는 유지됩니다.':current.locked?(current.owned?'자료를 안전하게 쓰는 중입니다. 이 VOD의 중복 시작은 차단됩니다.':(current.context?.owned||current.voices?.owned||current.speech?.owned?'이 앱에서 영상·음성 파생 파일을 처리하고 있습니다. 다른 작업은 완료 또는 중단 후 시작하세요.':'다른 실행기가 이 VOD를 사용 중입니다. 여기서는 결과만 확인할 수 있습니다.')):'저장된 프로젝트입니다. 미완료 작업만 이어받을 수 있습니다.';
 for(const kind of ['video','chat']){const task=current.tasks[kind],p=task.progress||{};$(`${kind}-state`).textContent=labels[task.state]||'확인 필요';$(`${kind}-state`).dataset.state=task.state;$(`${kind}-message`).textContent=task.message;const progress=$(`${kind}-progress`);if(finished.has(task.state))progress.value=100;else if(kind==='video'&&(p.total_bytes||p.total_bytes_estimate)){progress.value=Math.min(99,100*(p.downloaded_bytes||p.bytes||0)/(p.total_bytes||p.total_bytes_estimate));}else if(active.has(task.state))progress.removeAttribute('value');else progress.value=0;
  $(`${kind}-detail`).textContent=kind==='video'?`${bytes(p.downloaded_bytes||p.bytes||0)}${p.total_bytes?' / '+bytes(p.total_bytes):p.total_bytes_estimate?' / 약 '+bytes(p.total_bytes_estimate):''}${p.speed?' · '+bytes(p.speed)+'/초':''}${p.fragment_count?' · '+(p.fragment_index||0)+'/'+p.fragment_count+'조각':''}`:`${(p.messages||0).toLocaleString()}건 · ${p.pages||0}페이지${p.last_ms!=null?' · 마지막 '+duration(p.last_ms/1000):''}`;
  $(`${kind}-resume`).disabled=(current.locked&&!current.owned)||active.has(task.state)||finished.has(task.state)||busy;$(`${kind}-resume`).textContent=task.state==='error'||task.state==='review'?'다시 시도':task.state==='idle'?'시작하기':'이어받기';$(`${kind}-stop`).disabled=!current.owned||!active.has(task.state)||task.state==='stopping';
 }
 $('stop-all').disabled=!current.owned;$('resume-all').disabled=(current.locked&&!current.owned)||Object.values(current.tasks).every(t=>finished.has(t.state)||active.has(t.state));
 const ready=current.tasks.video.state==='complete';$('video-result').hidden=!ready;$('video-unready').hidden=ready;
 if(ready){const url=new URL(fileURL('video','playback'),location.href).href;if($('player').src!==url){player.reset();$('player').src=url;}$('original').href=fileURL('video','original');}else if($('player').getAttribute('src')){$('player').removeAttribute('src');$('player').load();}
 const task=current.tasks.chat;$('export-state').textContent=task.message+(task.state==='paused'||task.state==='error'?' · 내보내기가 있으면 마지막으로 보존한 일부 결과입니다.':'');$('export-links').replaceChildren();for(const key of ['json','csv','txt','jsonl'])if(task.assets?.[key]){const a=document.createElement('a');a.href=fileURL('chat',key);a.className='text-link';a.textContent=key.toUpperCase()+' 저장';$('export-links').append(a);}
}
async function start(kind){if(!current)throw Error('프로젝트를 먼저 열어주세요');if(current.input&&current.tasks.video.state!=='complete'&&kind!=='chat'){go(1);notice('이전 로컬 영상의 가져오기가 미완료입니다. 기존 파일은 보존됩니다. 완료된 로컬 영상은 계속 분석할 수 있습니다.');return;}current=await api('start',{root:current.root,vod_id:current.vod_id,format_id:current.format_id,kind});render();go(2);await list();}
$('root').oninput=()=>queue.rootChanged();
$('load-library').onclick=$('refresh').onclick=()=>perform(async()=>{await list();await queue.refresh();});
function clearProject(){reports.clear();help.setProject(null);notice();current=null;sessionStorage.removeItem('project');for(const i of [2,3,4,5,6,8])$(`step${i}`).disabled=true;player.reset();$('player').removeAttribute('src');$('player').load();reactions.setProject(null);speech.setProject(null);voices.setProject(null);explorer.setProject(null);context.setProject(null);external.setProject(null);$('delete-project').hidden=true;go(1);$('queue-inputs').querySelector('input')?.focus();}
$('new').onclick=clearProject;
connectDeletion({api,beforeOpen:help.close,getProject:()=>current,onDeleted:async removed=>{sessionStorage.removeItem('explore:'+removed.path);clearProject();await list();notice('VOD 관련 자료를 모두 휴지통으로 이동했습니다. 공용 모델과 다른 VOD는 유지됩니다.');}});
for(const kind of ['video','chat']){$(`${kind}-resume`).onclick=()=>perform(()=>start(kind));$(`${kind}-stop`).onclick=()=>perform(async()=>{current=await api('stop',{root:current.root,vod_id:current.vod_id,kind});render();});}
$('resume-all').onclick=()=>perform(()=>start('all'));$('stop-all').onclick=()=>perform(async()=>{current=await api('stop',{root:current.root,vod_id:current.vod_id,kind:'all'});render();});
$('step1').onclick=()=>go(1);$('step2').onclick=()=>go(2);
$('step3').onclick=$('show-speech').onclick=()=>go(3);
$('step4').onclick=$('show-voices').onclick=()=>go(4);
$('step5').onclick=$('show-results').onclick=$('speech-next-step').onclick=()=>go(5);
$('voices-next-step').onclick=()=>go(5);
$('step6').onclick=()=>go(6);$('step7').onclick=()=>go(7);$('step8').onclick=()=>go(8);
setInterval(()=>queue.refresh(),2000);
setInterval(async()=>{if(page===1)await folders.refresh();if(!current||polling||busy)return;polling=true;const selected=current.path;try{const fresh=await api('state',{root:current.root,vod_id:current.vod_id});if(current?.path===selected){const changed=JSON.stringify(current.tasks)!==JSON.stringify(fresh.tasks);current=fresh;render();if(changed&&!fresh.locked)await list();}}catch(error){notice(error.message);}finally{polling=false;}},1000);
(async()=>{try{const config=await (await fetch('api/config')).json();folders.set(config.folders);const saved=JSON.parse(sessionStorage.getItem('project')||'null');$('root').value=saved?.root||config.root;await list();await queue.refresh();if(saved){current=await api('state',saved);render();go(2);}if(!config.media_tools)notice('FFmpeg와 ffprobe를 찾지 못했습니다. 영상 다운로드 전 설치 경로를 확인하세요.');}catch(error){notice('실행기에 연결하지 못했습니다. '+error.message);}})();
