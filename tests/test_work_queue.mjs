import assert from 'node:assert/strict';
import {dom,Element} from './polish_dom.mjs';
import {createWorkQueue} from '../web/work-queue.js';

dom();document.head=new Element('head');
globalThis.CustomEvent=class {constructor(type,{detail}){this.type=type;this.detail=detail;}};
let poll,interval,items=[],unavailable=false;const calls=[],changes=[];
globalThis.setInterval=(fn,ms)=>{poll=fn;interval=ms;};
globalThis.fetch=async(url,options)=>{
  calls.push([url,options]);
  if(unavailable)throw Error('일시적인 연결 오류');
  return {ok:true,json:async()=>({items})};
};
document.addEventListener('work-queue-change',e=>changes.push(e.detail));
const previousBody=[...document.body.children],previousHead=[...document.head.children];
const ui=createWorkQueue();
await new Promise(setImmediate);
assert.equal(interval,1500);assert.deepEqual(document.body.children,previousBody);assert.deepEqual(document.head.children,previousHead);
const task={id:'a',action:'analyze',label:'채팅 분석',title:'검사',root:'/library',vod_id:'1'};
// 첫 갱신 전에 끝난 짧은 분석도 결과 화면을 갱신한다.
items=[{...task,state:'complete'}];await poll();
assert.equal(changes.length,1);assert.equal(changes[0].state,'complete');
await poll();assert.equal(changes.length,1);
items=[{...task,state:'queued'}];await poll();
assert.equal(changes.at(-1).state,'queued');
assert.throws(()=>ui.accept({queued:items[0]}),e=>e.queued===true&&/대기열에 등록/.test(e.message)&&/‘진행 상태’/.test(e.message)&&!/작업 대기열/.test(e.message));
await new Promise(setImmediate);
const active={id:'running-job'};assert.equal(ui.accept(active),active);
// 취소는 진행 상태 페이지가 실행하며 이 모듈은 완료·취소 변경을 계속 전달한다.
items=[{...task,state:'cancelled'}];await poll();assert.equal(changes.at(-1).state,'cancelled');
const eventCount=changes.length;unavailable=true;await poll();assert.equal(changes.length,eventCount);
unavailable=false;items=[{...task,state:'running'}];await poll();assert.equal(changes.length,eventCount+1);assert.equal(changes.at(-1).state,'running');
assert.ok(calls.every(([url])=>url==='api/work-queue'),'공용 폴링에서 취소·실행 API를 호출하지 않음');
assert.deepEqual(document.body.children,previousBody);assert.deepEqual(document.head.children,previousHead);
console.log('별도 대기열 UI 미생성·15초 토스트와 독립적인 상태 폴링·중복 억제·즉시 완료/취소 전달·진행 상태 안내·조회 실패 복구 검사 통과');
