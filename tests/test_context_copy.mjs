import assert from 'node:assert/strict';
import {playbackRanges} from '../web/player-sequence.js';
import {createContextCopy,canCopyContext,hasUsableContextSummary} from '../web/context-copy.js';
import {commentText,restoreComment,commentRow,commentTimeText,editedCommentRange} from '../web/context-comment-model.js';

const created=[];
class Element{
  constructor(tag='div'){this.tag=tag;this.children=[];this.attributes={};this.value='';this.textContent='';this.disabled=false;created.push(this);}
  after(...values){this.afterNodes=values;}
  append(...values){for(const node of values){node.remove?.();if(typeof node==='object')node.parent=this;this.children.push(node);}}
  remove(){if(this.parent){this.parent.children=this.parent.children.filter(n=>n!==this);this.parent=null;}}
  replaceChildren(...values){for(const n of this.children)if(typeof n==='object')n.parent=null;this.children=[];this.append(...values);}
  setAttribute(k,v){this.attributes[k]=v;}
  showModal(){this.open=true;}
  close(){this.open=false;this.onclose?.();}
  focus(){this.focused=true;}
  select(){this.selectionEnd=this.value.length;}
}
const elements=new Map();
globalThis.document={createElement:tag=>new Element(tag),querySelectorAll:()=>created.filter(n=>n.commentSource),getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);}};
const $=id=>document.getElementById(id),rows=()=> $('context-comment-list').children, titles=()=>rows().map(r=>r.children[1].value);
const source=Array.from({length:10},(_,i)=>({id:`item-${i+1}`,start_ms:(i+1)*10000,end_ms:(i+1)*10000+5000,summary:{title:`주제 ${i+1}`}}));
const original=JSON.stringify(source),saved=new Map(),identity={root:'/검증',vod_id:'1',run:'a'.repeat(32)};
const api=async(action,data)=>{const value=saved.get(data.run)||{revision:0,text:'',selected:[],edited:false,basis:''};if(action==='context-comment')return structuredClone(value);assert.equal(data.draft.revision,value.revision);const result={...data.draft,revision:value.revision+1};saved.set(data.run,structuredClone(result));return result;};
let playback=[],seq={active:false},stops=0;
const player={sequenceState:()=>seq,onSequence(fn){this.listener=fn;},stopSequence(){stops++;seq={active:false};this.listener?.();},playSequence(value){playback=structuredClone(value);seq={active:true,index:0,total:value.length};this.listener();return true;},toggleSequence(){seq.paused=!seq.paused;this.listener();},seek(...args){this.stopSequence();this.sought=args;}};
let beforeUnload;globalThis.addEventListener=(event,fn)=>{if(event==='beforeunload')beforeUnload=fn;};
let copy=createContextCopy({api,player});
const check=(item,checked=true)=>{const input=copy.checkbox(item).children[0];input.checked=checked;input.onchange();return input;};
await copy.setItems(source,'VOD/요약',0,identity);
for(const i of [1,2,3,6,10])check(source[i-1]);
rows()[1].children[1].value='편집 <제목>';rows()[1].children[1].oninput();
check(source[3]);check(source[6]);
assert.deepEqual(titles(),['주제 1','편집 <제목>','주제 3','주제 4','주제 6','주제 7','주제 10']);
const editedNode=rows()[1].children[1];await copy.setItems(source,'VOD/요약',0,identity);
assert.equal(rows()[1].children[1],editedNode);assert.equal(titles()[1],'편집 <제목>');
check(source[3]);assert.equal(rows().length,7);
$('context-list-play').onclick();assert.deepEqual(playback.map(r=>r.start_ms),[10000,20000,30000,40000,60000,70000,100000]);
$('context-list-play').onclick();assert.equal(seq.paused,true);
$('context-list-play').onclick();assert.equal(seq.paused,false);
const visibleCheck=copy.checkbox(source[3]).children[0];rows()[3].children[2].onclick();assert.equal(visibleCheck.checked,false);assert.equal(rows().length,6);assert.equal(seq.active,false);
check(source[3]);check(source[3],false);assert.equal(rows().length,6);
let copied='';Object.defineProperty(globalThis,'navigator',{value:{clipboard:{async writeText(value){copied=value;}}},configurable:true});
await $('context-copy').onclick();assert.equal(copied,'00:00:10 주제 1\n00:00:20 편집 <제목>\n00:00:30 주제 3\n00:01:00 주제 6\n00:01:10 주제 7\n00:01:40 주제 10');
navigator.clipboard=undefined;await $('context-copy').onclick();assert.equal($('context-copy-fallback').value,copied);assert.equal($('context-copy-fallback').selectionEnd,copied.length);
rows()[0].children[1].onblur();await new Promise(r=>setTimeout(r,5));
copy=createContextCopy({api,player});await copy.setItems(source,'VOD/요약',0,identity);assert.equal(titles()[1],'편집 <제목>');assert.equal(copy.checkbox(source[1]).children[0].checked,true);
await copy.setItems(source.filter(r=>r.id!=='item-2'),'VOD/요약',0,identity);assert.equal(titles()[1],'편집 <제목>'); // 결과 갱신으로 직접 편집한 줄을 삭제하지 않음
const stale=copy.checkbox(source[0]).children[0];await copy.setItems(source,'다른 결과',0,{...identity,run:'b'.repeat(32)});stale.checked=true;stale.onchange();assert.equal(rows().length,0);
await copy.setItems(source,'VOD/요약',0,identity);globalThis.confirm=()=>false;$('context-copy-reset').onclick();assert.equal(rows().length,6);
globalThis.confirm=()=>true;$('context-copy-reset').onclick();assert.equal(rows().length,0);assert.equal(copy.checkbox(source[0]).children[0].checked,false);
assert.equal($('context-copy').disabled,true);assert.equal($('context-list-play').disabled,true);
let prevented=false;beforeUnload({preventDefault(){prevented=true;}});assert(prevented);await new Promise(r=>setTimeout(r,5));
assert.equal(saved.get(identity.run).rows.length,0);
const fail={...source[0],failed:true,copy_ready:false},gap={id:'gap',start_ms:0,end_ms:10000,gap:true};
await copy.setItems([fail,gap],'실패',3600000,{...identity,run:'c'.repeat(32)});check(fail);check(gap);
assert.deepEqual(titles(),['사용 가능한 전사 없음','요약 실패']);assert.equal(rows()[0].children[0].textContent,'01:00:00');
rows()[1].children[0].onclick();assert.deepEqual(player.sought,[10000,true,15000]);
for(const r of [fail,gap]){assert(!hasUsableContextSummary(r));for(const change of [{provisional:true},{time_review:true},{start_ms:-1},{start_ms:NaN},{end_ms:Infinity}])assert(!canCopyContext({...r,...change}));}
const legacy={revision:3,text:'01:00:20 직접 수정한 제목\n자유 문장\n01:50:00 연결 없는 시각',selected:['item-2'],edited:true,basis:''};
const migrated=restoreComment(legacy,source,3600000);
assert.equal(migrated.legacy_text,legacy.text);assert.equal(migrated.rows[0].source_id,'item-2');assert.equal(migrated.rows[0].end_ms,25000);
assert.equal(migrated.rows[1].start_ms,null);assert.equal(migrated.rows[2].end_ms,null);
assert.equal(commentText(migrated.rows,3600000),'01:00:20 직접 수정한 제목\n01:50:00 연결 없는 시각\n자유 문장');
saved.set('d'.repeat(32),legacy);await copy.setItems(source,'이전 메모',3600000,{...identity,run:'d'.repeat(32)});
assert.equal($('context-comment-legacy-text').textContent,legacy.text);assert.equal(rows().length,3);check(source[0]);assert.equal(titles()[1],'직접 수정한 제목');
await $('context-copy').onclick();await new Promise(r=>setTimeout(r,5));assert.equal(saved.get('d'.repeat(32)).legacy_text,legacy.text);
assert.equal(JSON.stringify(source),original);
// 클립의 제목은 summary 문자열이 아닌 title에 있으며 핵심 시각과 재생 시작은 다르다.
const candidates=[{id:'clip-b',title:'뒤 장면',summary:'줄거리',start_ms:30000,peak_ms:32000,end_ms:40000},
  {id:'clip-a',title:'앞 장면',summary:'줄거리',start_ms:10000,peak_ms:12000,end_ms:20000}];
const clipOriginal=JSON.stringify(candidates);await copy.setItems(candidates,'클립 목록',0,{...identity,run:'e'.repeat(32)});
check(candidates[0]);rows()[0].children[1].value='직접 고친 제목';rows()[0].children[1].oninput();check(candidates[1]);
assert.deepEqual(titles(),['앞 장면','직접 고친 제목']);
$('context-list-play').onclick();assert.deepEqual(playback.map(r=>[r.start_ms,r.end_ms]),[[10000,20000],[30000,40000]]);
navigator.clipboard={async writeText(value){copied=value;}};await $('context-copy').onclick();
assert.equal(copied,'00:00:10 앞 장면\n00:00:30 직접 고친 제목');
await copy.setItems([], '');await copy.setItems(candidates,'클립 목록',0,{...identity,run:'e'.repeat(32)});
assert.equal(copy.checkbox(candidates[0]).children[0].checked,true);assert.equal(titles()[1],'직접 고친 제목');
globalThis.confirm=()=>true;$('context-copy-reset').onclick();await copy.setItems([], '');
assert.equal(JSON.stringify(candidates),clipOriginal);
const noApi=createContextCopy({player});await noApi.setItems([], '');assert.equal($('context-copy').disabled,true);
console.log('시간순 중간 삽입·제목 편집/폴링 보존·선택 연동·구간 전달·복사 대안·저장 복원·초기화·기존 메모 보존·실패 선택·시각 보정 통과');

// 댓글 시각 편집은 원문·제목·선택 연결을 유지하며 정렬·복사·재생에만 반영한다.
assert.equal(commentTimeText(8123456),'02:15:23.456');
assert.deepEqual(editedCommentRange('01:00:12.345','01:00:15.006',3600000,120000),{start_ms:12345,end_ms:15006});
assert.deepEqual(editedCommentRange('01:00:12','',3600000,120000),{start_ms:12000,end_ms:null});
for(const [start,end] of [['bad',''],['00:60:00',''],['01:00:12','01:00:11'],['00:59:59',''],['01:02:00',''],['01:00:12','01:02:01']])assert.throws(()=>editedCommentRange(start,end,3600000,120000));
copy=createContextCopy({api,player});
const editable=[{...source[0],reaction_peaks:[12000,12000,3000,18000]},source[1]],editOriginal=JSON.stringify(editable),editIdentity={...identity,run:'f'.repeat(32)};
await copy.setItems(editable,'시각 편집',3600000,editIdentity,120000);check(editable[0]);check(editable[1]);
rows()[0].children[1].value='유지할 제목';rows()[0].children[1].oninput();rows()[0].children[3].onclick();
assert.equal($('comment-time-editor').open,true);assert.equal($('comment-time-start').value,'01:00:10');
assert.deepEqual($('comment-time-reaction').children.map(o=>o.value),['','3000','12000','18000']);
$('comment-time-reaction').value='12000';$('comment-time-reaction').onchange();
$('comment-time-form').onsubmit({preventDefault(){}});assert.equal($('comment-time-editor').open,false);
assert.equal(rows()[0].children[0].textContent,'01:00:12');assert.equal(titles()[0],'유지할 제목');assert.equal(copy.checkbox(editable[0]).children[0].checked,true);
rows()[0].children[3].onclick();$('comment-time-start').value='01:00:22';
$('comment-time-form').onsubmit({preventDefault(){}});assert.equal($('comment-time-editor').open,true);assert.match($('comment-time-error').textContent,/끝 시각/);assert.equal(rows()[0].children[0].textContent,'01:00:12');
await copy.setItems(editable,'시각 편집',3600000,editIdentity,120000);assert.equal($('comment-time-start').value,'01:00:22');
$('comment-time-end').value='01:00:25';$('comment-time-form').onsubmit({preventDefault(){}});
assert.deepEqual(titles(),['주제 2','유지할 제목']);assert.equal(copy.checkbox(editable[0]).children[0].checked,true);
await $('context-copy').onclick();assert.equal(copied,'01:00:20 주제 2\n01:00:22 유지할 제목');
$('context-list-play').onclick();assert.deepEqual(playback.map(r=>[r.start_ms,r.end_ms]),[[20000,25000],[22000,25000]]);
await copy.setItems([],'');copy=createContextCopy({api,player});await copy.setItems(editable,'시각 편집',3600000,editIdentity,120000);
assert.equal(rows()[1].children[0].textContent,'01:00:22');assert.equal(titles()[1],'유지할 제목');
rows()[1].children[3].onclick();$('comment-time-original').onclick();$('comment-time-form').onsubmit({preventDefault(){}});
assert.equal(rows()[0].children[0].textContent,'01:00:10');assert.equal(titles()[0],'유지할 제목');
rows()[0].children[3].onclick();$('comment-time-start').value='01:00:18';$('comment-time-end').value='';$('comment-time-form').onsubmit({preventDefault(){}});
assert.equal(rows()[0].children[0].disabled,true);$('context-list-play').onclick();assert.deepEqual(playbackRanges(playback),[{start:20000,end:25000}]);
rows()[0].children[3].onclick();$('comment-time-start').value='01:00:19';await copy.setItems([], '');assert.equal($('comment-time-editor').open,false);
assert.equal(saved.get(editIdentity.run).rows.find(r=>r.source_id===source[0].id).start_ms,18000);
assert.equal(JSON.stringify(editable),editOriginal);
console.log('댓글 반응 시각 선택·수동 수정·범위 검사·정렬/복사/재생·저장 복원·원문/제목/체크 보존·폴링/전환 검사 통과');

// 삭제 요청은 진행 중인 저장까지 기다리고, 저장 오류가 나면 실행하지 않는다.
let releaseSave,deleteCalls=0;
const deletingCopy=createContextCopy({player,api:async(action,args)=>{
  if(action==='context-comment')return {revision:0,format:2,rows:[],legacy_text:''};
  await new Promise(resolve=>releaseSave=resolve);
  return {...args.draft,revision:1};
}});
await deletingCopy.setItems(source,'삭제 검증',0,identity);
const deleteCheck=deletingCopy.checkbox(source[0]).children[0];deleteCheck.checked=true;deleteCheck.onchange();
rows()[0].children[1].value='보존할 편집';rows()[0].children[1].oninput();rows()[0].children[1].onblur();
const deleting=deletingCopy.deleteVersion('삭제 검증',async()=>{deleteCalls++;return '삭제 완료';});
assert.equal(rows()[0].children[1].disabled,true);assert.equal(deleteCalls,0);
releaseSave();assert.equal(await deleting,'삭제 완료');assert.equal(deleteCalls,1);assert.equal(rows().length,0);
const errorCopy=createContextCopy({api:async(action)=>{if(action==='context-comment')return {revision:0,format:2,rows:[],legacy_text:''};throw Error('저장 공간 부족');}});
await errorCopy.setItems(source,'실패 검증',0,identity);
const errorCheck=errorCopy.checkbox(source[0]).children[0];errorCheck.checked=true;errorCheck.onchange();
await assert.rejects(()=>errorCopy.deleteVersion('실패 검증',async()=>deleteCalls++),/저장 공간 부족/);
assert.equal(deleteCalls,1);assert.equal(rows()[0].children[1].disabled,false);assert.equal(rows()[0].children[1].value,'주제 1');
console.log('삭제 전 댓글 저장 대기·저장 실패 시 삭제 차단·편집 내용 유지 검사 통과');
