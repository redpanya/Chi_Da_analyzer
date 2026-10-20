import assert from 'node:assert/strict';
import {fallbackEvidence,fallbackChats} from '../web/context-fallback.js';
import {createBackground} from '../web/context-background.js';
import {canCopyContext} from '../web/context-copy.js';
const item={failed:true,input:{evidence:[
  ...Array.from({length:8},(_,i)=>({id:'S'+i,kind:'speech',start_ms:i*1000,text:'발언 '+i})),
  {id:'C1',kind:'chat',text:'채팅 1',count:2},{id:'C2',kind:'chat',text:'채팅 2',count:8}
]}};
const before=JSON.stringify(item);
assert.deepEqual(fallbackEvidence(item).map(r=>r.id),['S0','S4','S7']);
assert.equal(fallbackChats(item)[0].id,'C2');
assert.equal(canCopyContext(item),false);assert.equal(JSON.stringify(item),before);
const fields=new Map();
globalThis.document={getElementById(id){if(!fields.has(id))fields.set(id,{value:'',textContent:'',disabled:false});return fields.get(id);}};
const $=id=>document.getElementById(id);let finish,pending=false;
const view=createBackground({message(){},api:async(action)=>{
  if(action==='context-background')return {text:'저장 설명'};
  if(pending)await new Promise(resolve=>finish=resolve);
  return {text:'저장 설명'};
}});
await view.setProject({path:'a',root:'root',vod_id:'1'});
assert.equal($('context-background').value,'저장 설명');assert.equal(view.ready(),true);
$('context-background').value='입력 중';await view.setProject({path:'a',root:'root',vod_id:'1'});
assert.equal($('context-background').value,'입력 중');
pending=true;const save=view.save();assert.equal($('context-background-save').disabled,true);assert.equal(view.ready(),false);
await view.setProject({path:'b',root:'root',vod_id:'2'});finish();
assert.equal(await save,false);assert.equal($('context-background').value,'저장 설명');
console.log('실패 참고 발언·채팅 분리/원본 보존/복사 제외 · 방송 설명 저장 중 VOD 전환 보호 통과');
