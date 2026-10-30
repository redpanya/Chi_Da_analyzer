import assert from 'node:assert/strict';
import {clipEvidence,skippedChatEvidence} from '../web/context-clip-evidence.js';
class Element{
  children=[];dataset={};listeners={};
  append(...items){this.children.push(...items);}
  addEventListener(event,callback){this.listeners[event]=callback;}
}
globalThis.document={createElement:()=>new Element()};
const card=new Element(),seeks=[];
const candidate={start_ms:1000,end_ms:3000,discovery_info:{source:'chat',relation:'uncertain',signals:[
  {reaction_ms:4000,messages:20,unique_texts:3,burst_ratio:4,repeats:[{term:'<script>내용</script>',messages:12}]}]},
  chat_reactions:[{time_ms:4000,text:'<img onerror=alert(1)>'},{time_ms:4000,text:'같은 시각'},{time_ms:2000,text:'반응'}]};
clipEvidence(card,candidate,at=>seeks.push(at));
assert.equal(card.children[0].textContent,'발견 근거 · 채팅');assert.match(card.children[1].textContent,/관련성 확인 필요/);
const actions=card.children.find(e=>e.className==='play-actions clip-chat-reactions');
assert.equal(actions.children.length,2);assert.match(actions.children[1].textContent,/인접 반응/);
assert.match(actions.children[1].title,/<img onerror=alert\(1\)>/);assert.match(actions.children[1].title,/같은 시각/);actions.children[1].onclick();assert.deepEqual(seeks,[4000]);
const legacy=new Element();clipEvidence(legacy,{},()=>{});assert.match(legacy.children[0].textContent,/기록 없음/);
const skipped=new Element();skippedChatEvidence(skipped,{chat_discovery:{unanchored:[{reaction_ms:70000,messages:12}]}});
const details=skipped.children[0];assert.equal(details.children.length,1);details.open=true;details.listeners.toggle();
assert.equal(details.children.length,2);details.listeners.toggle();assert.equal(details.children.length,2);
console.log('클립 발견 UI: 근거·관련성 표시, 지연 반응 이동, 동일 시각 중복 제거, 안전한 원문 표시, 구버전·보류 목록 통과');
