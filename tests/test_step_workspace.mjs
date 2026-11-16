import assert from 'node:assert/strict';
import {createSettingsPanel} from '../web/settings-panel.js';
import {createStepWorkspace,workspaceDepth,routeSteps} from '../web/step-workspace.js';
import {createWorkspaceStatus} from '../web/workspace-status.js';

// test_workspace_ui의 이동 가능한 DOM 패턴에 지연 close 이벤트만 추가한다.
// 실제 API·파일·브라우저 저장소 없이 기존 폼과 통합 화면 전환을 검사한다.
const lateEvents=[];let focused=null;
const descendants=node=>node.children.flatMap(child=>[child,...descendants(child)]);
function simple(node,selector,scope){
  if(selector===':scope')return node===scope;
  let rejected=false;selector=selector.replace(/:not\(([^)]+)\)/g,(_,part)=>{if(simple(node,part,scope))rejected=true;return '';});
  if(rejected)return false;
  const tag=selector.match(/^[a-z][\w-]*/i)?.[0];if(tag&&node.tagName!==tag.toUpperCase())return false;
  for(const [,id] of selector.matchAll(/#([\w-]+)/g))if(node.id!==id)return false;
  for(const [,cls] of selector.matchAll(/\.([\w-]+)/g))if(!node.className.split(/\s+/).includes(cls))return false;
  for(const [,name,value] of selector.matchAll(/\[([\w-]+)(?:=["']?([^\]"']+)["']?)?\]/g)){
    const actual=node.getAttribute(name);if(actual==null||value!=null&&actual!==value)return false;
  }
  return true;
}
function matches(node,selector,scope){
  const children=selector.split('>').map(part=>part.trim());
  if(children.length>1){let at=node;for(let i=children.length-1;i>=0;i--){if(!at||!simple(at,children[i],scope))return false;at=at.parentElement;}return true;}
  const parts=selector.trim().split(/\s+/);if(!simple(node,parts.pop(),scope))return false;
  let at=node.parentElement;while(parts.length){const part=parts.pop();while(at&&!simple(at,part,scope))at=at.parentElement;if(!at)return false;at=at.parentElement;}return true;
}
class Element{
  constructor(tag='div'){
    this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.listeners={};this.dataset={};this.style={};this.className='';this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.open=false;this._text='';
    this.classList={add:(...items)=>{this.className=[...new Set([...this.className.split(/\s+/).filter(Boolean),...items])].join(' ');},remove:(...items)=>{this.className=this.className.split(/\s+/).filter(item=>!items.includes(item)).join(' ');},toggle:(name,value)=>{if(value===undefined)value=!this.className.split(/\s+/).includes(name);value?this.classList.add(name):this.classList.remove(name);}};
  }
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  set textContent(value){for(const child of this.children)child.parentElement=null;this.children=[];this._text=String(value??'');}
  append(...items){for(const node of items){assert(node instanceof Element,'DOM을 복제하지 않고 기존 노드를 이동해야 합니다.');node.remove();node.parentElement=this;this.children.push(node);}}
  prepend(...items){for(const node of [...items].reverse()){node.remove();node.parentElement=this;this.children.unshift(node);}}
  replaceChildren(...items){this.textContent='';this.append(...items);}
  before(...items){const parent=this.parentElement;assert(parent);let index=parent.children.indexOf(this);for(const node of items){node.remove();node.parentElement=parent;parent.children.splice(index++,0,node);}}
  after(...items){const parent=this.parentElement;assert(parent);let index=parent.children.indexOf(this)+1;for(const node of items){node.remove();node.parentElement=parent;parent.children.splice(index++,0,node);}}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(child=>child!==this);this.parentElement=null;}
  get previousElementSibling(){return this.parentElement?.children[this.parentElement.children.indexOf(this)-1]||null;}
  get nextElementSibling(){return this.parentElement?.children[this.parentElement.children.indexOf(this)+1]||null;}
  get isConnected(){return this===body||!!this.parentElement?.isConnected;}
  setAttribute(key,value){if(key==='hidden')this.hidden=true;else this.attributes[key]=String(value);}
  getAttribute(key){if(key==='hidden')return this.hidden?'':null;if(key==='open')return this.open?'':null;if(key==='id')return this.id??null;if(key.startsWith('data-'))return this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]??null;return this.attributes[key]??null;}
  addEventListener(type,callback){(this.listeners[type]??=[]).push(callback);}
  dispatchEvent(event){for(const callback of this.listeners[event.type]||[])callback(event);}
  querySelectorAll(selector){return descendants(this).filter(node=>selector.split(',').some(part=>matches(node,part.trim(),this)));}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  closest(selector){for(let node=this;node;node=node.parentElement)if(matches(node,selector,this))return node;return null;}
  contains(node){return node===this||descendants(this).includes(node);}
  focus(){focused=this;}getClientRects(){return this.isConnected&&!this.hidden?[{}]:[];}
  show(){this.open=true;}showModal(){this.open=true;}
  close(){if(!this.open)return;this.open=false;lateEvents.push(()=>this.dispatchEvent(new Event('close')));}
  click(){if(!this.disabled){this.dispatchEvent(new Event('click'));this.onclick?.();}}
}
const body=new Element('body');
globalThis.document={body,createElement:tag=>new Element(tag),getElementById:id=>descendants(body).find(node=>node.id===id)||null,querySelector:selector=>body.querySelector(selector),addEventListener:(...args)=>body.addEventListener(...args)};
globalThis.window={};globalThis.MutationObserver=class{observe(){}};
globalThis.fetch=()=>{throw Error('통합 UI 검사에서 네트워크 접근 금지');};
const $=id=>{const node=document.getElementById(id);assert(node,'없는 폼 ID: '+id);return node;};
const add=(tag,id,parent=body,cls='')=>{const node=new Element(tag);node.id=id;node.className=cls;parent.append(node);return node;};
const flushClose=()=>{while(lateEvents.length)lateEvents.shift()();};
const rail=add('aside','primary'),navigation=add('div','navigation',rail,'workspace-navigation'),main=add('main','main');add('header','header',main);
for(const id of ['new','nav-library','nav-jobs','open-video-split','open-mix','workspace-search-open'])add('button',id,navigation);
add('button','step9',add('footer','rail-footer',rail));
for(const id of ['library-page','import-panel','jobs-page','download-panel','context-panel','speech-panel','analysis-results-nav'])add('section',id,main);
add('div','jobs-intro',$('jobs-page'),'library-intro');
for(const id of ['open-clip-studio','jobs-automation'])add('button',id,main);
const queue=add('section','queue-section',$('import-panel'),'queue-section');add('h3','addresses-title',queue).textContent='등록할 주소';
const inputs=add('div','queue-inputs',queue),row=add('div','queue-row',inputs),url=add('input','queue-url',row);url.value='https://chzzk.naver.com/video/123';
const moreRow=add('div','more-row',queue);add('button','queue-more',moreRow);
add('h3','settings-old-title',queue);add('div','queue-settings-launcher',queue);add('button','queue-add',queue);
add('p','queue-selection-summary',queue).textContent='영상·채팅 → 전사 → 타임스탬프';add('p','queue-status',queue);add('div','queue-list',queue);
const queueActions=add('div','queue-actions',queue);add('button','queue-start',queueActions);
const queueWork=add('div','queue-work-options');add('select','queue-height',queueWork).value='480';
add('select','queue-fragments',queueWork).value='1';
const originalCards=add('div','download-cards',$('download-panel'),'cards');add('button','video-resume',originalCards);add('button','chat-resume',originalCards);
const originalActions=add('div','download-actions',$('download-panel'),'action-row');add('button','resume-all',originalActions);
const scope=add('section','scope-preview',$('download-panel'),'analysis-scope-preview'),scopeOpen=add('button','analysis-scope-open',scope);
const scopeSettings=createSettingsPanel('analysis-scope-settings','분석 범위',[add('section','scope-fields')]);scopeOpen.onclick=()=>scopeSettings.open(scopeOpen);
const settings=add('section','settings-page',main),appearance=add('section','appearance',settings,'settings-appearance');
add('h3','appearance-title',appearance).textContent='화면';add('input','theme-option',appearance).value='dark';
add('h3','storage-title',appearance).textContent='보관함 저장 공간';add('button','storage-action',appearance);
add('section','folder-settings',settings,'folder-settings');add('section','compute-settings',settings);
add('input','error-log-enabled',add('section','log-settings',settings)).checked=true;
let registrations=0,starts=0;$('queue-add').onclick=()=>registrations++;
const speechSteps=add('div','speech-steps',body,'speech-steps');for(let i=0;i<3;i++)add('article','speech-step-'+i,speechSteps);
add('input','speech-prompt',$('speech-step-2')).value='기존 용어';
const transcribe=add('button','transcribe');transcribe.onclick=()=>starts++;
function analysisSettings(prefix){
  const input=add('fieldset',prefix+'-inputs');add('select',prefix+'-transcript',input).value='원본 전사 버전';
  const background=add('form',prefix+'-background-form');add('textarea',prefix+'-background',background).value='기존 방송 상황';
  const thinking=add('label',prefix+'-thinking-label');add('input',prefix+'-thinking',thinking).checked=true;
  const control=add('p',prefix+'-model'),generate=add('button',prefix+'-generate');generate.onclick=()=>starts++;
  return createSettingsPanel(prefix+'-settings','새 분석',[input,background,thinking,control],[generate]);
}
const layout={
  queueSettings:createSettingsPanel('queue-options','처리 선택',[queueWork]),
  audioSettings:createSettingsPanel('audio-settings','원음 추출',[$('speech-step-0')]),
  speechSettings:createSettingsPanel('speech-settings','전사',[speechSteps],[transcribe]),
  voiceSettings:createSettingsPanel('voice-settings','화자',[add('section','voices-setup')]),
  contextSettings:analysisSettings('context'),clipSettings:analysisSettings('context-clips'),versions:[],
};
const speechMaterials=add('section','speech-materials',layout.speechSettings.body);
const audioJobSlot=add('div','audio-job-slot',layout.audioSettings.body);
const coverage=add('p','speech-coverage',speechMaterials);coverage.textContent='완료된 전사 범위';
const audioLink=add('a','speech-audio-save',layout.audioSettings.body);audioLink.href='/saved-source.wav';
layout.panels=[layout.queueSettings,layout.audioSettings,layout.speechSettings,layout.voiceSettings,layout.contextSettings,layout.clipSettings];
for(const id of ['speech-model','voices-model','speech-readiness','voices-readiness','context-readiness','clips-readiness','context-resume','context-clips-resume','context-job','clips-job','speech-job','voices-job','download-details','project-assets','step2','lock-note','workspace-subtitle','context-version','context-clips-version','global-jobs','global-job-rows'])if(!document.getElementById(id))add('div',id,main);
const queueGlobal=add('div','global-state-wrap',main);add('p','global-queue-state',queueGlobal);add('button','global-queue-link',queueGlobal);
for(const id of ['context-job-history','clips-job-history']){const details=add('details',id,main);add('summary',id+'-summary',details);}
const originals=['queue-inputs','queue-url','queue-height','queue-add','speech-prompt','context-transcript','context-background','context-thinking','context-clips-transcript','context-clips-background','transcribe','context-generate','context-clips-generate'].map(id=>[id,$(id)]);
let project={path:'/가상/vod-1',metadata:{title:'검사 VOD',duration:60},tasks:{video:{state:'complete'},chat:{state:'complete'}},context:{state:'idle'},speech:{state:'idle'},voices:{state:'idle'}},mode='clips',view,currentStep=0;
const selections=[],context={mode:()=>mode,selectMode(value,options){mode=value;selections.push([value,options]);}};
const stopSpeech=add('button','speech-stop',$('speech-job'));
const status=createWorkspaceStatus(layout);status.update(project);
for(const [action,host,label] of [['audio',audioJobSlot,'원음 추출 중단'],['transcribe',speechMaterials,'음성 전사 중단']]){
  const panel=action==='audio'?layout.audioSettings:layout.speechSettings;
  panel.open();
  status.update({...project,speech:{action,state:'running',owned:true}});
  assert.ok(panel.dialog.open);
  assert.equal($('speech-job').parentElement,host);
  assert.ok(host.contains(stopSpeech));assert.equal(stopSpeech.textContent,label);
  panel.close();status.update(project);
}
const navigate=(step,options)=>{currentStep=step;status.navigate(step);view?.navigate(step,options);};
view=createStepWorkspace({layout,getProject:()=>project,navigate,enterAnalysis:()=>navigate(6),context});

assert.equal($('prepare-download-details').contains(originalCards),true);assert.equal($('prepare-download-details').contains(originalActions),true);
assert.equal($('registration-queue').tagName,'SECTION');assert.equal($('queue-list').parentElement,$('registration-queue'));assert.equal($('registration-queue').closest('#import-panel'),$('import-panel'));assert.equal(document.getElementById('automation-status'),null);
view.update();assert.equal($('prepare-download-details').open,true);
assert.equal($('prepare-download-details').closest('dialog').id,'download-settings');
project.tasks.video.state='downloading';view.update();assert.equal($('task-main').hidden,true,'폴링으로 작업 설정을 강제로 열지 않음');
project.tasks.video.state='error';view.update();assert.equal($('task-main').hidden,true);
project.tasks.video.state='complete';view.update();
const prepRows=$('download-panel').querySelectorAll('.prepare-row');
assert.equal(prepRows.length,5);
project.speech={action:'audio',state:'complete',raw_audio:{file:'source.wav'}};view.update();
assert.equal(prepRows[1].querySelector('.prepare-status').dataset.state,'complete');
assert.equal(prepRows[2].querySelector('.prepare-status').dataset.state,'idle','원음 추출 완료는 전사 완료가 아님');
project.speech={action:'transcribe',state:'running',raw_audio:{file:'source.wav'}};view.update();
assert.equal(prepRows[1].querySelector('.prepare-status').dataset.state,'complete');
assert.equal(prepRows[2].querySelector('.prepare-status').dataset.state,'running');
project.speech={action:'model',state:'complete',raw_audio:{file:'source.wav'},transcript:{complete:true}};view.update();
assert.equal(prepRows[2].querySelector('.prepare-status').dataset.state,'complete');
project.speech={state:'idle'};view.update();

assert.deepEqual(routeSteps,{register:1,library:0,jobs:10,split:11,mix:12,settings:9,prepare:2,speech:3,voices:4,explore:5,context:6,report:7,external:8});
add('section','video-split-page',main);add('section','mix-page',main);
const loadedProject=project;project=null;
view.previewUse('147');
view.update();
assert.equal($('use-page').children.length,3);
assert.equal($('use-page').hidden,false);assert.equal($('purpose-tabs').hidden,false);
assert.equal($('use-page').inert,true);assert.equal($('purpose-tabs').inert,true);
assert.equal($('purpose-tabs').children[2].getAttribute('aria-current'),'step');
assert.equal($('selected-vod-rail').hidden,false);assert.equal(body.dataset.railDepth,'2');
project=loadedProject;
const menuEntrances=[];
for(const id of ['video-split-page','mix-page']){
  $(id).animate=()=>{menuEntrances.push(id);return {cancel(){}};};
}
navigate(11);view.update();
assert.equal($('use-page').inert,false);assert.equal($('purpose-tabs').inert,false);
assert.equal($('use-page').hidden,true);assert.equal(body.dataset.openingWorkspace,undefined);
assert.deepEqual(menuEntrances,[],'편집기에서 돌아와 처음 표시하는 메뉴는 바로 보인다');
assert.equal(document.body.dataset.railDepth,'1');
assert.equal($('open-video-split').getAttribute('aria-current'),'page');
assert.equal($('nav-library').getAttribute('aria-current'),'false');
assert.equal($('purpose-tabs').hidden,true);
assert.equal($('selected-vod-rail').hidden,true);
navigate(12);view.update();
assert.equal($('open-mix').getAttribute('aria-current'),'page');
assert.equal($('open-video-split').getAttribute('aria-current'),'false');
assert.equal($('purpose-tabs').hidden,true);
assert.equal(document.body.dataset.railDepth,'1');
navigate(11);navigate(11);
assert.deepEqual(menuEntrances,['mix-page','video-split-page'],'문서 안에서 메뉴를 바꿀 때만 한 번 등장한다');
navigate(0);
add('h1','heading',main);
for(const id of ['voices-panel','explore-panel','report-panel','external-panel'])add('section',id,main);
const entered=[];
for(const id of ['prepare-overview','speech-panel','voices-panel','explore-panel','context-panel','report-panel','external-panel','use-page']){
  $(id).animate=()=>{entered.push(id);return {cancel(){}};};
}
for(const step of [2,3,4,5,6,7,8])navigate(step);
view.showUse();view.showUse();
assert.deepEqual(entered,['prepare-overview','speech-panel','voices-panel','explore-panel','context-panel','report-panel','external-panel','use-page']);
assert.equal($('context-panel').hidden,true);assert.equal($('analysis-results-nav').hidden,true);assert.equal($('use-page').hidden,false);
navigate(6);assert.equal(entered.at(-1),'context-panel');assert.equal($('use-page').hidden,true);
for(const [input,expected] of [[{},1],[{project:true},2],[{register:true},2],[{task:true},2],[{project:true,task:true},3]])assert.equal(workspaceDepth(input),expected);
navigate(1);assert.equal($('register-address').hidden,false);assert.equal($('register-confirm').hidden,true);
$('registration-next').click();assert.equal(layout.queueSettings.dialog.open,true);assert.equal(body.dataset.taskFlow,'queue-options');assert.equal($('task-main').hidden,false);
$('queue-height').value='1080';$('queue-fragments').value='16';layout.queueSettings.footer.querySelector('.task-next').click();
assert.equal(layout.queueSettings.dialog.open,false);assert.equal(body.dataset.taskFlow,undefined);assert.equal($('register-address').hidden,true);assert.equal($('register-confirm').hidden,false);
assert.match($('registration-summary').textContent,/123/);assert.match($('registration-summary').textContent,/1080p/);assert.equal(registrations,0);assert.equal(starts,0);
assert.match($('registration-summary').textContent,/동시 다운로드 16개/);
flushClose();assert.equal($('register-confirm').hidden,false); // 늦은 close 이벤트가 확인 화면을 다시 주소 화면으로 바꾸지 않는다.
$('queue-add').click();assert.equal(registrations,1);

// 실제 app.go와 같은 status.navigate → stepWorkspace.navigate 순서로 닫는다.
layout.queueSettings.open();navigate(0);
assert.equal(layout.queueSettings.dialog.open,false);assert.equal(body.dataset.taskFlow,undefined);assert.equal($('task-main').hidden,true);assert.equal(currentStep,0);
flushClose();assert.equal(body.dataset.taskFlow,undefined);assert.equal($('queue-height').value,'1080');

navigate(2);$('prepare-processing').click();
assert.equal(body.dataset.taskFlow,'download-settings');
assert.equal($('selected-vod-rail').hidden,false);assert.equal(body.dataset.railDepth,'3');
assert.equal($('prepare-download-details').contains(originalCards),true);
assert.deepEqual($('task-rail').children.filter(node=>node.title&&node.title!=='← 돌아가기').map(node=>node.title),['영상/채팅','원음 추출','음성 전사','화자 구분','AI 문맥']);
$('task-rail').children.find(node=>node.title==='원음 추출').click();
assert.equal(layout.audioSettings.dialog.open,true);
assert.equal(layout.audioSettings.body.contains($('speech-step-0')),true);
assert.equal(layout.audioSettings.body.contains(audioLink),true);
assert.equal(layout.audioSettings.body.children.indexOf($('speech-step-0'))<layout.audioSettings.body.children.indexOf(audioLink),true);
$('task-rail').children.find(node=>node.title==='음성 전사').click();
assert.equal(layout.speechSettings.dialog.open,true);assert.equal(speechMaterials.hidden,false);
assert.equal(layout.speechSettings.dialog.contains($('speech-step-0')),false);assert.equal($('transcribe').hidden,false);
assert.equal($('header').hidden,true);assert.equal($('speech-panel').contains(speechMaterials),false);
assert.equal($('speech-coverage'),coverage);assert.equal($('speech-audio-save'),audioLink);
assert.equal(audioLink.href,'/saved-source.wav');
assert.equal(layout.speechSettings.footer.querySelector('.task-next').hidden,true);
assert.equal(speechMaterials.hidden,false);assert.equal($('speech-step-1').hidden,false);
layout.speechSettings.close();flushClose();layout.speechSettings.open();
assert.equal(speechMaterials.hidden,false,'자료 확인과 전사 모델 설정을 같은 페이지에 표시');
assert.equal($('speech-step-1').hidden,false);assert.equal(starts,0);
layout.speechSettings.close();flushClose();$('prepare-processing').click();
$('task-rail').children.find(node=>node.title==='AI 문맥').click();
assert.equal(layout.contextSettings.dialog.open,true);
const modes=()=>layout.contextSettings.body.querySelectorAll('[data-analysis-mode]');
modes().find(button=>button.dataset.analysisMode==='timestamps').click();
assert.equal(mode,'timestamps');assert.equal(layout.contextSettings.dialog.open,true);assert.equal(layout.contextSettings.dialog.parentElement,$('task-main'));assert.equal(body.dataset.taskFlow,'context-settings');
const closeCount=lateEvents.length;assert.ok(closeCount>0);flushClose();
assert.equal(layout.contextSettings.dialog.open,true);assert.equal(layout.contextSettings.dialog.parentElement,$('task-main'));assert.equal(body.dataset.taskFlow,'context-settings');
assert.equal(modes().find(button=>button.dataset.analysisMode==='timestamps').getAttribute('aria-pressed'),'true');
modes().find(button=>button.dataset.analysisMode==='clips').click();
assert.equal(mode,'clips');assert.equal(layout.contextSettings.dialog.open,false);assert.equal(layout.clipSettings.dialog.open,true);flushClose();
assert.equal(body.dataset.taskFlow,'context-clips-settings');assert.equal(layout.clipSettings.dialog.parentElement,$('task-main'));
assert.equal($('context-clips-generate').hidden,true);layout.clipSettings.footer.querySelector('.task-next').click();
assert.equal($('context-clips-generate').hidden,true);layout.clipSettings.footer.querySelector('.task-next').click();
assert.equal($('context-clips-generate').hidden,false);assert.equal(starts,0); // 단계 이동만으로 실제 작업은 시작하지 않는다.
layout.clipSettings.body.querySelectorAll('[data-analysis-mode]').find(button=>button.dataset.analysisMode==='detail').click();
assert.equal(mode,'detail');assert.equal(layout.contextSettings.dialog.open,true);flushClose();assert.equal(body.dataset.taskFlow,'context-settings');
layout.contextSettings.close();assert.equal(body.dataset.taskFlow,undefined);layout.contextSettings.open();flushClose();
assert.equal(body.dataset.taskFlow,'context-settings');assert.equal(layout.contextSettings.dialog.open,true);
$('context-background').value='아직 실행하지 않은 추가 요청';status.update(project);view.update();
assert.equal(layout.contextSettings.dialog.open,true);assert.equal(body.dataset.taskFlow,'context-settings');assert.equal($('context-background').value,'아직 실행하지 않은 추가 요청');
navigate(10);flushClose();
assert.equal(body.dataset.taskFlow,undefined);assert.equal($('task-main').hidden,true);assert.equal($('context-background').value,'아직 실행하지 않은 추가 요청');

// 취소는 이번 열기 이후 변경만 복원하며, 기존 입력을 삭제하거나 실행하지 않는다.
layout.contextSettings.open();$('context-background').value='취소할 추가 요청';$('context-thinking').checked=false;
layout.contextSettings.footer.querySelector('.secondary:not(.task-previous)').click();
assert.equal(body.dataset.taskFlow,undefined);assert.equal($('context-background').value,'아직 실행하지 않은 추가 요청');assert.equal($('context-thinking').checked,true);
flushClose();assert.equal($('task-main').hidden,true);

// 도움말을 연 채 동기 닫기 후 즉시 재열어도 이전 도움말로 본문이 가려지면 안 된다.
const panel=layout.contextSettings,helpText=new Element('p');helpText.textContent='이전 도움말';
panel.open();panel.dialog.dispatchEvent({type:'settings-help',detail:helpText});
assert.equal(panel.body.hidden,true);assert.equal(panel.footer.hidden,true);
panel.close();
assert.equal(panel.body.hidden,false,'설정 닫기는 도움말의 본문 숨김도 즉시 해제해야 합니다.');
assert.equal(panel.footer.hidden,false);assert.equal(panel.dialog.querySelector('.settings-help'),null);
panel.open();assert.equal(panel.body.hidden,false);assert.equal(panel.dialog.open,true);
const newHelpText=new Element('p');newHelpText.textContent='새로 연 도움말';
panel.dialog.dispatchEvent({type:'settings-help',detail:newHelpText});flushClose();
assert.equal(panel.dialog.open,true);assert.equal(panel.body.hidden,true);assert.equal(panel.dialog.querySelector('.settings-help').textContent,'새로 연 도움말');
panel.dialog.querySelector('.settings-heading .subtle').click();
assert.equal(panel.dialog.open,true);assert.equal(panel.body.hidden,false);assert.equal(panel.footer.hidden,false);assert.equal(panel.dialog.querySelector('.settings-help'),null);
assert.equal(panel.dialog.querySelector('.settings-heading .subtle').textContent,'닫기 ×');
assert.equal(panel.note.hidden,true,'반복 설정 안내는 도움말로 옮긴다');
assert.equal(panel.dialog.querySelector('.settings-heading .help-button'),null,'도움말 전구 버튼을 생성하지 않는다');
panel.close();flushClose();assert.equal(body.dataset.taskFlow,undefined);

navigate(2);$('prepare-processing').click();assert.equal($('download-settings').open,true);
scopeOpen.click();assert.equal($('download-settings').open,false);assert.equal(scopeSettings.dialog.open,true);
scopeSettings.close();flushClose();assert.equal(body.dataset.taskFlow,undefined);
navigate(9);assert.equal($('folder-settings').parentElement.hidden,false);assert.equal($('log-settings').parentElement.hidden,true);
$('task-rail').querySelectorAll('button').find(button=>button.textContent==='처리·로그').click();
assert.equal($('folder-settings').parentElement.hidden,true);assert.equal($('log-settings').parentElement.hidden,false);
assert.equal($('error-log-enabled').checked,true);assert.equal($('theme-option').value,'dark');

for(const [id,node] of originals){assert.equal($(id),node);assert.equal(descendants(body).filter(item=>item.id===id).length,1);}
assert.equal($('speech-prompt').value,'기존 용어');assert.equal($('context-transcript').value,'원본 전사 버전');assert.equal($('context-thinking').checked,true);
assert.equal(starts,0);assert.equal(project.context.state,'idle');
console.log('단계형 실화면 통합: 등록→설정→확인, 주메뉴 닫힘, 같은/다른 패널 지연 close·빠른 재열기, 세 분석 모드 연결, 폼 ID·입력·실행 핸들러 보존, 깊이 계산 통과');
