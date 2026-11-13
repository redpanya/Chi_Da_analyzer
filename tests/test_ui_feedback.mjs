import test from 'node:test';
import assert from 'node:assert/strict';
import {showToast,exposeDetails} from '../web/ui-feedback.js';
import {showPreviewToast} from '../web/preview-toast.js';

class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.textContent='';}
 append(...items){for(const item of items){item.parent=this;this.children.push(item);}}
 setAttribute(key,value){this.attributes[key]=value;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(item=>item!==this);}
}
const body=new Element('body'),timers=new Map(),intervals=new Map();let tick=0,now=0;
globalThis.document={body,createElement:tag=>new Element(tag),getElementById:id=>body.children.find(item=>item.id===id)};
globalThis.setTimeout=(fn,ms)=>{const id=++tick;timers.set(id,{fn,ms});return id;};globalThis.clearTimeout=id=>timers.delete(id);
globalThis.setInterval=(fn,ms)=>{const id=++tick;intervals.set(id,{fn,ms});return id;};globalThis.clearInterval=id=>intervals.delete(id);
Date.now=()=>now;
const region=()=>document.getElementById('ui-toasts'),items=()=>region()?.children||[];
const dismissAll=()=>{for(const item of [...items()])item.children.at(-1).onclick();};
const countdown=()=>items()[0].children.find(item=>item.className==='ui-toast-countdown');

test('작업 알림은 15초 후 닫히고 같은 키의 중복 노출을 막는다',()=>{
 showToast('처리 중',{key:'job-1'});showToast('진행률 변경',{key:'job-1'});
 assert.equal(items().length,1);assert.equal(timers.size,1);assert.equal([...timers.values()][0].ms,15000);assert.equal(region().attributes['aria-live'],'polite');
 assert.equal(countdown().textContent,'15초 후 닫힘');assert.equal(countdown().attributes['aria-hidden'],'true');
 now+=1000;[...intervals.values()][0].fn();assert.equal(countdown().textContent,'14초 후 닫힘');
 now+=5500;[...intervals.values()][0].fn();assert.equal(countdown().textContent,'9초 후 닫힘','지연된 갱신에서도 실제 남은 시간을 표시한다');
 now+=8500;[...intervals.values()][0].fn();assert.equal(countdown().textContent,'0초 후 닫힘');
 [...timers.values()][0].fn();assert.equal(items().length,0);assert.equal(timers.size,0);assert.equal(intervals.size,0);
});

test('토스트 동작은 알림을 닫은 후 1번 실행하고 닫기 버튼은 작업을 실행하지 않는다',()=>{
 let opened=0;showToast('작업 열기',{key:'open',action:()=>{assert.equal(items().length,0);opened++;}});
 items()[0].children[1].onclick();assert.equal(opened,1);assert.equal(timers.size,0);assert.equal(intervals.size,0);
 showToast('작업 열기',{key:'dismiss',action:()=>opened++});items()[0].children.at(-1).onclick();assert.equal(opened,1);assert.equal(items().length,0);assert.equal(intervals.size,0);
});

test('동시 알림은 최대 4개이며 오래된 알림부터 닫고 HTML 내용을 실행하지 않는다',()=>{
 const message='<img src=x onerror=run()> 오류';
 for(let i=0;i<5;i++)showToast(message,{key:'limit-'+i});
 assert.equal(items().length,4);assert.equal(timers.size,4);assert.equal(intervals.size,4);assert.equal(items()[0].children[0].textContent,message);assert.equal(items()[0].children[0].tagName,'span');
 dismissAll();assert.equal(items().length,0);assert.equal(timers.size,0);assert.equal(intervals.size,0);
});

test('개발 미리보기 안내도 공통 토스트의 남은 시간과 닫기를 사용한다',()=>{
 showPreviewToast(false);assert.equal(items().length,0);
 showPreviewToast(true);showPreviewToast(true);assert.equal(items().length,1);
 assert.match(items()[0].children[0].textContent,/주석 호환 모드/);assert.equal(countdown().textContent,'15초 후 닫힘');
 [...timers.values()][0].fn();assert.equal(items().length,0);assert.equal(intervals.size,0);
});

test('접힘 영역은 기본·동적 추가·재닫기 때 열리고 내부 조작과 숨긴 자료는 유지한다',()=>{
 class DetailElement extends Element{
  constructor(tag){super(tag);this.open=false;this.hidden=false;this.listeners={};const classes=new Set();this.classList={add:value=>classes.add(value),contains:value=>classes.has(value)};}
  get parentElement(){return this.parent;}
  matches(selector){return selector.split(',').includes(this.tagName);}
  querySelectorAll(selector){return this.children.flatMap(child=>[...(child.matches?.(selector)?[child]:[]),...(child.querySelectorAll?.(selector)||[])]);}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  closest(selector){for(let node=this;node;node=node.parentElement)if(node.matches?.(selector))return node;return null;}
  addEventListener(type,fn){this.listeners[type]=fn;}
 }
 const make=tag=>new DetailElement(tag),root=make('section'),details=make('details'),summary=make('summary'),label=make('span'),hidden=make('details'),hiddenParent=make('section'),hiddenChild=make('details');
 summary.append(label);details.append(summary);hidden.hidden=true;hiddenParent.hidden=true;hiddenParent.append(hiddenChild);root.append(details,hidden,hiddenParent);
 const previousObserver=globalThis.MutationObserver;let notify,observed;
 globalThis.MutationObserver=class{constructor(callback){notify=callback;}observe(target,options){observed={target,options};}};
 try{
  exposeDetails(root);assert.equal(details.open,true);assert.equal(details.classList.contains('always-visible'),true);assert.equal(summary.tabIndex,-1);
  assert.equal(hidden.hidden,true);assert.equal(hiddenParent.hidden,true,'hidden 상태는 강제로 해제하지 않는다');
  assert.equal(observed.target,root);assert.deepEqual(observed.options.attributeFilter,['open']);assert.equal(observed.options.subtree,true);
  const direct=make('details'),container=make('div'),nested=make('details');container.append(nested);root.append(direct,container);
  notify([{type:'childList',addedNodes:[direct,container,{nodeType:3}]}]);assert.equal(direct.open,true);assert.equal(nested.open,true);
  details.open=false;notify([{type:'attributes',target:details}]);assert.equal(details.open,true);
  let prevented=0;root.listeners.click({target:label,preventDefault(){prevented++;}});assert.equal(prevented,1,'일반 제목 클릭은 접힘을 막는다');
  for(const tag of ['button','a','input','select','textarea']){
   const control=make(tag),inner=make('span');control.append(inner);summary.append(control);
   let invoked=0;control.onclick=()=>invoked++;
   root.listeners.click({target:inner,preventDefault(){assert.fail('내부 조작을 차단하면 안 됩니다.');}});control.onclick();assert.equal(invoked,1);
  }
  assert.equal(hidden.hidden,true);assert.equal(hiddenParent.hidden,true);
 }finally{globalThis.MutationObserver=previousObserver;}
});
