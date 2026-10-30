import assert from 'node:assert/strict';
import {Element,dom} from './polish_dom.mjs';
import {pagePolling,latestResponse} from '../web/page-lifecycle.js';
import {createEditSession} from '../web/edit-session.js';
import {studioCaptions} from '../web/studio-captions-ui.js';
import {resultBrowser,lazyDetails} from '../web/result-browser.js';
import {groupReactionTimes} from '../web/reaction-times.js';
import {createFramePreview} from '../web/clip-studio-preview.js';
import {fastConflicts} from '../web/studio-export-check.js';
import {studioHistory} from '../web/studio-history.js';
const flush=()=>new Promise(r=>setImmediate(r));
let $=dom();const target=new Element(),timers=new Map();let tick=0,calls=0,resolve;
const poll=pagePolling(()=>{calls++;return new Promise(r=>resolve=r);},1,{target,timers:{setInterval(fn){timers.set(++tick,fn);return tick;},clearInterval(id){timers.delete(id);}}});
assert.equal(calls,1);target.dispatchEvent({type:'pageshow'});await poll.refresh();assert.equal(timers.size,1);assert.equal(calls,1);
target.dispatchEvent({type:'pagehide'});assert.equal(timers.size,0);resolve();await flush();target.dispatchEvent({type:'pageshow'});assert.equal(calls,2);assert.equal(timers.size,1);resolve();poll.stop();
const latest=latestResponse(),a=latest.begin(),b=latest.begin();assert(!a());assert(b());
// 삭제 창을 바꿔 열었을 때 이전 작업 응답으로 대상이 바뀌지 않는다.
const historyHost=new Element(),historyCalls=[];let cleanRequest;
const historyUI=studioHistory({host:historyHost,identity:()=>({}),refresh:async()=>{},onError:assert.fail,api:async(action,data)=>{
 if(action==='studio-clean'){cleanRequest=data;return {};}
 return new Promise(resolve=>historyCalls.push(resolve));
}});
historyUI.set(['A','B'].map(id=>({id,kind:'start',state:'complete',created_at:'2026-10-29',outputs:{}})));
const historyDialog=document.body.children.at(-1);
const oldPreview=historyHost.children[0].children.at(-1).onclick();historyDialog.children[3].onclick();
const newPreview=historyHost.children[1].children.at(-1).onclick();historyCalls[1]({token:'B',bytes:0,folder:'B'});await newPreview;
historyCalls[0]({token:'A',bytes:0,folder:'A'});await oldPreview;await historyDialog.children[4].onclick();assert.equal(cleanRequest.run,'B');assert.equal(cleanRequest.token,'B');
// 이동 취소, 저장 실패, 저장 도중 입력 변경, 이탈 경고.
let data={nested:{value:'처음'}},written,fail=false;const events=new Element();globalThis.addEventListener=events.addEventListener.bind(events);
const session=createEditSession({read:()=>data,status:$('status'),save:async value=>{if(fail)throw Error('충돌');written=value;}});session.accept();data.nested.value='수정';session.changed();assert(session.dirty());
const dialog=document.body.children.at(-1);let choice=session.allow();dialog.children.at(-1).onclick();assert.equal(await choice,false);
fail=true;choice=session.allow();await dialog.children[2].onclick();assert(dialog.open);assert(session.dirty());fail=false;await dialog.children[2].onclick();assert(await choice);assert(!session.dirty());
data.nested.value='스냅샷';const save=session.save();data.nested.value='나중';await save;assert.equal(written.nested.value,'스냅샷');assert(session.dirty());
let warned=false;events.dispatchEvent({type:'beforeunload',preventDefault(){warned=true;}});assert(warned);
// 이전 초안의 소수 크기를 정수로 적용한 상태는 자동 저장되지 않고 변경으로 남는다.
data={options:{font_size:35}};const savedDraft={options:{font_size:34.682}};
session.accept(null,savedDraft);assert(session.dirty());assert.equal(savedDraft.options.font_size,34.682);assert.equal(written.nested.value,'스냅샷');
await session.save();assert.equal(written.options.font_size,35);assert(!session.dirty());
session.accept();assert(!session.dirty());
// 전사 A보다 B 응답이 먼저 와도 B만 표시하고 버전별 교정 유지.
$=dom();const pending=[],video=new Element();video.currentTime=0;const selected=()=>[{start_ms:0,end_ms:1000000}];let previewed;
const captions=studioCaptions({api:(_,request)=>new Promise((resolve,reject)=>pending.push({request,resolve,reject})),identity:()=>({}),video,selection:selected,onChange(){},onState(){},onPreview:row=>{previewed=row;}});
captions.init(0);$('caption-version').value='A';const loadA=captions.load();$('caption-version').value='B';const loadB=captions.load();
const rows=Array.from({length:550},(_,i)=>({id:String(i),start_ms:i*1000,end_ms:(i+1)*1000,text:'대사 '+i}));pending[1].resolve({rows});await loadB;pending[0].resolve({rows:[{...rows[0],text:'늦은 A'}]});await loadA;
assert.equal($('caption-rows').children.length,50);assert.equal($('caption-rows').children[0].children[1].value,'대사 0');
$('caption-search').value='대사 500';$('caption-search').oninput();const jump=$('caption-rows').children[0].children[0];jump.onclick();assert.equal(previewed.id,'500');assert.equal(previewed.start_ms,500000);let field=$('caption-rows').children[0].children[1];field.value='501번째 교정';field.oninput();assert.equal(captions.edits()['500'],'501번째 교정');
$('caption-version').value='A';const againA=captions.load();pending.at(-1).resolve({rows:[rows[0]]});await againA;assert.equal(captions.edits()['500'],undefined);
previewed=null;jump.onclick();assert.equal(previewed,null);
$('caption-version').value='B';const againB=captions.load();pending.at(-1).resolve({rows});await againB;assert.equal(captions.edits()['500'],'501번째 교정');
const failLoad=captions.load();pending.at(-1).reject(Error('연결 단절'));await failLoad;assert(captions.blocked());assert.equal(captions.versions().B['500'],'501번째 교정');
// 1/10/20시간 결과 전체를 탐색하지만 화면에는 25개만 만든다.
for(const hours of [1,10,20]){
 const host=new Element(),column=new Element(),items=Array.from({length:hours*60},(_,i)=>({id:String(i),start_ms:i*60000,end_ms:(i+1)*60000,title:'장면 '+i}));let visible;column.append(host);
 const browser=resultBrowser(host,()=>{visible=browser.slice(items);});visible=browser.slice(items);assert.equal(visible.length,25);
 const [prev,,next]=host.beforeNodes[0].children[3].children;
 host.scrollTop=900;next.onclick();assert.equal(visible[0].id,'25');assert.equal(host.scrollTop,0);assert(column.scrolled);
 column.scrolled=false;host.scrollTop=900;prev.onclick();assert.equal(visible[0].id,'0');assert.equal(host.scrollTop,0);assert(column.scrolled);assert(prev.disabled);
 assert(browser.locate(String(items.length-1)));assert(visible.some(r=>r.id===String(items.length-1)));
 const search=host.beforeNodes[0].children[0];search.value='장면 '+(items.length-1);search.oninput();assert.equal(visible.length,1);
}
const detail=new Element();let builds=0;lazyDetails(detail,()=>builds++);detail.dispatchEvent({type:'toggle'});assert.equal(builds,0);detail.open=true;detail.dispatchEvent({type:'toggle'});detail.dispatchEvent({type:'toggle'});assert.equal(builds,1);
const grouped=groupReactionTimes([1000,1050,1050,1100,1200],1100,2000);assert.equal(grouped.length,2);assert.deepEqual(grouped[0].raw,[1000,1050]);assert.deepEqual(grouped[1].raw,[1100,1200]);
const frames=new Map();let next=0;globalThis.window=new Element();globalThis.requestAnimationFrame=fn=>{frames.set(++next,fn);return next;};globalThis.cancelAnimationFrame=id=>frames.delete(id);createFramePreview(new Element(),()=>({}));assert.equal(frames.size,1);window.dispatchEvent({type:'pagehide'});assert.equal(frames.size,0);window.dispatchEvent({type:'pageshow'});window.dispatchEvent({type:'pageshow'});assert.equal(frames.size,1);
const opts={speed:'fast',mode:'separate',ratio:'original',layout:'single',size:'source',caption:false,sidecar:false,volume:100,brightness:0,contrast:1,saturation:1,fade:0};assert.equal(fastConflicts(opts,null).length,0);assert.deepEqual(fastConflicts({...opts,sidecar:true},{transcript_run:'B'}),['편집용 자막 끄기']);assert.equal(fastConflicts({...opts,speed:'exact',caption:true},null).length,0);
console.log('P01~P10: 이동/충돌/교정 보존, 응답 역전, 501번째 자막, 1·10·20시간 탐색, 반응 경계, 타이머·프레임 복귀 통과');
