import assert from 'node:assert/strict';
import {createBackground} from '../web/context-background.js';
class Element{value='';textContent='';disabled=false;}
const nodes=new Map();globalThis.document={getElementById(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);}};
const $=id=>document.getElementById(id),flush=()=>new Promise(resolve=>setImmediate(resolve));
const store=new Map(),pending=[];let deferred=false,localMode='detail',externalMode='detail';
const api=async(action,args)=>{
  if(deferred)return new Promise(resolve=>pending.push({action,args,resolve}));
  const previous=store.get(args.vod_id)||{text:'혼합 방송',custom_requests:{detail:'설명도 포함',timestamps:'목차',clips:'짧은 반응'}};
  if(action.endsWith('-save')){const next={text:args.text,custom_requests:{...previous.custom_requests,[args.mode]:args.custom_request}};store.set(args.vod_id,next);return structuredClone(next);}
  return structuredClone(previous);
};
const errors=[];let loads=0;
const local=createBackground({api,message:v=>errors.push(v),prefix:'local',mode:()=>localMode});
const external=createBackground({api,message:v=>errors.push(v),prefix:'external',mode:()=>externalMode,onLoad:()=>loads++});
const project={root:'/test',vod_id:'1',path:'/test/vod-1'};
await local.setProject(project);await external.setProject(project);
assert.equal(local.values().background,'혼합 방송');assert.equal(local.values().custom_request,'설명도 포함');
$('local-custom').value='중요한 정정 포함';$('local-custom').oninput();
localMode='timestamps';local.selectMode();assert.equal(local.values().custom_request,'목차');
localMode='detail';local.selectMode();assert.equal(local.values().custom_request,'중요한 정정 포함');
$('local-background').value='노래 후 게임';$('local-background').oninput();await local.save();
assert.deepEqual(local.values(),external.values());assert.equal(external.values().background,'노래 후 게임');
// 다른 화면의 저장과 상태 폴링이 입력 중 초안을 덮지 않는다.
$('external-custom').value='입력 중 요청';$('external-custom').oninput();
$('local-custom').value='새 기본 요청';$('local-custom').oninput();await local.save();
assert.equal(external.values().custom_request,'입력 중 요청');external.setProject({...project});assert.equal(external.values().custom_request,'입력 중 요청');
// 저장한 외부 작업서는 열 때만 표시하고 새로운 기본 설정 저장으로 바꾸지 않는다.
external.useSnapshot({background:'옛 상황',custom_request:'옛 요청'});
$('local-background').value='새 기본 상황';$('local-background').oninput();await local.save();
assert.equal(external.values().background,'옛 상황');assert.equal(external.values().custom_request,'옛 요청');
externalMode='clips';external.selectMode();assert.equal(external.values().background,'새 기본 상황');assert.equal(external.values().custom_request,'짧은 반응');
// 저장 중 다른 VOD를 선택하면 이전 설정으로 새 VOD 분석을 시작하지 않는다.
deferred=true;const saving=local.save();const old=pending.at(-1);
const loading=local.setProject({...project,vod_id:'2',path:'/test/vod-2'});const newLoad=pending.at(-1);
newLoad.resolve({text:'두번째 VOD',custom_requests:{detail:'다른 요청'}});await loading;
old.resolve({text:'첫 VOD 저장',custom_requests:{detail:'이전 요청'}});assert.equal(await saving,false);
assert.equal(local.values().background,'두번째 VOD');assert.equal(local.values().custom_request,'다른 요청');
const lateLoad=local.setProject({...project,vod_id:'3',path:'/test/vod-3'});const late=pending.at(-1);await local.setProject(null);
late.resolve({text:'이미 닫힌 VOD',custom_requests:{}});await lateLoad;await flush();
assert.equal(local.ready(),false);assert.equal(local.values().background,'');assert.deepEqual(errors,[]);assert.ok(loads>=3);
console.log('공통 설정 UI: 모드별 초안·화면 간 공유·작업서 동결·늦은 저장/읽기 응답 보존 검사 통과');
