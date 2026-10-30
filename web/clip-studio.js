import {createStudioInspector} from './studio-inspector.js';
import {createStudioTools} from './clip-studio-tools.js';
import {timecode} from './player.js';
import {commentTimeText} from './context-comment-model.js';
import {collectRanges,editRange,rangeError,sortedRanges,totalLength,captionPreviewTarget} from './clip-studio-model.js';

const $=id=>document.getElementById(id),video=$('studio-video');
const node=(tag,text='',cls='')=>{const el=document.createElement(tag);el.textContent=text;el.className=cls;return el;};
let project=null,origin=0,duration=0,rows=[],active=null,loadId=0,manualId=0,onlyPicked=false,sequence=null,ratio='original',mediaReady=false;
const chosen=new Map();
let rangeDrafts={};
function rememberRange(){if(!active)return;rangeDrafts[active.id]={title:$('range-title').value,start:$('range-start').value,end:$('range-end').value};editor?.selectionChanged();}
for(const id of ['range-title','range-start','range-end'])$(id).addEventListener('input',rememberRange);
let editor=null;
const tabs=['range','frame','caption','export'];
const inspector=createStudioInspector();
const notice=text=>{$('studio-notice').textContent=text;$('studio-notice').hidden=!text;};
const playerNotice=text=>$('player-notice').textContent=text;
const identity=()=>({root:project.root,vod_id:project.vod_id});
async function api(action,data){
  const response=await fetch('api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const value=await response.json();if(!response.ok)throw Error(value.error||'자료를 불러오지 못했습니다.');return value;
}
function showTab(name,focus=false){
  for(const key of tabs){$('panel-'+key).hidden=key!==name;$('tab-'+key).setAttribute('aria-selected',String(key===name));$('tab-'+key).tabIndex=key===name?0:-1;}
  inspector.setTab(name);if(name==='export')renderExport();if(focus)$('tab-'+name).focus();
}
for(const name of tabs){
  $('tab-'+name).onclick=()=>showTab(name);
  $('tab-'+name).onkeydown=event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();const i=tabs.indexOf(name),next=event.key==='Home'?0:event.key==='End'?3:(i+(event.key==='ArrowLeft'?3:1))%4;showTab(tabs[next],true);
  };
}
function currentRows(){
  const query=$('source-search').value.trim().toLocaleLowerCase();
  return (onlyPicked?sortedRanges(chosen.values()):rows).filter(row=>row.title.toLocaleLowerCase().includes(query));
}
function renderList(){
  const list=$('source-list'),position=list.scrollTop;list.replaceChildren();
  for(const row of currentRows()){
    const card=node('article','','source-card'+(active?.id===row.id?' active':''));
    const check=document.createElement('input');check.type='checkbox';check.checked=chosen.has(row.id);check.setAttribute('aria-label',row.title+' 담기');
    check.onchange=()=>{stopSequence();if(check.checked)chosen.set(row.id,row);else chosen.delete(row.id);renderSelection();renderList();};
    const button=node('button');button.append(node('strong',row.title),node('time',`${timecode(row.start_ms)} → ${timecode(row.end_ms)}`));
    if(row.failed)button.append(node('small','요약 실패 · 영상으로 확인'));button.onclick=()=>selectRow(row);
    card.append(check,button);list.append(card);
  }
  if(!list.children.length)list.append(node('p',onlyPicked?'아직 담은 구간이 없습니다. 전체 문맥에서 체크해 주세요.':rows.length?'검색 결과가 없습니다.':'문맥 결과가 없어도 구간을 직접 추가할 수 있습니다.','small'));
  list.scrollTop=position;
}
function renderSelection(){
  const selected=sortedRanges(chosen.values());
  for(const id of ['picked-count','assembly-count'])$(id).textContent=selected.length;
  $('footer-count').textContent=`${selected.length}개 구간 선택`;$('total-length').textContent='합계 '+timecode(totalLength(selected));
  $('review-export').disabled=$('clear-picked').disabled=!selected.length;$('play-sequence').disabled=!selected.length||!mediaReady;
  const list=$('assembly-list'),scroll=list.scrollLeft;list.replaceChildren();
  for(const [i,row] of selected.entries()){
    const card=node('div','','assembly-item'),button=node('button','','assembly-select');
    button.setAttribute('aria-pressed',String(active?.id===row.id));button.append(node('strong',`${i+1}. ${row.title}`),node('small',`${timecode(row.start_ms)} · ${timecode(row.end_ms-row.start_ms)}`));button.onclick=()=>selectRow(row);
    const remove=node('button','×','assembly-remove');remove.type='button';remove.title='담은 구간에서 제거';remove.setAttribute('aria-label',`${row.title} 담은 구간에서 제거`);
    remove.onclick=()=>{
      if(sequence)video.pause();stopSequence();chosen.delete(row.id);renderSelection();renderList();
      const next=$('assembly-list').querySelectorAll('.assembly-select');(next[Math.min(i,next.length-1)]||$('show-all')).focus();
      playerNotice('담은 구간에서 제거했습니다. 원본과 문맥 결과는 유지됩니다.');
    };
    card.append(button,remove);list.append(card);
  }
  if(!selected.length)list.append(node('p','왼쪽 목록에서 원하는 문맥을 체크하세요.','small'));
  list.scrollLeft=scroll;renderExport();editor?.selectionChanged();
}
function fields(){
  for(const id of ['range-title','range-start','range-end','apply-range','pad-three','pad-five','reset-range'])$(id).disabled=!active;
  for(const id of ['mark-start','mark-end','toggle-play','back-three','forward-three','preview-scrub'])$(id).disabled=!active||!mediaReady;
  $('range-error').textContent='';
  if(!active)return;
  $('range-title').value=active.title;$('range-start').value=commentTimeText(active.start_ms);$('range-end').value=commentTimeText(active.end_ms);
  const draft=rangeDrafts[active.id];if(draft){$('range-title').value=draft.title;$('range-start').value=draft.start;$('range-end').value=draft.end;$('range-error').textContent='입력 중인 값입니다. 구간에 적용해야 출력에 반영됩니다.';}
  $('active-title').textContent=active.title;$('active-description').textContent=active.description||'클립의 제목·구간을 수정한 뒤 편집 초안을 저장하세요.';
  $('range-duration').textContent=`선택 길이 ${timecode(active.end_ms-active.start_ms)} · 원본 VOD 시각 기준`;
  $('preview-scrub').min=(active.start_ms-origin)/1000;$('preview-scrub').max=(active.end_ms-origin)/1000;
  $('scrub-start').textContent=timecode(active.start_ms);$('scrub-end').textContent=timecode(active.end_ms);
}
function selectRow(row,keepSequence=false){
  if(!keepSequence)stopSequence();active=row;video.pause();fields();renderList();renderSelection();
  if(mediaReady){video.currentTime=(row.start_ms-origin)/1000;updateClock();}
}
function updateClock(){
  $('play-clock').textContent=timecode(origin+video.currentTime*1000);$('preview-scrub').value=video.currentTime;
  $('toggle-play').textContent=video.paused?'▶ 재생':'Ⅱ 일시정지';
}
function stopSequence(){sequence=null;$('play-sequence').textContent='▶ 담은 구간 이어 보기';}
async function play(){try{await video.play();}catch{stopSequence();playerNotice('재생을 시작하지 못했습니다. 재생 버튼을 다시 누르거나 저장 영상을 확인하세요.');}}
function previewCaption(caption){
  if(!mediaReady){playerNotice('영상이 아직 준비되지 않았습니다. 저장 파일과 연결 상태를 확인하세요.');return;}
  const target=captionPreviewTarget(caption,chosen.values(),active,origin,duration);
  if(!target){playerNotice('이 자막과 겹치는 담은 구간이 없습니다. 구간을 다시 확인하세요.');return;}
  stopSequence();if(active?.id!==target.clip.id)selectRow(target.clip);
  video.currentTime=target.seconds;updateClock();playerNotice('자막 시각부터 재생합니다.');void play();
}
video.addEventListener('loadedmetadata',()=>{
  mediaReady=true;$('media-empty').hidden=true;fields();renderSelection();$('mute-video').disabled=false;resizeFrame();
  if(active)video.currentTime=(active.start_ms-origin)/1000;updateClock();
});
video.addEventListener('error',()=>{
  mediaReady=false;stopSequence();fields();renderSelection();$('media-empty').hidden=false;$('media-empty').textContent='영상을 열 수 없습니다. 외장 디스크와 저장 파일을 확인해 주세요.';
});
for(const event of ['play','pause','seeked'])video.addEventListener(event,updateClock);
video.addEventListener('timeupdate',()=>{
  updateClock();if(!active||video.seeking||video.paused)return;
  if(origin+video.currentTime*1000>=active.end_ms){
    video.pause();
    if(sequence){const next=sequence.index+1;if(next<sequence.rows.length){sequence.index=next;selectRow(sequence.rows[next],true);play();return;}stopSequence();playerNotice('담은 구간을 모두 재생했습니다.');}
  }
});
video.addEventListener('ended',()=>{stopSequence();updateClock();});
$('toggle-play').onclick=()=>{if(!active||!mediaReady)return;if(!video.paused){video.pause();stopSequence();return;}const at=video.currentTime*1000+origin;if(at<active.start_ms||at>=active.end_ms-50)video.currentTime=(active.start_ms-origin)/1000;play();};
for(const [id,delta] of [['back-three',-3],['forward-three',3]])$(id).onclick=()=>{stopSequence();video.currentTime=Math.max((active.start_ms-origin)/1000,Math.min((active.end_ms-origin)/1000,video.currentTime+delta));updateClock();};
$('preview-scrub').oninput=()=>{stopSequence();video.currentTime=Number($('preview-scrub').value);updateClock();};
$('mute-video').onclick=()=>{video.muted=!video.muted;$('mute-video').textContent=video.muted?'소리 꺼짐':'소리 켜짐';$('mute-video').setAttribute('aria-pressed',String(video.muted));};
$('volume').oninput=()=>{video.volume=Number($('volume').value)/100;$('volume-value').textContent=$('volume').value+'%';};
$('play-sequence').onclick=()=>{
  if(sequence){video.pause();stopSequence();return;}
  const selected=sortedRanges(chosen.values());if(!selected.length||!mediaReady)return;
  sequence={rows:selected,index:0};$('play-sequence').textContent='■ 이어 보기 중단';selectRow(selected[0],true);play();playerNotice('선택한 구간만 시간순으로 이어 봅니다.');
};
$('clear-picked').onclick=()=>{stopSequence();video.pause();chosen.clear();renderSelection();renderList();};
$('source-search').oninput=renderList;
for(const [id,value] of [['show-all',false],['show-picked',true]])$(id).onclick=()=>{onlyPicked=value;$('show-all').setAttribute('aria-pressed',String(!value));$('show-picked').setAttribute('aria-pressed',String(value));renderList();};

function applyRange(start,end,title=active.title){
  const error=rangeError(start,end,origin,duration);if(error){$('range-error').textContent=error;return;}
  stopSequence();delete rangeDrafts[active.id];Object.assign(active,{start_ms:start,end_ms:end,title:title.trim()||'제목 없는 구간'});selectRow(active);playerNotice('이 화면의 구간에 적용했습니다. 원래 문맥 결과는 유지됩니다.');
}
$('range-form').onsubmit=event=>{event.preventDefault();if(!active)return;try{const value=editRange($('range-start').value,$('range-end').value,origin,duration);applyRange(value.start_ms,value.end_ms,$('range-title').value);}catch(error){$('range-error').textContent=error.message;}};
$('mark-start').onclick=()=>{$('range-start').value=timecode(origin+video.currentTime*1000);rememberRange();};
$('mark-end').onclick=()=>{$('range-end').value=timecode(origin+video.currentTime*1000);rememberRange();};
for(const [id,seconds] of [['pad-three',3],['pad-five',5]])$(id).onclick=()=>applyRange(Math.max(origin,active.start_ms-seconds*1000),Math.min(origin+duration,active.end_ms+seconds*1000));
$('reset-range').onclick=()=>applyRange(active.original_start,active.original_end);
$('add-range').onclick=()=>{
  if(!duration)return;const start=Math.floor(Math.max(origin,Math.min(origin+duration-1000,origin+video.currentTime*1000))/1000)*1000,end=Math.min(origin+duration,start+30000);
  const row={id:'manual-'+(++manualId),run:null,title:'직접 선택한 구간 '+manualId,start_ms:start,end_ms:end,original_start:start,original_end:end,description:'시작과 끝을 직접 지정한 구간입니다.'};
  rows.push(row);chosen.set(row.id,row);selectRow(row);showTab('range');
};

function resizeFrame(){
  const stage=$('preview-stage'),frame=$('preview-frame'),sourceRatio=video.videoWidth/video.videoHeight||16/9;
  const aspect=ratio==='original'?sourceRatio:ratio.split(':').reduce((a,b)=>Number(a)/Number(b));
  const width=Math.min(stage.clientWidth,stage.clientHeight*aspect),height=width/aspect;
  frame.style.width=width+'px';frame.style.height=height+'px';
  $('preview-format').textContent=ratio==='original'?'원본 비율':ratio+' · '+(ratio==='9:16'?'쇼츠·릴스':'화면 미리보기');
}
new ResizeObserver(resizeFrame).observe($('preview-stage'));
for(const button of document.querySelectorAll('[data-ratio]'))button.onclick=()=>{ratio=button.dataset.ratio;for(const b of document.querySelectorAll('[data-ratio]'))b.setAttribute('aria-pressed',String(b===button));resizeFrame();renderExport();};
function framePosition(){video.style.objectFit=$('frame-fit').value;video.style.objectPosition=`${$('frame-x').value}% ${$('frame-y').value}%`;for(const axis of ['x','y']){$('frame-'+axis+'-value').textContent=$('frame-'+axis).value+'%';$('frame-'+axis).disabled=$('frame-fit').value!=='cover';}}
for(const id of ['frame-fit','frame-x','frame-y'])$(id).oninput=framePosition;
$('frame-reset').onclick=()=>{$('frame-x').value=$('frame-y').value=50;framePosition();};
function caption(){
  for(const axis of ['x','y']){const value=Number($('caption-'+axis).value);$('caption-'+axis+'-value').textContent=(value>0?'+':'')+value+'%';}
  const size=Number($('caption-size').value);$('caption-size-value').textContent=size<=18?'작게':size>=28?'크게':'보통';renderExport();
}
for(const id of ['caption-enabled','caption-style','caption-position','caption-size','caption-x','caption-y'])$(id).oninput=caption;
$('caption-reset').onclick=()=>{$('caption-x').value=$('caption-y').value=0;caption();};
function renderExport(){
  const joined=document.querySelector('[name=output-mode]:checked').value==='joined';$('transition').disabled=!joined;
  const values=[['담은 구간',`${chosen.size}개 · 합계 ${timecode(totalLength(chosen.values()))}`],['파일 구성',joined?'합친 영상 1개':`영상 ${chosen.size}개`],['화면 비율',ratio==='original'?'원본':ratio],['해상도',$('export-size').selectedOptions[0].textContent],['자막',$('caption-enabled').checked?'선택 전사 · 스타일 적용':'영상에 입히지 않음'],['편집용 자막',$('sidecar').checked?'별도 파일 포함':'포함 안 함'],['전환',joined?$('transition').selectedOptions[0].textContent:'구간별 저장']];
  $('export-summary').replaceChildren(...values.map(([key,value])=>{const row=node('div');row.append(node('dt',key),node('dd',value));return row;}));
}
for(const el of document.querySelectorAll('[name=output-mode],#transition,#sidecar,#export-size'))el.onchange=renderExport;
$('review-export').onclick=()=>showTab('export',true);
const help={
  intro:['클립 만들기 · 화면 먼저 살펴보기','왼쪽에서 구간을 담고, 가운데 영상으로 확인하고, 오른쪽 설정으로 다듬는 구성입니다.','저장된 영상과 분석 결과를 읽고 별도 파일로 출력합니다. 편집 초안 저장을 누르면 다음 실행에서도 불러올 수 있습니다.'],
  sources:['원하는 장면만 담기','문맥 제목을 누르면 해당 장면으로 이동합니다. 체크한 구간은 아래 목록에 시간순으로 모입니다. 다른 결과 버전으로 바꿔도 이미 담은 구간은 유지합니다.','시작과 끝이 유효한 완료 항목을 불러옵니다. 실패한 요약도 유효한 시간 범위가 있으면 영상으로 검토할 수 있습니다.'],
  range:['원본은 그대로, 구간만 조절','시각은 전체 VOD 기준으로 입력합니다. 제목·시작·끝을 바꾼 뒤 구간 변경 적용을 누르세요. 앞뒤 여유는 현재 구간에 더해집니다.','편집 초안과 출력 영상에만 적용하며 기존 문맥·댓글 목록을 수정하지 않습니다.'],
  frame:['한 화면에서 비율 확인','전체 보이기는 영상 전체를 유지하고 남는 공간을 검게 채웁니다. 화면 채우기는 일부가 잘리는 대신 지정 비율을 채웁니다. 가로·세로 위치로 보일 부분을 조절하세요.','세로 2단은 같은 원본의 두 영역을 위아래로 배치합니다. 숫자로 게임·얼굴 영역을 지정하고 아래 원본의 테두리로 확인하세요. 자동 얼굴 추적은 하지 않습니다.'],
  caption:['자막 스타일 미리보기','선택한 완료 전사의 실제 시각과 교정 내용을 사용합니다. 자막 교정은 클립 편집에만 적용되고 원전사는 보존합니다.','템플릿은 색상·테두리·발광 효과만 바꿉니다. 글꼴은 별도로 선택하고, 사용할 언어를 고르면 기본 문자 지원이 확인된 글꼴만 표시합니다. 글꼴 목록 미리보기에서 모양을 확인한 뒤 선택할 수 있습니다. 폰트를 새로 설치했다면 목록을 다시 불러오세요. 설치 글꼴의 영상 사용 허용 범위는 해당 라이선스를 확인해 주세요.','미세 조정은 화면 크기 기준 %로 이동합니다. 오른쪽·아래가 + 방향이며 화면 밖 글자는 잘릴 수 있습니다. MP4는 같은 합성 방식으로 저장하고 ASS는 글꼴 설치 여부·편집기에 따라 표현이 달라질 수 있습니다. SRT는 시각·글자만 보존합니다.'],
  export:['출력 구성 확인','원본과 기존 결과를 보존하고 별도 MP4로 저장합니다. 작업을 중단하면 완료된 자료부터 이어할 수 있습니다.','합계는 선택 구간 길이의 합입니다. 디졸브 적용 후 실제 출력 길이는 달라지며, 이 미리보기에는 전환 효과를 적용하지 않습니다. 해상도를 키워도 원본의 세부 화질이 복원되지는 않습니다.'],
};
for(const button of document.querySelectorAll('[data-help]'))button.onclick=()=>{const [title,...paragraphs]=help[button.dataset.help];$('help-title').textContent=title;$('help-content').replaceChildren(...paragraphs.map(text=>node('p',text)));$('studio-help').showModal();};
$('help-close').onclick=()=>$('studio-help').close();

async function loadRun(id){
  const request=++loadId;$('source-state').textContent='분석 결과를 불러오는 중…';
  try{
    const result=await api('context-result',{...identity(),run:id});if(request!==loadId)return;
    const value=collectRanges(result,id,origin,duration);rows=value.rows.map(row=>chosen.get(row.id)||row);
    $('source-state').textContent=`${rows.length}개 구간${result.complete?'':' · 완료된 항목부터 표시'}${value.invalid?' · 시간 범위 확인 필요 '+value.invalid+'개 제외':''}`;
    if(!active&&rows.length){chosen.set(rows[0].id,rows[0]);selectRow(rows[0]);}
    renderList();renderSelection();
  }catch(error){if(request===loadId)$('source-state').textContent='불러오기 실패 · '+error.message;}
}
$('source-version').onchange=()=>loadRun($('source-version').value);
async function init(){
  const params=new URLSearchParams(location.search),config=await (await fetch('api/config')).json();
  let selected={root:params.get('root')||config.root,vod_id:params.get('vod_id')};
  if(!selected.vod_id){const projects=await api('projects',{root:selected.root});const candidate=projects.find(p=>p.tasks?.video?.state==='complete');if(!candidate)throw Error('저장된 영상이 없습니다. 분석 화면에서 VOD를 선택한 뒤 다시 열어주세요.');selected={root:candidate.root,vod_id:candidate.vod_id};}
  project=await api('state',selected);origin=Number(project.input?.start_vod_ms)||0;duration=Math.round((project.tasks?.video?.verification?.duration||project.metadata?.duration||0)*1000);
  try{sessionStorage.setItem('project',JSON.stringify(identity()));}catch{/* 브라우저 저장소가 막혀 있어도 미리보기는 계속한다. */}
  $('vod-title').textContent=project.metadata.title;$('vod-title').title=project.metadata.title;$('add-range').disabled=duration<1000;
  const runs=project.context?.runs||[],select=$('source-version');select.replaceChildren(...runs.map(run=>new Option(`${({clips:'클립 후보',timestamps:'타임스탬프',detail:'상세 문맥'})[run.mode||'detail']||'이전 문맥'} · ${run.label||run.title||run.id}`,run.id)));
  select.disabled=!runs.length;
  if(project.tasks?.video?.state==='complete'){
    const url=new URL('file',location.href);url.search=new URLSearchParams({...identity(),kind:'video',key:'playback'});video.src=url.href;
  }else{$('media-empty').textContent='저장된 영상이 준비되면 여기서 재생할 수 있습니다.';}
  if(runs.length){select.value=runs.some(r=>r.id===params.get('run'))?params.get('run'):runs.at(-1).id;await loadRun(select.value);}
  else{select.append(new Option('저장된 분석 결과 없음',''));$('source-state').textContent='분석 결과 없음 · 구간을 직접 추가해 보세요.';renderList();}
  renderSelection();await editor.init(project);
}
editor=createStudioTools({api,identity,video,onCaptionPreview:previewCaption,rangeDrafts:()=>rangeDrafts,restoreRangeDrafts:value=>{rangeDrafts=value;fields();},selection:()=>sortedRanges(chosen.values()),getRatio:()=>ratio,setRatio:value=>{ratio=value;for(const b of document.querySelectorAll('[data-ratio]'))b.setAttribute('aria-pressed',String(b.dataset.ratio===value));resizeFrame();renderExport();},restore:clips=>{chosen.clear();manualId=Math.max(manualId,...clips.map(c=>Number(/^manual-(\d+)$/.exec(c.id||'')?.[1])||0));for(const [i,c] of clips.entries()){const match=rows.find(r=>c.id?r.id===c.id:r.title===c.title&&r.start_ms===c.start_ms&&r.end_ms===c.end_ms);const row={...match,...c,id:c.id||match?.id||'draft-'+i,original_start:match?.original_start??c.start_ms,original_end:match?.original_end??c.end_ms};chosen.set(row.id,row);}rows=rows.map(r=>chosen.get(r.id)||r);if(chosen.size)selectRow([...chosen.values()][0]);else{active=null;fields();renderSelection();renderList();}}});
renderExport();init().catch(error=>{notice(error.message);$('source-state').textContent='자료를 불러오지 못했습니다.';$('media-empty').textContent='보관함 연결을 확인해 주세요.';});
window.addEventListener('pagehide',()=>{video.pause();stopSequence();});
