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
globalThis.document={body,createElement:tag=>new Element(tag),querySelector:()=>body.children.find(n=>n.open)};
globalThis.MutationObserver=class{observe(){}};
const input=new Element('input');input.value='기존 입력';const check=new Element('input');check.checked=false;
const group=new Element('fieldset');group.append(input,check);body.append(group);
const start=new Element('button'),opener=new Element('button');let starts=0;start.onclick=()=>starts++;
const panel=createSettingsPanel('settings','설정',[group],[start]);
assert.equal(panel.body.children.includes(group),true);assert.equal(group.children[0],input);
panel.open(opener);input.value='편집';check.checked=true;panel.close();assert.equal(input.value,'편집');assert.equal(focused,opener);assert.equal(starts,0);
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
let closed=0,accepted=0,opened=0,stopped=0,moreClosed=0;
const settings={close(){closed++;},accepted(){accepted++;}};
const view=createWorkspaceStatus({closeMore(){moreClosed++;},panels:[],versions:[],contextSettings:settings,clipSettings:settings,speechSettings:settings,voiceSettings:settings});
const p={root:'/library',vod_id:'1',path:'/test-1',metadata:{title:'상태 검증',duration:60},tasks:{video:{state:'complete'},chat:{state:'complete'}},speech:{state:'idle'},voices:{state:'idle'},context:{state:'idle',inputs:{}}};
view.update(p);assert.equal($('global-jobs').hidden,true);assert.equal($('context-job').dataset.idle,'true');
const running={...p,context:{...p.context,state:'running',action:'clips',owned:true,message:'클립 검토 중'}};const original=JSON.stringify(running);
view.update(running);assert.equal(accepted,2);assert.equal(closed,2);assert.equal($('global-jobs').hidden,false);
$('step6').click=()=>opened++;$('context-stop').click=()=>stopped++;
const job=$('global-job-rows').children[0];job.children[1].onclick();job.children[2].onclick();assert.equal(opened,1);assert.equal(stopped,1);
view.navigate(6);assert.equal($('global-jobs').hidden,true);assert.equal(JSON.stringify(running),original);
view.navigate(3);view.update({...running,context:{state:'error',action:'clips',message:'입력 읽기 실패',owned:false}});
assert.equal($('global-jobs').hidden,false);assert.equal($('global-job-rows').children[0].children[2].hidden,true);assert.match($('global-job-rows').children[0].children[0].textContent,/입력 읽기 실패/);
view.update(null);assert.equal($('download-details').hidden,true);assert.equal($('global-job-rows').children.length,0);
console.log('다른 페이지 진행/오류 노출·중단/열기 연결·작업 수락 시 패널 닫기·원본 상태 불변 검사 통과');

view.update(p);view.navigate(2);assert.equal($('queue-section').hidden,true);assert.equal($('download-details').hidden,false);assert.equal($('lock-note').hidden,true);assert.match($('workspace-subtitle').textContent,/상태 검증/);
view.navigate(1);assert.equal($('queue-section').hidden,false);assert.equal($('download-details').hidden,true);
view.navigate(9);assert.equal($('queue-section').hidden,true);assert.equal($('download-details').hidden,true);assert.match($('workspace-subtitle').textContent,/폴더/);
console.log('등록·저장 VOD·설정 화면 분리 검사 통과');
const {showPreviewToast}=await import('../web/preview-toast.js');
let timer=null,delay=null;globalThis.setTimeout=(fn,ms)=>{timer=fn;delay=ms;return 1;};globalThis.clearTimeout=()=>{timer=null;};
$('preview-toast').hidden=true;$('notice').textContent='유지할 오류';showPreviewToast(false);assert.equal($('preview-toast').hidden,true);
showPreviewToast(true);assert.equal($('preview-toast').hidden,false);assert.equal(delay,6000);
$('preview-toast').onmouseenter();assert.equal(timer,null);$('preview-toast').onmouseleave();timer();assert.equal($('preview-toast').hidden,true);assert.equal($('notice').textContent,'유지할 오류');
showPreviewToast(true);$('preview-toast-close').onclick();assert.equal($('preview-toast').hidden,true);
console.log('토스트 노출·자동 닫기·포인터 체류 유지·오류 유지 검사 통과');

view.update(p);view.navigate(2);
const queue={active:true,root:'/library',items:[{state:'running',vod:'2'}]};
view.setQueue(queue);assert.equal($('global-jobs').hidden,true);
view.setQueue({...queue,items:[{state:'running',vod:'1'}]});assert.equal($('global-queue-state').hidden,false);
view.setQueue({...queue,root:'/other',items:[{state:'running',vod:'1'}]});assert.equal($('global-jobs').hidden,true);
view.setQueue({...queue,active:false});assert.equal($('global-jobs').hidden,true);
view.setQueue(queue);const closes=moreClosed;view.update({...p,path:'/test-2',vod_id:'2'});
assert.equal(moreClosed,closes+1);assert.equal($('global-queue-state').hidden,false);
view.update(p);assert.equal($('global-jobs').hidden,true);view.setQueue(null);
console.log('진행 VOD·보관함 일치 알림, 선택 변경 메뉴 닫기 검사 통과');

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
$('delete-confirmation').value='wrong';$('delete-confirmation').oninput();assert.equal($('delete-confirm').disabled,true);
$('delete-confirmation').value='1';$('delete-confirmation').oninput();assert.equal($('delete-confirm').disabled,false);
assert.equal(deleted,0);selected={...p,path:'/test-2'};
await $('delete-form').onsubmit({preventDefault(){}});assert.equal(deleted,0);assert.deepEqual(requests,['delete-preview','delete-preview']);
selected=p;await $('delete-form').onsubmit({preventDefault(){}});assert.equal(deleted,1);assert.equal(requests.at(-1),'delete-project');
console.log('삭제 모달 즉시 표시·취소 뒤 응답 무시·번호 확인·대상 변경 차단 검사 통과 (가짜 API)');
