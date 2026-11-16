import assert from 'node:assert/strict';
import {createSettingsPanel} from '../web/settings-panel.js';
import {shortVersion,compactVersionPicker} from '../web/version-picker.js';

// 네트워크·실제 분석 없이 설정 패널의 입력/취소/도움말 계약을 검사한다.
class Element {
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.dataset={};this.classList={toggle(){}};this.attributes={};this.value='';this.checked=false;this.disabled=false;this.isConnected=true;}
  setAttribute(k,v){this.attributes[k]=v;}
  append(...items){for(const n of items){n.parentElement?.removeChild(n);n.parentElement=this;this.children.push(n);}}
  removeChild(n){this.children=this.children.filter(x=>x!==n);n.parentElement=null;}
  before(n){const parent=this.parentElement;parent.children.splice(parent.children.indexOf(this),0,n);n.parentElement=parent;}
  remove(){this.parentElement?.removeChild(this);}
  addEventListener(name,fn){(this.listeners[name]||=[]).push(fn);}
  dispatchEvent(event){for(const fn of this.listeners[event.type]||[])fn(event);}
  querySelector(selector){return this.children.find(n=>n.tagName===selector.toUpperCase())||null;}
  querySelectorAll(){return this.children.flatMap(n=>['INPUT','SELECT','TEXTAREA'].includes(n.tagName)?[n]:n.querySelectorAll());}
  getClientRects(){return [{}];} focus(){focused=this;}
  showModal(){this.open=true;} close(){this.open=false;this.dispatchEvent(new Event('close'));}
  get options(){return this.children;} get selectedOptions(){return this.children.filter(n=>n.value===this.value);}
}
let focused=null;
const body=new Element('body');
globalThis.document={body,createElement:tag=>new Element(tag),querySelector:()=>body.children.find(n=>n.open),addEventListener:(...args)=>body.addEventListener(...args)};
globalThis.MutationObserver=class{observe(){}};
const input=new Element('input');input.value='기존 입력';const check=new Element('input');check.checked=false;
const group=new Element('fieldset');group.append(input,check);body.append(group);
const start=new Element('button'),opener=new Element('button');let starts=0;start.onclick=()=>starts++;
const panel=createSettingsPanel('settings','설정',[group],[start]);
assert.equal(panel.body.children.includes(group),true);assert.equal(group.children[0],input);
panel.open(opener);input.value='편집';check.checked=true;panel.close();assert.equal(input.value,'편집');assert.equal(focused,opener);assert.equal(starts,0);
panel.open(opener);input.value='바깥 클릭 후 보존';
for(const type of ['pointerdown','click'])body.dispatchEvent({type,button:0,target:opener,composedPath:()=>[opener,body],clientX:100,clientY:100});
assert.equal(panel.dialog.open,false);assert.equal(input.value,'바깥 클릭 후 보존');assert.equal(starts,0);input.value='편집';
panel.open(opener);input.value='취소할 입력';check.checked=false;panel.footer.children[0].onclick();assert.equal(input.value,'편집');assert.equal(check.checked,true);
panel.open(opener);const help=new Element('section');panel.dialog.dispatchEvent({type:'settings-help',detail:help});assert.equal(panel.body.hidden,true);
panel.dialog.dispatchEvent({type:'cancel',preventDefault(){}});assert.equal(panel.dialog.open,true);assert.equal(panel.body.hidden,false);
panel.dialog.dispatchEvent({type:'cancel',preventDefault(){}});assert.equal(panel.dialog.open,false);
panel.open(opener);input.value='처리 수락';panel.accepted();input.value='추가 입력';panel.footer.children[0].onclick();assert.equal(input.value,'처리 수락');assert.equal(starts,0);
panel.open(opener);panel.reset();assert.equal(panel.dialog.open,false);
assert.equal(shortVersion('이전 결과'), '이전 결과');
assert.match(shortVersion('2026-10-27T18:30:10 · Gemma 클립 · 전사 18:05 · 완료'),/^10-27 18:30 · Gemma 클립 · 전사 18:05$/);
const select=new Element('select');const label='2026-10-27T18:30 · 한국어 전사 · 원본 오디오 · 완료 · 100개 발언';
for(const id of ['11111111-aaaa','22222222-bbbb']){const o=new Element('option');o.value=id;o.textContent=label;select.append(o);}select.value=select.options[1].value;
const picker=compactVersionPicker(select);assert.notEqual(select.options[0].textContent,select.options[1].textContent);assert.equal(select.options[0].title,label);
assert.equal(select.value,'22222222-bbbb');assert.match(picker.details.children[1].textContent,/22222222-bbbb/);
const labels=select.options.map(x=>x.textContent);picker.update();assert.deepEqual(select.options.map(x=>x.textContent),labels);
console.log('설정 원본 노드 유지·닫기 보존·취소 복원·도움말/Esc·시작 미발생·버전 설명/ID/중복 구분 통과');

const {createWorkspaceStatus}=await import('../web/workspace-status.js');
const nodes=new Map();document.getElementById=id=>{if(!nodes.has(id)){const el=new Element('div');el.id=id;el.textContent='';if(id.endsWith('-job-history'))el.append(new Element('summary'));el.classList={toggle(){}};nodes.set(id,el);}return nodes.get(id);};
const $=id=>document.getElementById(id);document.querySelector=()=>$('queue-section');$('queue-pause').disabled=true;
Object.defineProperty(Element.prototype,'nextElementSibling',{get(){const p=this.parentElement;return p?.children[p.children.indexOf(this)+1];}});
const bar=new Element('div');bar.append($('global-queue-state'),new Element('button'));
const timers=new Map();let clock=0;
globalThis.setTimeout=(fn,ms)=>{const id=++clock;timers.set(id,{fn,ms});return id;};globalThis.clearTimeout=id=>timers.delete(id);
let closed=0,accepted=0,opened=0,jobsOpened=0,moreClosed=0;
const toastItems=()=>$('ui-toasts').children,clearToasts=()=>{for(const item of [...toastItems()])item.children.at(-1).onclick();};
const settings={close(){closed++;},accepted(){accepted++;}};
const view=createWorkspaceStatus({closeMore(){moreClosed++;},panels:[],versions:[],contextSettings:settings,clipSettings:settings,speechSettings:settings,voiceSettings:settings});
const p={root:'/library',vod_id:'1',path:'/test-1',metadata:{title:'상태 검증',duration:60},tasks:{video:{state:'complete'},chat:{state:'complete'}},speech:{state:'idle'},voices:{state:'idle'},context:{state:'idle',inputs:{}}};
view.update(p);assert.equal($('global-jobs').hidden,true);assert.equal($('context-job').dataset.idle,'true');
const running={...p,context:{...p.context,state:'running',action:'clips',owned:true,message:'클립 검토 중'}};const original=JSON.stringify(running);
view.update(running);assert.equal(accepted,2);assert.equal(closed,2);assert.equal($('global-jobs').hidden,true);
assert.equal(toastItems().length,1);assert.match(toastItems()[0].children[0].textContent,/클립 검토 중/);assert.equal([...timers.values()][0].ms,15000);
view.update({...running,context:{...running.context,message:'진행률만 변경'}});assert.equal(toastItems().length,1,'동일 상태를 반복 조회해도 알림을 중복하지 않음');
$('step6').click=()=>opened++;$('nav-jobs').click=()=>jobsOpened++;
toastItems()[0].children[1].onclick();assert.equal(opened,1);assert.equal(toastItems().length,0);
view.navigate(6);view.update({...running,context:{...running.context,run:'new-run'}});assert.equal(toastItems().length,0,'현재 작업 화면에서는 별도 토스트 생략');assert.equal(JSON.stringify(running),original);
view.navigate(3);view.update({...running,context:{state:'error',action:'clips',message:'입력 읽기 실패',owned:false}});
assert.equal($('global-jobs').hidden,true);assert.equal(toastItems().length,1);assert.match(toastItems()[0].children[0].textContent,/입력 읽기 실패/);
view.update({...p,path:'/test-2',vod_id:'2'});toastItems()[0].children[1].onclick();assert.equal(jobsOpened,1,'알림 대상과 현재 VOD가 다르면 전체 진행 상태로 이동');assert.equal(opened,1);
view.update(running);view.update({...running,context:{state:'complete',action:'clips',message:'완료 결과 저장'}});assert.equal(toastItems().length,1,'완료는 대기열에서 한 번만 알린다');
clearToasts();view.update(null);assert.equal($('download-details').hidden,true);assert.equal($('global-jobs').hidden,true);
console.log('작업 상태별 15초 토스트·중복 억제·대상별 열기·완료 전환·작업 수락·원본 불변 검사 통과');

view.update(p);view.navigate(2);assert.equal($('queue-section').hidden,true);assert.equal($('download-details').hidden,false);assert.equal($('lock-note').hidden,true);assert.match($('workspace-subtitle').textContent,/상태 검증/);
view.navigate(1);assert.equal($('queue-section').hidden,false);assert.equal($('download-details').hidden,true);
view.navigate(9);assert.equal($('queue-section').hidden,true);assert.equal($('download-details').hidden,true);assert.equal($('workspace-subtitle').textContent,'');
console.log('등록·저장 VOD·설정 화면 분리 검사 통과');
let resultTab='clips';const lookup=document.querySelector;
document.querySelector=selector=>selector.includes('[role=tab]')?{id:'context-tab-'+resultTab}:lookup(selector);
$('context-clips-version').value='saved-clips';$('context-version').value='saved-detail';
view.update({...p,context:{state:'paused',action:'timestamps',run:'old-timestamps'}});
assert.equal($('clips-job-history').hidden,true,'다른 결과의 이전 작업은 클립 목록에 표시하지 않음');
assert.equal($('context-job-history').hidden,true);
view.update({...p,context:{state:'paused',action:'clips',clip_run:'saved-clips'}});
assert.equal($('clips-job-history').hidden,false,'선택한 결과의 작업 상태는 유지');
resultTab='detail';view.update({...p,context:{state:'complete',action:'whole',full_run:'saved-detail'}});
assert.equal($('context-job-history').hidden,false);
assert.equal($('clips-job-history').hidden,true);
document.querySelector=lookup;
console.log('선택 결과 상태 유지와 다른 결과의 이전 상태 제거 검사 통과');

view.update(p);view.navigate(2);
const queue={active:true,root:'/library',items:[{state:'running',vod:'2'}]};
for(const value of [queue,{...queue,items:[{state:'running',vod:'1'}]},{...queue,root:'/other'},{...queue,active:false}]){view.setQueue(value);assert.equal($('global-jobs').hidden,true);}
view.setQueue(queue);const closes=moreClosed;view.update({...p,path:'/test-2',vod_id:'2'});
assert.equal(moreClosed,closes+1);view.update(p);assert.equal($('global-jobs').hidden,true);view.setQueue(null);
console.log('순차 작업 배너 미노출·선택 변경 메뉴 닫기 검사 통과');

const {connectDeletion}=await import('../web/project-delete.js');
let deleted=0,requests=[],resolvePreview;let selected=p;
connectDeletion({getProject:()=>selected,onDeleted:()=>{deleted++;},api:async(action,args)=>{
  requests.push(action);if(action==='delete-preview')return new Promise(resolve=>resolvePreview=resolve);return {};
}});
const preview={title:'확인할 자료',vod_id:'1',path:p.path,token:'test-token',bytes:100};
const opening=$('delete-project').onclick();assert.equal($('delete-dialog').open,true);
assert.equal($('delete-confirm').disabled,true);assert.equal(deleted,0);
$('delete-cancel').onclick();resolvePreview(preview);await opening;
assert.equal($('delete-dialog').open,false);assert.equal(deleted,0);
const second=$('delete-project').onclick();resolvePreview(preview);await second;
assert.equal(deleted,0);selected={...p,path:'/test-2'};
await $('delete-form').onsubmit({preventDefault(){}});assert.equal(deleted,0);assert.deepEqual(requests,['delete-preview','delete-preview']);
selected=p;await $('delete-form').onsubmit({preventDefault(){}});assert.equal(deleted,1);assert.equal(requests.at(-1),'delete-project');
console.log('삭제 모달 즉시 표시·취소 뒤 응답 무시·확인 버튼·대상 변경 차단 검사 통과 (가짜 API)');
