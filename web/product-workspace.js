import {vodLabel,vodDuration} from './vod-label.js';
import {timecode} from './player.js';
import {elapsedText} from './task-timing.js';
import {createJobDetail,jobDetailKey} from './job-detail.js';
const $=id=>document.getElementById(id);
const node=(tag,text='')=>{const el=document.createElement(tag);el.textContent=text;return el;};
const active=new Set(['queued','running','downloading','verifying','exporting','stopping']);
const labels={idle:'준비 전',queued:'대기',running:'진행 중',downloading:'다운로드 중',verifying:'검사 중',exporting:'정리 중',stopping:'중단 중',paused:'중단됨',error:'확인 필요',review:'확인 필요',complete:'완료',empty:'제공 없음',unavailable:'미제공',cancelled:'취소됨'};
export function projectStatus(p){
 return libraryStatus(p).group;
}
export function libraryStatus(p){
 const speech=p.summaries?.speech;
 const audio=speech?.action==='audio'?speech:{state:speech?.audio_ready?'complete':'idle'};
 const transcript=speech?.action==='transcribe'||speech&&!speech.action&&!('transcript_state' in speech)?speech:{state:speech?.transcript_state||'idle'};
 const rows=[['영상',p.video_replacement?.task||p.tasks?.video],['채팅',p.tasks?.chat],['원음 추출',audio],['전사',transcript],['화자',p.summaries?.voices],['문맥',p.summaries?.context]];
 if(speech?.action==='model'&&speech.state!=='complete')rows.splice(3,0,['전사 모델',speech]);
 const usable=s=>s?.results?.usable;
 const ongoing=rows.find(([,s])=>active.has(s?.state)),review=rows.find(([,s])=>['error','review','paused'].includes(s?.state)&&!usable(s));
 const chosen=ongoing||review||[...rows].reverse().find(([,s])=>s?.state==='complete'||usable(s))||rows[0];
 const [label,state]=chosen;
 function status(s){
  if(active.has(s?.state))return labels[s.state];
  if(usable(s)){
   if(s.results.previous)return '이전 결과 사용 가능';
   if(s.state==='paused'||s.state==='cancelled')return '일부 완료 (중단)';
   if(s.state==='error')return '일부 완료 (작업 실패)';
   if(s.state==='review'||s.results.issues)return '사용 가능 (일부 확인)';
   return s.results.complete?'완료':'일부 결과 사용 가능';
  }
  if(s?.state==='error'&&s.results)return '실패 (결과 없음)';
  return labels[s?.state]||'준비 전';
 }
 const detail=rows.filter(([,s])=>s?.state&&s.state!=='idle'||usable(s)).map(([n,s])=>`${n} ${status(s)}${s.results?.previous?` / 최근 작업 ${labels[s.state]||s.state}`:''}${s.results?.origin==='external'?' / 외부 AI 결과':''}`).join(' / ');
 return {group:ongoing?'working':review?'review':'ready',label:`${label} ${status(state)}`,detail};
}
export function initialProjectPage(p){
 return p.context?.runs?.length?6:p.speech?.run?3:p.tasks?.video?.state==='complete'?5:2;
}
export function projectPageKey(p){
 const root=String(p.root||'').replace(/\\/g,'/').replace(/\/$/,'');
 const key=JSON.stringify([/^[a-z]:/i.test(root)?root.toLowerCase():root,String(p.vod_id),p.download_range?.start_ms??p.input?.start_vod_ms??0,p.download_range?.end_ms??p.input?.end_vod_ms??0]);
 let a=2166136261,b=3335557771;for(const ch of key){a=Math.imul(a^ch.charCodeAt(0),16777619);b=Math.imul(b^ch.charCodeAt(0),2246822519);}
 return [a,b].map(n=>(n>>>0).toString(16).padStart(8,'0')).join('');
}
export function validProjectPage(p,page){
 return page===2||page===3&&!!p.speech?.run||page===4&&!!p.voices?.run||page===5&&p.tasks?.video?.state==='complete'||page===6&&!!p.context?.runs?.length;
}
const pagePreferences={
 read(){try{const saved=document.cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('chida_project_pages='));if(saved)return JSON.parse(decodeURIComponent(saved.slice(20)));}catch{}
  try{return JSON.parse(localStorage.getItem('chida.project-pages'));}catch{return [];}},
 write(rows){const value=JSON.stringify(rows);try{document.cookie='chida_project_pages='+encodeURIComponent(value)+'; Path=/; Max-Age=31536000; SameSite=Strict';}catch{}try{localStorage.setItem('chida.project-pages',value);}catch{}},
};
export function createProjectPageMemory(preferences=pagePreferences){
 const saved=preferences.read();let entries=Array.isArray(saved)?saved.filter(v=>Array.isArray(v)&&/^[a-f0-9]{16}$/.test(v[0])&&Number.isInteger(v[1])).slice(-32):[];
 return {page(p){const value=entries.find(([key])=>key===projectPageKey(p))?.[1];return validProjectPage(p,value)?value:initialProjectPage(p);},
  remember(p,page){if(!p||!validProjectPage(p,page))return;const key=projectPageKey(p);if(entries.at(-1)?.[0]===key&&entries.at(-1)?.[1]===page)return;entries=[...entries.filter(v=>v[0]!==key),[key,page]].slice(-32);preferences.write(entries);}};
}
export function broadcastTime(p){
 const m=p.metadata||{};for(const value of [m.broadcast_at,m.broadcast_date,m.live_open_date,m.liveOpenDate]){if(typeof value!=='string')continue;const parsed=Date.parse(/^\d{8}$/.test(value)?value.replace(/^(\d{4})(\d{2})(\d{2})$/,'$1-$2-$3'):value);if(Number.isFinite(parsed))return parsed;}return null;
}
export function sortLibraryProjects(projects,order='recent'){
 const time=p=>{const value=Date.parse(p.updated_at);return Number.isFinite(value)?value:0;};
 return [...projects].sort((a,b)=>order==='broadcast'?(broadcastTime(b)??-Infinity)-(broadcastTime(a)??-Infinity)||time(b)-time(a):time(b)-time(a));
}
const stageLabels={download:'영상과 채팅',audio:'원음 추출',transcribe:'음성 전사',speech:'음성 전사',diarize:'화자 구분',voices:'화자 구분',reactions:'채팅 반응 분석',context:'AI 문맥',summary:'상세 문맥',detail:'상세 문맥',timestamps:'타임스탬프',clips:'클립 후보'};
const stageLabel=stage=>stageLabels[stage]||stageLabels[String(stage||'').replace(/^context[-_:]/,'')]||'순차 작업';
const stateGroup=state=>active.has(state)||state==='starting'?'active':['error','review','paused','partial','cancelled'].includes(state)?'review':'complete';
const stateLabel=state=>labels[state]||({starting:'준비 중',partial:'일부 처리·확인 필요'})[state]||state;
const jobProjectKey=(root,vod)=>{let path=String(root||'').replace(/\\/g,'/').replace(/\/$/,'');if(/^[a-z]:/i.test(path))path=path.toLowerCase();return JSON.stringify([path,String(vod)]);};
// 다운로드 구간은 저장 루트로 구분하며, 한 VOD의 작업 상태는 같은 행에 모은다.
export function groupedJobs(library={},heavy={},queue={},filter='all'){
 const groups=new Map();
 function append(key,item){groups.get(key)?.items.push(item);}
 for(const p of library.projects||[]){
  const projectKey=jobProjectKey(p.root,p.vod_id);
  groups.set(projectKey,{key:projectKey,title:p.metadata?.title||'제목 없음',project:p,items:[]});
  for(const [label,key] of [['영상','video'],['채팅','chat'],['전사','speech'],['화자 구분','voices'],['AI 문맥','context']]){
  const state=(key==='video'?p.video_replacement?.task:null)||p.tasks?.[key]||p.summaries?.[key];
  if(!state?.state||state.state==='idle')continue;
  const phase=key==='speech'?state.action||'transcribe':key;
  append(projectKey,{id:key,phase,label:stageLabels[phase]||(phase==='model'?'전사 모델':label),state:state.state,group:stateGroup(state.state),message:state.message||'',elapsed:state.timing?elapsedText(state):'',at:state.timing?.finished_ms||Date.parse(state.updated_at)||0,detail:{root:p.root,vod_id:p.vod_id,kind:key}});
  }
  for(const result of p.external_results||[]){
   append(projectKey,{id:'external:'+result.export_id,phase:'external:'+result.mode,label:'외부 AI '+stageLabel(result.mode),state:result.state,group:stateGroup(result.state),at:Date.parse(result.created_at)||0,detail:{root:p.root,vod_id:p.vod_id,kind:'external',id:result.export_id}});
  }
 }
 const aliases={'voices-start':'voices','context-start':'context','video-quality':'video',analyze:'reactions',diarize:'voices',summary:'context',timestamps:'context',clips:'context'};
 for(const item of heavy.items||[]){
  if(item.action==='queue-start' && (item.state!=='queued'||jobProjectKey(item.root,'')!==jobProjectKey(queue.root||library.root,'')))continue;
  const key=item.vod_id?jobProjectKey(item.root,item.vod_id):'heavy:'+item.id;
  if(!item.vod_id)groups.set(key,{key,title:item.title||item.label||'보관함 작업',project:null,items:[]});
  const phase=item.stage||aliases[item.action]||item.action||item.id;
  append(key,{id:'heavy:'+item.id,phase,label:item.label||'대기열 작업',state:item.state,group:stateGroup(item.state),message:item.message||'',at:Date.parse(item.finished_at||item.created_at)||0,cancelId:item.state==='queued'?item.id:null,detail:{kind:'heavy',id:item.id}});
 }
 for(const item of [...(queue.results||[]),...(queue.items||[])]){
  const key=jobProjectKey(item.project_root||queue.root,item.vod),phase=aliases[item.stage]||item.stage||'queue';
  append(key,{id:'queue:'+item.id,phase,label:item.stage?stageLabel(item.stage):'등록 작업',state:item.state,group:stateGroup(item.state),message:item.message||'',at:Date.parse(item.finished_at)||0,detail:{kind:'queue',root:queue.root,id:item.id}});
 }
 const visible=[];
 for(const group of groups.values()){
  const live=group.items.filter(i=>i.group==='active');
  const covers=(job,other)=>other.phase===job.phase||(['start','download','all'].includes(job.phase)&&['video','chat'].includes(other.phase));
  const sourceOrder={queue:0,heavy:1};
  const priority=i=>sourceOrder[i.detail.kind]??2;
  const current=live.filter(i=>i.state==='queued'||priority(i)===2||!live.some(other=>priority(other)>priority(i)&&other.state!=='queued'&&covers(i,other)));
  const needsReview=group.items.filter(i=>i.group==='review'&&(i.detail.kind==='queue'||!group.items.some(other=>other.group!=='review'&&covers(i,other)&&
    (other.group==='active'||other.at>i.at))));
  const completed=group.items.filter(i=>i.group==='complete');
  let rows=current;
  if(filter==='review')rows=needsReview;
  else if(!current.length&&filter!=='active'){
   rows=needsReview;
   if(!rows.length&&completed.length){
    const done=completed.filter(i=>i.state==='complete');
    const last=(done.length?done:completed).reduce((a,b)=>b.at>=a.at?b:a);
    const outputs=done.filter(i=>priority(i)===2||!done.some(other=>priority(other)>priority(i)&&covers(i,other)));
    rows=[{...last,summary:[...new Set(outputs.map(i=>stageLabels[i.phase]||i.label))].join(', ')||last.label+' '+stateLabel(last.state)}];
   }
  }
  if(filter==='complete')rows=rows.filter(i=>i.group==='complete');
  if(rows.length)visible.push({...group,items:rows});
 }
 return visible.sort((a,b)=>Number(b.items[0].group==='active')-Number(a.items[0].group==='active'));
}
export function createProductWorkspace({api,getRoot,getProject,navigate,openProject,openJobResult,refreshLibrary,onDelete}){
 let catalog={projects:[]},page=0,listPage=0,query='',filter='all',order='recent',jobBusy=false,jobSignature='';const pageMemory=createProjectPageMemory();
 const home=node('section');home.id='library-page';home.className='panel library-page';
 home.innerHTML=`<div class="library-searchbar"><input id="library-search" type="search" placeholder="방송 제목·채널·VOD 번호 검색" aria-label="보관함 검색"><select id="library-filter" aria-label="보관함 상태"><option value="all">전체</option><option value="ready">저장된 자료</option><option value="working">진행 기록 있음</option><option value="review">확인 필요</option></select><select id="library-sort" aria-label="보관함 정렬"><option value="recent">최근 작업순</option><option value="broadcast">방송일 최신순</option></select><button id="library-refresh">새로고침</button></div><div class="library-list-heading"><p id="library-health" role="status"></p></div><div id="library-cards"></div><div class="library-pagination"><button id="library-prev">이전</button><span id="library-page-label"></span><button id="library-next">다음</button></div>`;
 const jobs=node('section');jobs.id='jobs-page';jobs.className='panel';jobs.hidden=true;
 jobs.innerHTML=`<div class="library-intro"><div><h2>진행 상태</h2></div><button id="jobs-refresh">새로고침</button></div><label class="jobs-filter">작업 상태<select id="jobs-filter"><option value="all">전체</option><option value="active">실행·대기</option><option value="review">확인 필요·중단</option><option value="complete">완료</option></select></label><p id="jobs-state" role="status"></p><div id="jobs-rows"></div>`;
 document.querySelector('main').append(home,jobs);
 const detailButtons=new Map();let detailProject=null;
 const jobDetail=createJobDetail({api,onResult:openJobResult,onChanged:()=>{jobSignature='';refreshJobs();},onSelection:key=>{
  if(!key)detailProject=null;
  for(const [id,button] of detailButtons){button.setAttribute('aria-expanded',String(id===key));button.closest('.workspace-job-stage').classList.toggle('selected',id===key);}
 }});
 const navigation=node('nav');navigation.className='workspace-navigation';navigation.setAttribute('aria-label','앱 메뉴');
 const homeButton=node('button','보관함'),jobButton=node('button','진행 상태'),searchButton=node('button','빠른 찾기  ⌘ / Ctrl K');
 homeButton.id='nav-library';jobButton.id='nav-jobs';homeButton.setAttribute('appearance','outlined');jobButton.setAttribute('appearance','outlined');searchButton.id='workspace-search-open';
 navigation.append(homeButton,jobButton,searchButton);$('new').before(navigation);homeButton.onclick=()=>navigate(0);jobButton.onclick=()=>navigate(10);
 const filterBar=node('div');filterBar.className='library-filterbar';filterBar.setAttribute('aria-label','보관함 상태');
 for(const [value,label] of [['all','전체'],['working','진행 중'],['review','확인 필요'],['ready','저장된 자료']]){const button=node('button',label);button.dataset.filter=value;button.onclick=()=>{$('library-filter').value=value;$('library-filter').dispatchEvent(new Event('change'));};filterBar.append(button);}
 $('library-filter').hidden=true;$('library-filter').after(filterBar);home.querySelector('.library-list-heading').append($('library-sort'),$('library-refresh'));
 $('library-refresh').onclick=()=>refreshLibrary();
 $('library-search').oninput=e=>{query=e.target.value;listPage=0;renderLibrary();};$('library-filter').onchange=e=>{filter=e.target.value;listPage=0;renderLibrary();};
 $('library-sort').onchange=e=>{order=e.target.value;listPage=0;renderLibrary();};
 $('library-prev').onclick=()=>{listPage--;renderLibrary();home.scrollIntoView({block:'start'});};$('library-next').onclick=()=>{listPage++;renderLibrary();home.scrollIntoView({block:'start'});};
 function matching(value=''){const words=value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);return catalog.projects.filter(p=>words.every(word=>`${p.metadata?.title} ${p.metadata?.channel} ${p.vod_id}`.toLocaleLowerCase().includes(word)));}
 function renderLibrary(){
  const values=sortLibraryProjects(matching(query).filter(p=>filter==='all'||projectStatus(p)===filter),order),pages=Math.max(1,Math.ceil(values.length/24));listPage=Math.max(0,Math.min(listPage,pages-1));
  $('library-health').textContent=catalog.message||({empty:'아직 저장한 VOD가 없습니다. VOD 등록에서 시작하세요.',partial:'일부 등록 정보를 읽지 못했습니다. 아래 자료는 사용할 수 있습니다.'}[catalog.status]||`방송 ${catalog.projects.length}개`);
  for(const button of filterBar.children){const count=catalog.projects.filter(p=>button.dataset.filter==='all'||projectStatus(p)===button.dataset.filter).length;button.setAttribute('aria-pressed',String(filter===button.dataset.filter));button.textContent=({all:'전체',working:'진행 중',review:'확인 필요',ready:'저장된 자료'})[button.dataset.filter]+' '+count;}
  $('library-health').className=['missing','permission','invalid','partial'].includes(catalog.status)?'notice-warning':'hint';
  if(catalog.warnings?.length)$('library-health').textContent+=' '+catalog.warnings.join(' ');
  $('library-cards').replaceChildren();
  for(const p of values.slice(listPage*24,listPage*24+24)){
   const card=node('div');card.className='library-card';
   const open=node('button');open.type='button';open.className='library-open';open.setAttribute('aria-label',vodLabel(p)+' 열기');open.onclick=()=>openProject(p);
   const remove=node('button','삭제');remove.type='button';remove.className='library-delete danger';remove.setAttribute('aria-label',vodLabel(p)+' 삭제');remove.onclick=()=>onDelete(p);
   const titleText=node('span');titleText.className='library-card-heading';const title=node('strong',p.metadata?.title||'제목 없음');title.title=title.textContent;
   const date=broadcastTime(p),range=p.download_range,meta=node('small',(p.metadata?.channel||'채널 정보 없음')+(range?` · ${timecode(range.start_ms)}–${timecode(range.end_ms)} 구간`:'')+(date===null?'':' · '+new Date(date).toLocaleDateString('ko-KR')));titleText.append(title,meta);
   const summary=libraryStatus(p),status=node('span');status.className='library-statuses';status.title=summary.detail;
   const badge=node('span',summary.label);badge.className='state-pill';badge.dataset.state=summary.group;
   const detail=node('small',summary.detail);status.append(badge,detail);
   const duration=vodDuration(p),clock=node('time',Number.isFinite(duration)?timecode(duration*1000):'길이 미확인');
   open.append(titleText,status,clock);card.append(open,remove);$('library-cards').append(card);
  }
  if(!values.length&&catalog.projects.length)$('library-cards').append(node('p','검색·필터에 맞는 VOD가 없습니다.'));
  $('library-page-label').textContent=`${listPage+1} / ${pages}쪽 · ${values.length}개`;$('library-prev').disabled=!listPage;$('library-next').disabled=listPage+1>=pages;
 }
 const palette=node('dialog');palette.className='workspace-palette';palette.setAttribute('aria-label','빠른 찾기');palette.innerHTML='<div class="play-actions"><h2>빠른 찾기</h2><button id="workspace-search-close">닫기</button></div><input id="workspace-search" type="search" aria-label="VOD·메뉴 찾기" placeholder="VOD 제목이나 메뉴 이름 검색"><div id="workspace-search-results"></div>';
 document.body.append(palette);$('workspace-search-close').onclick=()=>palette.close();
 function paletteResults(){const q=$('workspace-search').value.trim();const values=matching(q).slice(0,20);$('workspace-search-results').replaceChildren();for(const [title,step] of [['보관함',0],['VOD 등록',1],['진행 상태',10],['영상 나누기',11],['믹스클립',12],['설정',9]])if(!q||title.includes(q)){const b=node('button',title);b.onclick=()=>{palette.close();navigate(step);};$('workspace-search-results').append(b);}for(const p of values){const b=node('button',vodLabel(p));b.onclick=()=>{palette.close();openProject(p);};$('workspace-search-results').append(b);}}
 searchButton.onclick=()=>{if(document.querySelector('dialog[open]'))return;palette.showModal();paletteResults();$('workspace-search').focus();};$('workspace-search').oninput=paletteResults;
 document.addEventListener('keydown',e=>{if(!e.isComposing&&(e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){if(document.querySelector('dialog[open]')!==palette&&document.querySelector('dialog[open]'))return;e.preventDefault();searchButton.click();}});
 palette.addEventListener('keydown',e=>{if(!['ArrowDown','ArrowUp'].includes(e.key)||e.isComposing)return;const buttons=[...$('workspace-search-results').querySelectorAll('button')];if(!buttons.length)return;e.preventDefault();const i=buttons.indexOf(document.activeElement);buttons[i<0?(e.key==='ArrowDown'?0:buttons.length-1):(i+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length].focus();});
 $('jobs-refresh').onclick=refreshJobs;$('jobs-filter').onchange=()=>{jobSignature='';refreshJobs();};
 async function refreshJobs(){
  if(jobBusy)return;jobBusy=true;const requested=getRoot();try{
   const reads=await Promise.allSettled([api('library-catalog',{root:requested}),api('work-queue',{}),api('queue-status',{root:requested})]);
   if(page!==10||requested!==getRoot())return;
   const [library,heavy,queue]=reads.map(read=>read.status==='fulfilled'?read.value:{}),errors=reads.filter(read=>read.status==='rejected').map(read=>read.reason?.message||'작업 상태 조회 실패');
   if(library.message)errors.push(library.message);
   if(detailProject&&reads[0].status==='fulfilled'&&['ready','empty'].includes(library.status)&&!library.projects.some(p=>jobProjectKey(p.root,p.vod_id)===detailProject))jobDetail.close();
   const filter=$('jobs-filter').value,signature=JSON.stringify([library,heavy,queue,filter,errors]);if(signature===jobSignature)return;jobSignature=signature;
   const groups=groupedJobs(library,heavy,queue,filter),focused=[...detailButtons].find(([,button])=>button===document.activeElement)?.[0];$('jobs-rows').replaceChildren();detailButtons.clear();
   for(const group of groups){
    const row=node('article');row.className='workspace-job-group';const title=node('div');title.className='workspace-job-title';title.append(node('strong',group.title));
    if(group.project){const duration=vodDuration(group.project);title.append(node('small',`VOD ${group.project.vod_id}${Number.isFinite(duration)?' · '+timecode(duration*1000):''}`));}
    const stages=node('div');stages.className='workspace-job-stages';
    for(const item of group.items){
     const stage=node('div');stage.className='workspace-job-stage';stage.dataset.state=item.group;
     const label=node('strong',item.summary?'완료 결과':`${item.label} ${stateLabel(item.state)}`);stage.append(label);
     if(item.summary)stage.append(node('p',item.summary));
     if(item.message&&item.group!=='complete')stage.append(node('p',item.message));
     if(item.elapsed)stage.append(node('small',item.elapsed));
     const controls=node('div');controls.className='workspace-job-actions';
     if(item.cancelId){const cancel=node('button','대기 취소');cancel.onclick=async()=>{cancel.disabled=true;try{await api('work-cancel',{id:item.cancelId});jobSignature='';await refreshJobs();}catch(error){$('jobs-state').textContent=error.message;cancel.disabled=false;}};controls.append(cancel);}
     const open=node('button','상세'),key=jobDetailKey(item.detail);open.type='button';open.setAttribute('aria-label',`${group.title} ${item.label} 상세`);open.setAttribute('aria-controls','job-detail');open.setAttribute('aria-haspopup','dialog');open.setAttribute('aria-expanded',String(key===jobDetail.key()));stage.classList.toggle('selected',key===jobDetail.key());
     open.onclick=()=>{detailProject=group.project?group.key:null;jobDetail.open(item.detail,{opener:open,getOpener:()=>detailButtons.get(key)});};detailButtons.set(key,open);controls.append(open);
     stage.append(controls);stages.append(stage);
    }
    row.append(title,stages);$('jobs-rows').append(row);
   }
   if(focused)detailButtons.get(focused)?.focus({preventScroll:true});
   $('jobs-state').textContent=errors.length?errors.join(' / '):`${groups.length}개 자료`;
   $('jobs-state').className=errors.length?'notice-warning':'hint';
   if(!groups.length)$('jobs-rows').append(node('p','이 상태에 해당하는 작업이 없습니다.'));
  }catch(e){$('jobs-state').textContent=e.message;}finally{jobBusy=false;}
 }
 const appearance=node('section');appearance.className='settings-appearance';appearance.innerHTML=`<h2>화면과 사용성</h2><label>화면 테마<select id="workspace-theme"><option value="system">시스템 설정 따르기</option><option value="light">라이트</option><option value="dark">다크</option></select></label><h3>보관함 저장 공간</h3><button id="storage-read">용량 확인</button><p id="storage-status" role="status"></p><div id="storage-sizes"></div>`;
 $('settings-page').prepend(appearance);window.ChidaTheme?.connect($('workspace-theme'));
 $('storage-read').onclick=async()=>{const button=$('storage-read'),requested=getRoot();button.disabled=true;$('storage-status').textContent='보관함 용량을 계산하는 중…';try{const result=await api('storage-info',{root:requested});if(requested!==getRoot())return;$('storage-sizes').replaceChildren(...Object.entries(result.sizes).map(([key,value])=>node('p',`${key}: ${(value/1024**3).toFixed(2)} GiB`)));$('storage-status').textContent=`남은 공간 ${(result.free/1024**3).toFixed(1)} GiB${result.unreadable?' / 읽지 못한 파일과 폴더 '+result.unreadable+'개':''}`;}catch(e){$('storage-status').textContent=e.message;}finally{button.disabled=false;}};
 for(const [dialogId,sourceId] of [['context-settings','context-external-open'],['clip-settings','context-clips-external']]){const dialog=$(dialogId),source=$(sourceId);if(!dialog||!source)continue;const choice=node('div');choice.className='analysis-method';choice.append(node('span','이 PC에서 Gemma로 분석'));const external=node('button','외부 AI 파일로 작업');external.className='secondary';external.onclick=()=>{dialog.close();source.click();};choice.append(external);dialog.querySelector('.settings-body')?.prepend(choice);}
 const speaker=node('button','화자 검토 · 선택');speaker.onclick=()=>navigate(4);$('speech-panel').querySelector('.result-toolbar').append(speaker);
 for(const [selectId,deleteId] of [['context-version','context-delete'],['context-clips-version','context-clips-delete']]){const toolbar=$(selectId).closest('.result-toolbar'),details=toolbar?.querySelector('.version-details');if(details&&$(deleteId)){const content=node('div');content.className='version-info-popover';content.append(details.querySelector('p'),$(deleteId));details.append(content);}}

 // 처리 단계 ID와 이벤트는 유지하고, 작업 목적에 맞춰 탐색 순서만 정리한다.
 const stepNav=$('step1').parentElement;stepNav.setAttribute('aria-label','선택 VOD의 작업');stepNav.prepend($('step6'),$('step5'),$('step3'));$('step6').textContent='장면 탐색';$('step5').textContent='영상·시간축';$('step3').textContent='전사 검토';$('step1').textContent='자료 관리';$('step4').hidden=true;
 document.querySelector('.brand').onclick=e=>{e.preventDefault();navigate(0);};
 setInterval(()=>{if(page===10)refreshJobs();},5000);
 return {
  initialPage:p=>pageMemory.page(p),
  setCatalog(value){catalog=value;renderLibrary();},
  navigate(step){if(step!==10)jobDetail.close();pageMemory.remember(getProject(),step);page=step;home.hidden=step!==0;jobs.hidden=step!==10;homeButton.setAttribute('variant',step===0?'brand':'neutral');jobButton.setAttribute('variant',step===10?'brand':'neutral');stepNav.hidden=!getProject()||[0,1,7,8,9,10,11,12].includes(step);$('global-jobs').hidden=[0,1,7,8,9,10,11,12].includes(step)||$('global-jobs').hidden;document.body.dataset.workspacePage=String(step);if(step===0)$('workspace-subtitle').textContent='내 컴퓨터의 보관함';if(step===10){$('workspace-subtitle').textContent='다른 VOD를 재생·편집하면서 작업 진행을 확인하세요.';refreshJobs();}},
  update(){if([0,10].includes(page)){$('global-jobs').hidden=true;$('workspace-subtitle').textContent=page===0?'내 컴퓨터의 보관함':'다른 VOD를 재생·편집하면서 작업 진행을 확인하세요.';}}
 };
}
