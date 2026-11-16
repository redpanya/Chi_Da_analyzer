import {enterView} from './workspace-motion.js';
import {bindDesktopSettings} from './desktop-settings.js';
import {createSettingsPanel} from './settings-panel.js';
const $=id=>document.getElementById(id);
const make=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
export const routeSteps={register:1,library:0,jobs:10,split:11,mix:12,settings:9,prepare:2,speech:3,voices:4,explore:5,context:6,report:7,external:8};
export function workspaceDepth({project=false,task=false,register=false}={}){return task&&project?3:project||register||task?2:1;}

// 초기 배치에서 기존 노드를 옮긴다. 폴링은 텍스트·상태만 갱신한다.
export function createStepWorkspace({layout,getProject,navigate,enterAnalysis,context}){
 document.body.classList.add('step-workspace');
 const main=document.querySelector('body>main'),rail=document.querySelector('body>aside');
 rail.classList.add('step-primary');rail.setAttribute('aria-label','기본 메뉴');
 const navigation=rail.querySelector('.workspace-navigation');
 const symbols={new:'M12 5v14M5 12h14','nav-library':'M3 5h18v15H3zM3 9h18M8 5v15','nav-jobs':'M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18m0 4v5l3 2','open-video-split':'M6 6l14 14M6 18L20 4M8 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0M8 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0','open-mix':'M3 5h12v10H3zM8 18h12V9M7 8l4 2-4 2z',step9:'M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z',theme:'M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1'};
 const icon=key=>{const el=make('span','','rail-icon');el.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${symbols[key]}"/></svg>`;return el;};
 for(const [id,label] of [['new','VOD 등록'],['nav-library','보관함'],['nav-jobs','진행 상태'],['open-video-split','영상 나누기'],['open-mix','믹스클립'],['step9','설정']]){
  const button=$(id);button.replaceChildren(icon(id),make('span',label,'rail-label'));button.setAttribute('title',label);button.setAttribute('aria-label',label);button.classList.add('rail-action');
 }
 navigation.replaceChildren($('new'),$('nav-library'),$('nav-jobs'),$('open-video-split'),$('open-mix'));
 const bottom=make('div','','rail-bottom'),theme=make('button','','rail-action');theme.id='rail-theme';theme.type='button';theme.title='화면 테마 전환';theme.setAttribute('aria-label',theme.title);theme.append(icon('theme'),make('span','테마','rail-label'));
 theme.onclick=()=>window.ChidaTheme?.setPreference(window.ChidaTheme.resolved()==='dark'?'light':'dark');bottom.append(theme,$('step9'));rail.append(bottom);
 const selected=make('aside','','selected-vod-rail');selected.id='selected-vod-rail';selected.setAttribute('aria-label','선택한 VOD');
 const selectedTitle=make('strong','','selected-vod-title'),back=make('button','←','rail-back');back.title='보관함으로 돌아가기';back.setAttribute('aria-label',back.title);back.onclick=()=>navigate(0);selected.append(make('small','선택 VOD'),selectedTitle,back);
 const subnav=make('aside','','task-rail');subnav.id='task-rail';subnav.setAttribute('aria-label','현재 작업 메뉴');main.before(selected,subnav);
 const purposes=make('nav','','purpose-tabs');purposes.id='purpose-tabs';purposes.setAttribute('aria-label','선택 VOD의 작업 과정');
 const purposeButtons=[];
 for(const [index,label,fn] of [[0,'준비',()=>navigate(2)],[1,'분석',()=>enterAnalysis()],[2,'작업',()=>showUse()]]){const button=make('button');button.append(make('span',String(index+1),'step-number'),make('span',label));button.onclick=fn;purposes.append(button);purposeButtons.push(button);}
 const header=main.querySelector('header');header.after(purposes);
 const use=make('section','','panel use-page');use.id='use-page';use.hidden=true;
 for(const [title,description,action] of [['클립 만들기','담은 구간·화면·자막을 편집하고 영상으로 저장합니다.',()=>$('open-clip-studio').click()],['외부 AI 파일 분석','자료 내보내기와 결과 가져오기를 진행합니다.',()=>navigate(8)],['결과 리포트 보내기','처리 시간과 오류 기록을 확인하고 리포트를 저장합니다.',()=>navigate(7)]]){const button=make('button','','flow-card');button.append(make('strong',title),make('span',description));button.onclick=action;use.append(button);}
 main.append(use);
 const taskHost=make('section','','task-main');taskHost.id='task-main';taskHost.hidden=true;main.append(taskHost);
 const prep=make('div','','prepare-overview'),prepMain=make('section'),prepNote=make('section','','prepare-note');
 prep.id='prepare-overview';const prepTitle=make('h2','자료 준비');prepMain.append(prepTitle);
 const prepareRows=new Map(),prepList=make('div','','preparation-list');prepMain.append(prepList);
 const download=$('download-panel'),cards=download.querySelector('.cards'),downloadDetail=make('details','','prepare-download-details');downloadDetail.id='prepare-download-details';
 downloadDetail.append(make('summary','영상·채팅 상세 상태'));
 if(cards)downloadDetail.append(cards);
 const oldActions=download.querySelector('.action-row');if(oldActions)downloadDetail.append(oldActions);
 for(const [id,title,detail] of [
  ['download','영상/채팅','다운로드와 채팅 수집'],['audio','원음 추출','영상에서 오디오 추출'],
  ['speech','음성 전사','오디오를 텍스트로 변환'],['voices','화자 구분','선택 단계 (생략 가능)'],['context','AI 문맥','대화 주제와 장면 탐색']]){
  const row=make('div','','prepare-row'),mark=make('span','○','prepare-status'),text=make('div'),description=make('small',detail),button=make('button','확인','secondary');button.setAttribute('aria-label',title+' 상태 확인');text.append(make('strong',title),description);row.append(mark,text,button);prepList.append(row);prepareRows.set(id,{mark,description});
 }
 const results=make('button','분석 결과 열기 →','primary');results.onclick=()=>enterAnalysis();prepMain.append(results);
 prepNote.append(make('h3','처리할 작업'));
 const processing=make('button','처리 설정','secondary');processing.id='prepare-processing';processing.onclick=()=>openPreparation('download',processing);
 prepNote.append(processing);const scope=download.querySelector('.analysis-scope-preview');
 prep.append(prepMain,prepNote);download.prepend(prep);download.append(downloadDetail);
 const downloadSettings=createSettingsPanel('download-settings','영상·채팅 설정',[downloadDetail,...(scope?[scope]:[])],$('queue-add-project')?[$('queue-add-project')]:[]);
 downloadSettings.note.textContent='완료된 자료는 재사용합니다. 화질 변경과 채팅 이어받기는 해당 작업만 실행합니다.';
 layout.panels.push(downloadSettings);
 // 범위 설정은 별도 패널이므로 현재 설정을 닫은 뒤 기존 열기 동작을 실행한다.
 $('analysis-scope-open')?.addEventListener('click',()=>downloadSettings.close(),{capture:true});
 const prepPanels={download:downloadSettings,audio:layout.audioSettings,speech:layout.speechSettings,voices:layout.voiceSettings,context:layout.contextSettings};
 function openPreparation(kind,button){preparing=true;prepPanels[kind].open(button);}
 for(const [i,kind] of Object.keys(prepPanels).entries()){const button=prepList.children[i].querySelector('button');button.onclick=()=>openPreparation(kind,button);}
 function updatePreparation(){
  const project=getProject();if(!project)return;
  const speech=project.speech||{},inProgress=['queued','running','stopping'].includes(speech.state);
  const audio=speech.action==='audio'&&inProgress?speech:{state:speech.raw_audio||speech.audio?'complete':speech.action==='audio'?speech.state:'idle'};
  const transcript=speech.action==='transcribe'?speech:{state:speech.transcript?.complete?'complete':speech.transcript?'paused':'idle'};
  const states={download:project.video_replacement?.task||project.tasks?.video,audio,speech:transcript,voices:project.voices,context:project.context};
  const names={complete:'완료',idle:'아직 준비하지 않음',error:'확인 필요',review:'확인 필요',paused:'중단됨',running:'진행 중',downloading:'수신 중',queued:'대기',verifying:'검사 중',exporting:'결과 정리 중',stopping:'중단 중'};
  for(const [id,{mark,description}] of prepareRows){const task=states[id],state=task?.state||'idle';mark.textContent=state==='complete'?'✓':['error','review','paused'].includes(state)?'!':state==='idle'?'○':'◷';mark.dataset.state=state;description.textContent=id==='download'?`영상 ${names[state]||state} · 채팅 ${names[project.tasks?.chat?.state]||'준비 전'}`:id==='voices'&&state==='idle'?'선택 단계 · 생략 가능':names[state]||state;}
  const signature=[project.path,states.download?.state,project.tasks?.chat?.state].join('|');
  if(downloadDetail.dataset.state!==signature){downloadDetail.dataset.state=signature;downloadDetail.open=true;}
 }


 // 등록 화면은 주소, 옵션, 확인 순서로 진행한다. 실제 등록 버튼과 유효성 검사는 재사용한다.
 const queue=document.querySelector('.queue-section'),address=make('section','','register-address'),confirm=make('section','','register-confirm');
 address.id='register-address';confirm.id='register-confirm';confirm.hidden=true;
 const addressesTitle=$('queue-inputs').previousElementSibling,addRow=$('queue-more').parentElement;
 address.append(make('p','새 VOD · 1 / 3','eyebrow'),make('h2','VOD 주소 입력'),addressesTitle,$('queue-inputs'),addRow);
 const next=make('button','처리할 작업 선택 →','primary');next.id='registration-next';next.onclick=()=>layout.queueSettings.open(next);address.append(next);
 const confirmSummary=make('div','','registration-summary');confirmSummary.id='registration-summary';confirm.append(make('h2','등록 내용 확인'),confirmSummary,$('queue-add'));
 const edit=make('button','← 처리 설정 수정','secondary');edit.onclick=()=>layout.queueSettings.open(edit);confirm.append(edit);
 queue.prepend(address,confirm);
 $('queue-settings-launcher').hidden=true;
 const oldTitle=$('queue-settings-launcher').previousElementSibling;if(oldTitle?.tagName==='H3')oldTitle.hidden=true;
 // 진행 목록은 별도의 관리 화면으로 이동하며 기존 폴링·선택·취소 이벤트를 유지한다.
 const automation=make('section','','registration-queue');automation.id='registration-queue';
 const pendingSettings=make('button','대기 항목 설정 변경','secondary');pendingSettings.onclick=()=>layout.queueSettings.open(pendingSettings);
 automation.append(make('h3','등록된 VOD'),$('queue-status'),pendingSettings,$('queue-list'),$('queue-start').parentElement);
 queue.append(automation);
 for(const heading of queue.querySelectorAll(':scope>h3'))heading.hidden=true;
 const progressLink=make('button','진행 상태에서 목록 보기 →','secondary');progressLink.onclick=()=>navigate(10);confirm.append(progressLink);

 function formPage(section,nodes,actions){
  const columns=make('div','','task-columns'),form=make('section','','form-section'),footer=make('div','','flow-footer');
  form.append(...nodes);columns.append(form);footer.append(...actions);section.append(columns,footer);
 }
 formPage(address,[addressesTitle,$('queue-inputs'),addRow],[next]);
 const addressBack=make('button','이전','secondary');addressBack.onclick=()=>layout.queueSettings.open(addressBack);
 formPage(confirm,[confirmSummary],[addressBack,$('queue-add'),progressLink]);edit.remove();

 let page=0,registration=0,flow=null,path=null,railKey='',preparing=false,settingsTab=0;
 let firstNavigation=true;
 const settings=$('settings-page'),appearance=settings?.querySelector('.settings-appearance'),settingsGroups=[];
 const info=$('app-info'),setUpdateVisible=bindDesktopSettings(info);
 if(appearance){
  const storage=make('section','','form-section'),general=make('section','','form-section'),logs=make('section','','form-section');
  let destination=general;
  for(const child of [...appearance.children]){if(child.tagName==='H3')destination=child.textContent.includes('보관함 저장 공간')?storage:general;destination.append(child);}
  const folders=settings.querySelector('.folder-settings'),errors=$('error-log-enabled')?.closest('section');
  if(folders)storage.prepend(folders);
  if($('compute-settings'))logs.append($('compute-settings'));if(errors)logs.append(errors);
  appearance.remove();settings.append(storage,general,logs);settingsGroups.push(['저장 폴더',storage],['화면·안내',general],['처리·로그',logs]);
  if(info){settings.append(info);settingsGroups.push([window.chidaDesktop?'앱 업데이트':'앱 정보',info]);}
 }
 function renderSettings(animate=false){settingsGroups.forEach(([,node],i)=>node.hidden=i!==settingsTab);setUpdateVisible(page===9 && !info?.hidden);renderRails();if(animate)enterView(settingsGroups[settingsTab]?.[1],0);}
 const panels=[layout.queueSettings,downloadSettings,layout.audioSettings,layout.speechSettings,layout.voiceSettings,layout.contextSettings,layout.clipSettings];
 const names=new Map([[downloadSettings,'영상·채팅'],[layout.queueSettings,'처리 선택'],[layout.audioSettings,'원음 추출'],[layout.speechSettings,'음성 전사'],[layout.voiceSettings,'화자 구분'],[layout.contextSettings,'새 분석'],[layout.clipSettings,'클립 후보 분석']]);
 const group=(parent,nodes)=>{const section=make('section','','task-field-group');section.append(...nodes);parent.append(section);return section;};
 // 설정 화면에서도 원본 폼은 하나만 존재한다. 단계별 그룹만 바꿔 보여준다.
 const groups=new Map();
 for(const panel of [layout.contextSettings,layout.clipSettings]){
  const prefix=panel===layout.contextSettings?'context':'context-clips',body=panel.body;
  const input=$(prefix+'-transcript').closest('fieldset'),background=$(prefix+'-background-form'),thinking=$(prefix+'-thinking').closest('label');
  const controls=[...body.children].filter(node=>node!==panel.note&&node!==input&&node!==background&&node!==thinking);
  const kind=group(body,controls),data=group(body,[input,thinking]),request=group(body,[background]);
  const modes=make('div','','review-tabs');modes.setAttribute('aria-label','진행할 분석 모드');
  for(const [mode,label] of [['detail','상세 문맥'],['timestamps','타임스탬프'],['clips','클립 후보']]){const button=make('button',label);button.type='button';button.dataset.analysisMode=mode;button.onclick=()=>{panel.close();context.selectMode(mode,{allowEmpty:true});(mode==='clips'?layout.clipSettings:layout.contextSettings).open();};modes.append(button);}kind.prepend(modes);
  groups.set(panel,[['분석 방법',kind],['입력 데이터',data],['추가 요청',request]]);
 }
 for(const panel of panels){
  panel.note.hidden=true;
  const columns=make('div','','task-columns');
  panel.body.before(columns);columns.append(panel.body);
  const previous=make('button','이전','secondary task-previous');previous.type='button';panel.footer.prepend(previous);
  previous.onclick=()=>{if(flow?.index>0){flow.index--;renderTask(-1);}else panel.close();};
  const finish=make('button',panel===layout.queueSettings?'등록 내용 확인 →':'다음 →','primary');finish.type='button';finish.className='primary task-next';panel.footer.append(finish);
  finish.onclick=()=>{if(panel===layout.queueSettings){panel.close();showRegistration(2);return;}const list=groups.get(panel)||[];if(flow&&flow.index<list.length-1){flow.index++;renderTask(1);} };
  panel.setPresentation({open(){
   use.hidden=true;flow={panel,index:0};if(panel===layout.queueSettings)registration=1;
   document.body.dataset.taskFlow=panel.dialog.id;taskHost.hidden=false;taskHost.append(panel.dialog);panel.dialog.classList.add('inline-task');panel.dialog.show();renderTask();renderRails();enterView(taskHost,0);
  },closed(){
   panel.dialog.classList.remove('inline-task');document.body.append(panel.dialog);
   if(flow?.panel!==panel)return;flow=null;preparing=false;taskHost.hidden=true;delete document.body.dataset.taskFlow;if(panel===layout.queueSettings&&page===1)showRegistration(0);renderRails();
  }});
 }
 function renderTask(direction=0){
  if(!flow)return;const {panel,index}=flow,list=groups.get(panel)||[];
  for(const button of panel.body.querySelectorAll('[data-analysis-mode]'))button.setAttribute('aria-pressed',String(button.dataset.analysisMode===context.mode()));
  for(const [i,[,node]] of list.entries())node.hidden=i!==index;
  const next=panel.footer.querySelector('.task-next');next.hidden=panel===layout.queueSettings?page!==1:index>=list.length-1;
  if(panel===layout.queueSettings&&$('queue-apply'))$('queue-apply').hidden=page===1;
  for(const id of ['context-generate','context-clips-generate','transcribe']){const button=$(id);if(panel.dialog.contains(button))button.hidden=list.length>0&&index<list.length-1;}
  panel.footer.querySelector('.task-previous').hidden=index===0&&panel!==layout.queueSettings;
  panel.dialog.querySelector('.settings-heading h2').textContent=panel===layout.queueSettings?'처리할 작업 선택':list[index]?.[0]||names.get(panel);
  if(panel===downloadSettings)downloadDetail.open=true;
  if(direction)enterView(list[index]?.[1]||panel.body,direction);renderRails();
 }
 function showRegistration(index,animate=true){const changed=registration!==index;registration=index;address.hidden=index!==0;confirm.hidden=index!==2;
  if(index===2){confirmSummary.replaceChildren();for(const row of $('queue-inputs').children){const value=row.project?.metadata?.title||row.querySelector('input')?.value?.trim();if(value)confirmSummary.append(make('p',value));}confirmSummary.append(make('p',$('queue-selection-summary').textContent),make('p',`다운로드 화질 ${$('queue-height').value}p / 동시 다운로드 ${$('queue-fragments').value}개`));if(!confirmSummary.children.length)confirmSummary.append(make('p','등록할 VOD 주소를 입력하세요.'));}
  renderRails();if(animate&&changed)enterView(index===2?confirm:address,0);
 }
 function showUse(){navigate(6,{use:true});}
 function previewUse(vodId){
  document.body.dataset.openingWorkspace='use';
  selectedTitle.textContent='VOD '+vodId;
  purposeButtons[2].setAttribute('aria-current','step');
  purposes.hidden=use.hidden=false;
  purposes.inert=use.inert=true;
  use.setAttribute('aria-busy','true');
  renderRails();
 }
 function railButton(label,action,current=false,index){const button=make('button','','rail-action');if(index!=null)button.append(make('span',String(index+1),'step-number'));button.append(make('span',label,'rail-label'));button.title=label;if(label.startsWith('←'))button.classList.add('rail-return');button.setAttribute('aria-current',current?'step':'false');button.onclick=action;subnav.append(button);}
 function renderRails(){
  const project=getProject(),pendingUse=use.inert;
  const projectScreen=pendingUse||!!project&&(![0,1,9,10,11,12].includes(page)||!!flow&&flow.panel!==layout.queueSettings);
  header.hidden=projectScreen||page===11||page===12;
  selected.hidden=!projectScreen;if(!pendingUse)selectedTitle.textContent=projectScreen?project.metadata?.title||'선택 VOD':'';selectedTitle.title=selectedTitle.textContent;
  const nextKey=[projectScreen,page,flow?.panel.dialog.id,flow?.index,registration,preparing,settingsTab].join('|');
  if(railKey===nextKey)return;railKey=nextKey;subnav.replaceChildren();
  if(flow){
   const {panel,index}=flow;subnav.append(make('strong',preparing?'자료 준비':names.get(panel),'task-rail-title'));
   if(preparing){
    for(const [kind,label] of [['download','영상/채팅'],['audio','원음 추출'],['speech','음성 전사'],['voices','화자 구분'],['context','AI 문맥']])railButton(label,()=>{if(panel!==prepPanels[kind]){panel.close();openPreparation(kind);}},panel===prepPanels[kind]);
   }else if(panel===layout.queueSettings&&page===1){for(const [i,label] of ['주소 입력','처리 선택','등록 확인'].entries())railButton(label,()=>{if(i===1)return;panel.close();showRegistration(i);},i===1,i);}
   else for(const [i,[label]] of (groups.get(panel)||[['설정',panel.body]]).entries())railButton(label,()=>{if(i!==index){flow.index=i;renderTask(Math.sign(i-index));}},i===index,i);
   railButton('← 돌아가기',()=>panel.close());
  }else if(page===1){subnav.append(make('strong','VOD 등록','task-rail-title'));for(const [i,label] of ['주소 입력','처리 선택','등록 확인'].entries())railButton(label,()=>i===1?layout.queueSettings.open():showRegistration(i),registration===i,i);}
  else if(page===9){subnav.append(make('strong','설정','task-rail-title'));settingsGroups.forEach(([label],i)=>railButton(label,()=>{const changed=settingsTab!==i;settingsTab=i;renderSettings(changed);},settingsTab===i));}
  subnav.hidden=!flow&&![1,9].includes(page);
  document.body.dataset.railDepth=String(workspaceDepth({project:projectScreen,task:!!flow||page===9,register:page===1}));
  for(const [id,yes] of [['new',page===1],['nav-library',![1,9,10,11,12].includes(page)],['nav-jobs',page===10],['open-video-split',page===11],['open-mix',page===12],['step9',page===9]])$(id).setAttribute('aria-current',yes?'page':'false');
 }
 return {navigate(step,{use:workPage=false}={}){
  if(use.inert){
   delete document.body.dataset.openingWorkspace;
   purposes.inert=use.inert=false;
   use.setAttribute('aria-busy','false');
  }
  const changed=page!==step||use.hidden===workPage;
  const animate=changed&&!firstNavigation;
  firstNavigation=false;page=step;use.hidden=!workPage;
  if(workPage){
   document.body.dataset.usePage='true';$('heading').textContent='작업';$('context-panel').hidden=true;$('speech-panel').hidden=true;$('analysis-results-nav').hidden=true;
  }else delete document.body.dataset.usePage;
  purposes.hidden=!getProject()||[0,1,9,10,11,12].includes(step);
  purposeButtons.forEach((b,i)=>b.setAttribute('aria-current',(step===2?0:!workPage&&[3,4,5,6].includes(step)?1:2)===i?'step':'false'));
  if(step===1&&changed)showRegistration(0,false);if(step===9)renderSettings();else setUpdateVisible(false);renderRails();
  updatePreparation();
  if(animate){
   const panels=['library-page','register-address','prepare-overview','speech-panel','voices-panel','explore-panel','context-panel','report-panel','external-panel','settings-page','jobs-page','video-split-page','mix-page'];
   enterView(workPage?use:$(panels[step]),0);
  }
 },update(){
  const p=getProject();
  if(path!==p?.path){path=p?.path;if(!use.inert){use.hidden=true;delete document.body.dataset.usePage;}}
  renderRails();updatePreparation();
  if(!use.inert)purposes.hidden=!p||[0,1,9,10,11,12].includes(page);
 },showUse,previewUse};
}
