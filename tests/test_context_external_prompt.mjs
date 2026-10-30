import assert from 'node:assert/strict';
import {createExternal} from '../web/context-external.js';
class Element{
  value='';textContent='';disabled=false;hidden=false;children=[];checked=false;
  replaceChildren(...items){this.children=items;}append(...items){this.children.push(...items);}
}
const nodes=new Map();
globalThis.document={createElement:()=>new Element(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);}};
const $=id=>document.getElementById(id),pending=[],calls=[];
let bundle;
const api=async(action,args)=>{
  calls.push({action,args});
  if(action==='context-background')return {text:'게임과 노래',custom_requests:{}};
  if(action==='context-background-save')return {text:args.text,custom_requests:{[args.mode]:args.custom_request}};
  if(action.endsWith('-prompt'))return new Promise(resolve=>pending.push({args,resolve}));
  if(action.endsWith('-create'))return bundle;
  if(action.endsWith('-list'))return [];
};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const finish=async(index,text)=>{pending[index].resolve({prompt:text});await flush();};
$('external-mode').value='timestamps';$('external-offset').valueAsNumber=0;
const view=createExternal({api}),project={path:'/vod-1',root:'/test',vod_id:'1',metadata:{title:'독립 가상 VOD'},context:{inputs:{transcripts:[{id:'a',label:'검증 전사',complete:true}]}}};
view.setProject(project);await flush();assert.equal(pending[0].args.mode,'timestamps');assert.equal($('external-copy').disabled,true);
await finish(0,'타임스탬프 요청');assert.equal($('external-prompt').value,'타임스탬프 요청');
// 빠르게 모드를 바꾸어도 먼저 시작한 응답이 최신 탭의 요청문을 덮지 않는다.
view.selectMode('detail');view.selectMode('clips');
await finish(2,'클립 요청');await finish(1,'느린 상세 요청');assert.equal($('external-prompt').value,'클립 요청');
$('external-custom').value='노래 제목을 넣어 주세요';$('external-custom').oninput();
assert.equal($('external-copy').disabled,true);await new Promise(resolve=>setTimeout(resolve,230));
assert.equal(pending[3].args.custom_request,'노래 제목을 넣어 주세요');await finish(3,'추가 요청 포함 클립');
view.setProject({...project});assert.equal($('external-custom').value,'노래 제목을 넣어 주세요');assert.equal(pending.length,4);
view.selectMode('detail');assert.equal($('external-custom').value,'');await finish(4,'상세 요청');
view.selectMode('clips');assert.equal($('external-custom').value,'노래 제목을 넣어 주세요');await finish(5,'추가 요청 포함 클립');
bundle={id:'a'.repeat(32),mode:'clips',custom_request:'노래 제목을 넣어 주세요',prompt:'전체 목록 포함 저장 요청',files:[],speech_count:6,chat_count:0,rejected_count:0};
await $('external-create').onclick();
assert.equal(calls.find(c=>c.action.endsWith('-create')).args.options.custom_request,bundle.custom_request);
assert.equal($('external-prompt').value,bundle.prompt);assert.match($('external-prompt-status').textContent,/저장한/);
view.setProject({...project});assert.equal($('external-prompt').value,bundle.prompt);
// 프로젝트 전환 뒤 도착한 응답은 버리고 다른 VOD로 추가 요청을 전파하지 않는다.
view.selectMode('detail');view.setProject({...project,path:'/vod-2',vod_id:'2'});
assert.equal($('external-custom').value,'');await flush();await finish(7,'두번째 VOD');await finish(6,'이전 VOD');
assert.equal($('external-prompt').value,'두번째 VOD');
view.selectMode('clips');view.setProject(null);await finish(8,'닫힌 VOD');
assert.equal($('external-prompt').value,'');assert.equal($('external-copy').disabled,true);
console.log('외부 요청 UI: 모드 자동 선택·미리보기·추가 요청·저장 전달·폴링 보존·역순 응답·VOD 전환 검사 통과');
