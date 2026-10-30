import assert from 'node:assert/strict';
import {createClipResults} from '../web/context-clips.js';
class Element{
  setAttribute(k,v){(this.attributes??={})[k]=v;}
  addEventListener(k,v){(this.listeners??={})[k]=v;}
  before(value){this.beforeNode=value;}
  value='';textContent='';disabled=false;children=[];dataset={};classList={toggle(){}};
  querySelectorAll(){return [];}
  replaceChildren(...items){this.children=items;} append(...items){this.children.push(...items);}
}
const nodes=new Map();globalThis.document={addEventListener(){},createElement:()=>new Element(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);}};
const $=id=>document.getElementById(id),pending=[],seeks=[];let clears=0;
const api=(action,args)=>new Promise((resolve,reject)=>pending.push({action,args,resolve,reject}));
const view=createClipResults({api,player:{seek(...args){seeks.push(args);},clearRange(){clears++;}}});
const run={id:'clip-1',mode:'clips',label:'외부 클립',title:'한국어 수동 교정'},old={id:'detail',mode:'detail'};
const project={path:'/vod-1',root:'/test',vod_id:'1',tasks:{video:{state:'complete'}},context:{clip_run:run.id,runs:[old,run]}};
const candidate={title:'<img src=x onerror=alert(1)>',summary:'대화 내용',reason:'독립적으로 이해 가능한 반전',context_note:'규칙 설명',video_checks:['말투와 화면 확인'],uncertainties:['겹친 목소리'],review_needed:true,chat_summary:'웃음 반응',evidence:[{start_ms:1000,text:'근거 대사'}],chat_evidence:[{start_ms:2500,text:'ㅋㅋ'}],start_ms:1000,peak_ms:2000,end_ms:3000};
const value={mode:'clips',items:[candidate],complete:false,done:2,total:5,input_label:'한국어 · 교정 포함',stale:false};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
view.setProject(project);assert.equal(pending.length,1);assert.equal($('context-clips-version').children.length,1);
pending[0].resolve(value);await flush();assert.match($('context-clips-status').textContent,/일부 묶음/);
const card=$('context-clips-result').children[0],actions=card.children.find(e=>e.className==='play-actions');
assert.equal(card.children.find(e=>e.textContent.includes('<img')).textContent,'1. '+candidate.title);
actions.children[0].onclick();actions.children[1].onclick();assert.deepEqual(seeks,[[1000,true,3000],[2000,true,3000]]);
view.setProject(structuredClone(project));assert.equal(pending.length,1); // 상태 폴링으로 목록과 재생을 초기화하지 않는다.
const refresh=view.openRun(run.id);const stale=pending.at(-1);
view.setProject({...project,path:'/vod-2',vod_id:'2',context:{runs:[]}});
stale.resolve(value);await refresh;assert.equal($('context-clips-result').children.length,0);
assert.equal($('context-clips-version').disabled,true);assert.match($('context-clips-status').textContent,/가져오면/);
view.setProject({...project,tasks:{video:{state:'error'}}});pending.at(-1).resolve(value);await flush();
$('context-clips-result').children[0].children.find(e=>e.className==='play-actions').children[0].onclick();
assert.equal(seeks.length,2);assert.match($('context-clips-status').textContent,/영상이 준비/);
const request=view.openRun(run.id);pending.at(-1).resolve({...value,items:[],complete:true});await request;
assert.match($('context-clips-result').children[0].textContent,/추천 후보가 없습니다/);
assert.ok(clears>=3);
console.log('클립 UI: 별도 버전·안전한 텍스트 표시·구간/핵심 재생·폴링 유지·늦은 응답 무시·미준비/빈 결과 검사 통과');
