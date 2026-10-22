import assert from 'node:assert/strict';
import {createContextCopy} from '../web/context-copy.js';
import {contextReactionRows} from '../web/context-tree.js';

class Element{
  value='';textContent='';disabled=false;children=[];attributes={};
  append(...values){this.children.push(...values);}
  setAttribute(name,value){this.attributes[name]=value;}
  focus(){this.focused=true;}
  select(){this.selectionStart=0;this.selectionEnd=this.value.length;}
}
const elements=new Map();
globalThis.document={createElement:()=>new Element(),getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);}};
const el=id=>document.getElementById(id),text=el('context-comment-text'),notice=el('context-copy-notice');
const copy=createContextCopy(),a={start_ms:100000,end_ms:110000,summary:{title:'질문\n \t 답변'},reaction_count:2};
const b={start_ms:3661999,end_ms:3670000,summary:{title:'다음 <이야기>'}};
const gap={start_ms:0,end_ms:100000,gap:true},before=JSON.stringify([a,b,gap]);
const check=(item,checked=true)=>{const input=copy.checkbox(item).children[0];input.checked=checked;input.onchange();return input;};
copy.setItems([b,gap,a],'VOD1/버전1');
assert.equal(el('context-copy').disabled,true);
check(b);check(a);
assert.equal(text.value,'00:01:40 질문 답변\n01:01:01 다음 <이야기>');
assert.match(el('context-copy-count').textContent,/2개/);
assert.equal(copy.checkbox(a).children[0].checked,true);
assert.equal(copy.checkbox(a).children[0].attributes['aria-label'],`댓글에 포함: ${a.summary.title}`);
copy.setItems([gap,a,b],'VOD1/버전1');assert.equal(copy.checkbox(a).children[0].checked,true);
check(a,false);assert.equal(text.value,'01:01:01 다음 <이야기>');
copy.setItems([gap,a],'VOD1/버전1');assert.equal(text.value,'');assert.equal(el('context-copy-select').disabled,true);
check(a);copy.setItems([{...a,summary:{title:'변경된 제목'}}],'VOD1/버전1');assert.equal(text.value,'');
copy.setItems([a],'VOD1/버전1');check(a);copy.setItems([a],'VOD1/버전2');assert.equal(text.value,'');
check(a);copy.setItems([a],'VOD2/버전2');assert.equal(text.value,'');
check(a);el('context-copy-select').onclick();assert.equal(text.selectionEnd,text.value.length);assert.equal(text.focused,true);
let copied='';Object.defineProperty(globalThis,'navigator',{value:{clipboard:{async writeText(value){copied=value;}}},configurable:true});
await el('context-copy').onclick();assert.equal(copied,text.value);assert.match(notice.textContent,/복사했습니다/);
navigator.clipboard.writeText=async()=>{throw Error('권한 차단');};
await el('context-copy').onclick();assert.match(notice.textContent,/⌘C/);assert.equal(text.selectionEnd,text.value.length);
navigator.clipboard=undefined;await el('context-copy').onclick();assert.match(notice.textContent,/자동 복사/);
let reject;navigator.clipboard={writeText:()=>new Promise((_,fail)=>reject=fail)};
const pending=el('context-copy').onclick();copy.setItems([b],'VOD3/버전1');check(b);reject(Error('늦은 실패'));await pending;
assert.equal(notice.textContent,'');assert.equal(text.value,'01:01:01 다음 <이야기>');
assert.equal(JSON.stringify([a,b,gap]),before);
copy.setItems([],'');assert.equal(text.value,'');assert.equal(el('context-copy').disabled,true);
assert.match(el('context-copy-count').textContent,/0개/);
const parent={...a,id:'topic-0',kind:'topic'},child={...a,id:'story-0',kind:'story'};
copy.setItems([child,parent],'계층');check(parent);
assert.equal(copy.checkbox(child).children[0].checked,false);
check(child);assert.equal(text.value.split('\n').length,2);assert.match(el('context-copy-count').textContent,/같은 시작 시각/);
copy.setItems([{...child,summary:{title:'수정 제목'}},parent],'계층');assert.equal(copy.checkbox(child).children[0].checked,true);
assert.equal(text.value,'00:01:40 질문 답변\n00:01:40 수정 제목');
copy.setItems([child],'진행 중');check(child);
copy.setItems([child,{...b,id:'story-1'},parent],'진행 중');
assert.equal(copy.checkbox(child).children[0].checked,true);
assert.equal(text.value,'00:01:40 질문 답변');
const failed={...child,id:'failure',relation_status:'failed'};
copy.setItems([failed],'실패');check(failed);assert.equal(text.value,'');
const flatFailed={...child,id:'flat-failure',failed:true};
copy.setItems([flatFailed],'요약 실패');check(flatFailed);assert.equal(text.value,'');
console.log('문맥 선택·시간순 서식·해제·갱신/버전 격리·복사/수동 대안·원본 불변 검사 통과');

for (const flag of ['provisional','time_review']) {
  const item={...child,id:flag,[flag]:true};copy.setItems([item],'미확정');check(item);assert.equal(text.value,'');
}
const completed={...child,id:'완료',chat_state:'pending'};copy.setItems([completed],'채팅 대기');check(completed);assert.notEqual(text.value,'');
for(const grounding_state of ['pending','review']){
  const item={...child,id:grounding_state,grounding_state};copy.setItems([item],'대조 대기');check(item);assert.equal(text.value,'');
}
copy.setItems([completed],'채팅 대기');check(completed);
copy.setItems([{...completed,chat_state:'complete'}],'채팅 대기');assert.equal(copy.checkbox(completed).children[0].checked,true);
copy.setItems([a],'로컬 시작 시각',3532419);check(a);
assert.equal(text.value,'01:00:32 질문 답변');

const draftIdentity={root:'/검증',vod_id:'1',run:'a'.repeat(32)},savedDrafts=new Map();
let beforeUnload;
globalThis.addEventListener=(name,handler)=>{if(name==='beforeunload')beforeUnload=handler;};
const api=async(action,data)=>{
  const saved=savedDrafts.get(data.run)||{revision:0,text:'',selected:[],edited:false,basis:''};
  if(action==='context-comment')return structuredClone(saved);
  assert.equal(data.draft.revision,saved.revision);
  const next={...data.draft,revision:saved.revision+1};savedDrafts.set(data.run,structuredClone(next));return next;
};
let draft=createContextCopy({api});
await draft.setItems([a,b],'영구 초안',0,draftIdentity);
let tick=draft.checkbox(a).children[0];tick.checked=true;tick.onchange();
text.value='00:02:00 직접 편집한 <댓글>\n자유 문장';text.oninput();
let prevented=false;beforeUnload({preventDefault(){prevented=true;}});assert.equal(prevented,true);
await new Promise(resolve=>setTimeout(resolve,5));
prevented=false;beforeUnload({preventDefault(){prevented=true;}});assert.equal(prevented,false);
await draft.setItems([a,b],'영구 초안',0,draftIdentity);
assert.equal(text.value,'00:02:00 직접 편집한 <댓글>\n자유 문장');
tick=draft.checkbox(b).children[0];tick.checked=true;tick.onchange();
const appended='00:02:00 직접 편집한 <댓글>\n자유 문장\n01:01:01 다음 <이야기>';
assert.equal(text.value,appended);
assert.match(el('context-copy-count').textContent,/새 선택은 맨 아래 추가/);
tick.onchange();assert.equal(text.value,appended); // 이미 체크된 항목의 중복 이벤트
tick.checked=false;tick.onchange();assert.equal(text.value,appended); // 편집된 줄은 자동 삭제하지 않음
tick.checked=true;tick.onchange();assert.equal(text.value,appended); // 해제 후 재선택도 같은 줄은 중복하지 않음
text.onblur();await new Promise(resolve=>setTimeout(resolve,5));
draft=createContextCopy({api});await draft.setItems([a,b],'영구 초안',0,draftIdentity);
assert.equal(text.value,appended);assert.equal(draft.checkbox(b).children[0].checked,true);
await draft.setItems([a],'영구 초안',0,draftIdentity);text.onblur();await new Promise(resolve=>setTimeout(resolve,5));
assert.equal(savedDrafts.get(draftIdentity.run).selected.length,1);
assert.equal(text.value,appended);
await draft.setItems([a,b],'영구 초안',0,draftIdentity);tick=draft.checkbox(b).children[0];tick.checked=true;tick.onchange();
globalThis.confirm=()=>false;el('context-copy-reset').onclick();assert.match(text.value,/직접 편집/);
globalThis.confirm=()=>true;el('context-copy-reset').onclick();assert.equal(text.value,'00:01:40 질문 답변\n01:01:01 다음 <이야기>');
text.onblur();await new Promise(resolve=>setTimeout(resolve,5));
await draft.setItems([a,b],'다른 버전',0,{...draftIdentity,run:'b'.repeat(32)});assert.equal(text.value,'');
assert.equal(JSON.stringify([a,b,gap]),before);
console.log('댓글 편집·체크 변경·폴링·초안 재생성 확인·서버 저장·새 페이지 복원·버전 격리 통과');

// 화면에 안 보이게 된 선택도 원래 자료에서 삭제한 것으로 취급하지 않는다.
const low={...a,id:'낮은 반응',reaction_index:1},high={...b,id:'높은 반응',reaction_index:10};
const filteredCopy=createContextCopy();await filteredCopy.setItems([low,high],'필터 선택 보존');
const lowCheck=filteredCopy.checkbox(low).children[0];lowCheck.checked=true;lowCheck.onchange();
text.value='직접 편집한 댓글';text.oninput();
assert.deepEqual(contextReactionRows([low,high],10).map(r=>r.item.id),['높은 반응']);
// 실제 갱신도 전체 결과를 전달하고, 필터는 렌더링에만 사용한다.
await filteredCopy.setItems([low,high],'필터 선택 보존');
assert.equal(text.value,'직접 편집한 댓글');
assert.equal(filteredCopy.checkbox(low).children[0].checked,true);
assert.match(el('context-copy-count').textContent,/1개/);
console.log('반응 필터 밖 댓글 선택·직접 편집 보존 확인 통과');

// 편집 뒤에는 시각순 재정렬 없이 아래에 덧붙이고 사용자 공백도 보존한다.
const appendCopy=createContextCopy();
for(const [prefix,expected] of [['자유 문장','자유 문장\n'],['자유 문장\n','자유 문장\n'],['자유 문장\r\n','자유 문장\r\n'],['','']]){
  await appendCopy.setItems([a,b],'추가 위치 '+JSON.stringify(prefix),3532419);
  text.value=prefix;text.oninput();
  const add=row=>{const input=appendCopy.checkbox(row).children[0];input.checked=true;input.onchange();};
  add(b);add(a);
  assert.equal(text.value,expected+'01:59:54 다음 <이야기>\n01:00:32 질문 답변');
}
const staleCheckbox=appendCopy.checkbox(b).children[0];
await appendCopy.setItems([b],'다른 탭');text.value='다른 탭 초안';text.oninput();
staleCheckbox.checked=true;staleCheckbox.onchange();assert.equal(text.value,'다른 탭 초안');
const invalid={...b,id:'처리 중',provisional:true},invalidCheck=appendCopy.checkbox(invalid).children[0];
invalidCheck.checked=true;invalidCheck.onchange();assert.equal(text.value,'다른 탭 초안');
console.log('편집 후 아래줄 추가·재선택 중복 방지·줄바꿈 보존·원본 시각 보정·다른 탭 격리 통과');
