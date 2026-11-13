import assert from 'node:assert/strict';
import {createTaskTabs} from '../web/workspace-layout.js';
import {createVoiceTabs} from '../web/voice-tabs.js';

// 실제 API 없이 원래 폼·선택·검사 결과가 탭 전환 뒤에도 같은 노드인지 확인한다.
let focused = null;
class Element {
  constructor(tag) {this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.dataset={};this.hidden=false;}
  append(...items) {for(const item of items){item.remove();item.parentElement=this;this.children.push(item);}}
  prepend(item) {item.remove();item.parentElement=this;this.children.unshift(item);}
  remove() {if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(item=>item!==this);this.parentElement=null;}
  setAttribute(key,value) {this.attributes[key]=String(value);}
  focus() {focused=this;}
  animate() {this.animationCount=(this.animationCount||0)+1;return {cancel(){}};}
}
globalThis.document={createElement:tag=>new Element(tag)};
const make=tag=>document.createElement(tag);
const external=make('section'),exportPanel=make('section'),importPanel=make('section'),historyPanel=make('section');
const request=make('textarea'),file=make('input'),preview=make('div'),accept=make('input'),run=make('button');
request.value='기존 추가 요청';file.files=[{name:'결과.zip'}];preview.textContent='정상 2개 · 수정 필요 1개';accept.checked=true;
let writes=0;run.onclick=()=>writes++;exportPanel.append(request);importPanel.append(file,preview,accept,run);
const tabs=createTaskTabs(external,[['export','자료 내보내기',exportPanel],['import','결과 가져오기',importPanel],['history','작업 목록',historyPanel]],'external-task','외부 AI 파일 작업');
assert.equal(exportPanel.animationCount,undefined);
assert.equal(external.children[0],tabs.tabs);assert.equal(exportPanel.hidden,false);assert.equal(importPanel.hidden,true);
assert.equal(tabs.tabs.attributes.role,'tablist');
assert.equal(tabs.tabs.children[0].attributes['aria-controls'],exportPanel.id);
assert.equal(importPanel.attributes['aria-labelledby'],tabs.tabs.children[1].id);
tabs.tabs.children[1].onclick();assert.equal(importPanel.hidden,false);assert.equal(exportPanel.hidden,true);
assert.equal(importPanel.animationCount,1);tabs.select('import');assert.equal(importPanel.animationCount,1);
tabs.select('history');tabs.select('export');tabs.select('import');
assert.equal(exportPanel.children[0],request);assert.equal(request.value,'기존 추가 요청');
assert.equal(importPanel.children[0],file);assert.equal(file.files[0].name,'결과.zip');assert.equal(accept.checked,true);
assert.equal(preview.textContent,'정상 2개 · 수정 필요 1개');assert.equal(writes,0,'탭 전환은 저장·등록을 실행하지 않는다');
run.onclick();assert.equal(writes,1,'원래 클릭 핸들러 유지');
let prevented=0;
const key=(index,value)=>tabs.tabs.children[index].onkeydown({key:value,preventDefault(){prevented++;}});
key(1,'ArrowRight');assert.equal(external.dataset.taskTab,'history');assert.equal(focused,tabs.tabs.children[2]);
key(2,'ArrowRight');assert.equal(external.dataset.taskTab,'export');
key(0,'ArrowLeft');assert.equal(external.dataset.taskTab,'history');
key(2,'Home');assert.equal(external.dataset.taskTab,'export');
key(0,'End');assert.equal(external.dataset.taskTab,'history');assert.equal(prevented,5);
assert.equal(tabs.tabs.children.filter(button=>button.tabIndex===0).length,1);
assert.equal(tabs.tabs.children.filter(button=>button.attributes['aria-selected']==='true').length,1);
key(2,'Enter');assert.equal(prevented,5);
assert.equal(tabs.select('missing'),false);assert.equal(external.dataset.taskTab,'history');
const report=make('section'),runs=make('section'),errors=make('section');
const logs=createTaskTabs(report,[['runs','실행 리포트',runs],['errors','오류 기록',errors]],'report-task','작업 기록 종류');
logs.select('errors');assert.equal(errors.hidden,false);assert.equal(runs.hidden,true);assert.equal(external.dataset.taskTab,'history');
const voiceNodes=new Map();
for(const name of ['speakers','assigned','failed']){voiceNodes.set('voice-view-'+name,make('button'));voiceNodes.set('voice-pane-'+name,make('section'));}
document.getElementById=id=>voiceNodes.get(id);
const voices=createVoiceTabs();voices.select('assigned',true);
assert.equal(voiceNodes.get('voice-pane-assigned').animationCount,1);
assert.equal(voiceNodes.get('voice-pane-assigned').hidden,false);
assert.equal(focused,voiceNodes.get('voice-view-assigned'));
voices.select('assigned');voices.select('missing');assert.equal(voices.current(),'assigned');
assert.equal(voiceNodes.get('voice-pane-assigned').animationCount,1);
voices.reset();assert.equal(voices.current(),'speakers');assert.equal(voiceNodes.get('voice-pane-assigned').hidden,true);
console.log('외부AI·리포트 탭: 원본 폼/파일/검사/동의/이벤트 유지, 키보드 전환, 독립 상태, 자동 실행 없음 확인');
