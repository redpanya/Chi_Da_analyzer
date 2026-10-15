import assert from 'node:assert/strict';
import {createVoiceSuggestions} from '../web/voice-suggestions.js';
const nodes=new Map();
function node(){return {value:'',children:[],dataset:{},textContent:'',disabled:false,
  append(...v){this.children.push(...v);},replaceChildren(...v){this.children=v;},focus(){},
  querySelectorAll(){return this.children.flatMap(c=>c.children||[]).flatMap(c=>c.children||[]).filter(c=>c.dataset?.apply);}};}
globalThis.document={getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},createElement:node};
const $=id=>document.getElementById(id),calls=[],heard=[],separated=[];
const view=createVoiceSuggestions({listen:s=>heard.push(s),jump:t=>calls.push(t),start:(...v)=>calls.push(v),edit:(...v)=>calls.push(v),separate:r=>separated.push(r)});
const row={id:'x',start_ms:3000,end_ms:5000,text:'다음 판의 맵',candidate:'a',reason:'검토 필요',evidence:['x'],
  acoustic:{note:'확률 아님',candidates:[{speaker:'a',similarity:.65,samples:[{start_ms:6000,end_ms:8000,status:'confirmed'}]}]}};
const value={run:'voice',revision:1,suggestion:{id:'proposal',complete:true,stale:false,items:[row],
  input:{rows:[row],names:{a:'A화자'},context:[{...row,speaker_name:'불명'}]}}};
view.reset();view.render(value,{suggestions:[{id:'proposal',start_ms:3000,end_ms:5000}],suggestion:'proposal'});view.setDisabled(false);view.choose(row);
$('suggest-run').onclick();assert.deepEqual(calls.at(-1),['suggest',{start_ms:3000,end_ms:5000,run:'voice',revision:1,segment_id:'x'}]);
$('suggest-original').onclick();assert.deepEqual(calls.at(-1),['retranscribe-original',{start_ms:3000,end_ms:5000}]);
assert.equal($('suggest-separate').onclick,undefined);
$('suggest-start').oninput();$('suggest-run').onclick();assert.equal(calls.at(-1)[1].segment_id,undefined);
const actions=$('suggest-results').children[0].children[4];actions.children[0].onclick();assert.equal(heard.at(-1).sample.id,'x');
actions.children[3].onclick();assert.deepEqual(calls.at(-1),['accept-suggestion',{suggestion:'proposal',segment_id:'x',speaker:'a'}]);
const before=calls.length;view.setDisabled(true);actions.children[3].onclick();$('suggest-run').onclick();assert.equal(calls.length,before);
view.setDisabled(false);view.render({...value,suggestion:{...value.suggestion,stale:true}},{});
const stale=$('suggest-results').children[0].children[4].children[3];assert.equal(stale.disabled,true);stale.onclick();assert.equal(calls.length,before);
console.log('후보 UI: 범위·단일 발언·원음 재전사·분리 제거·듣기·명시 배정·잠금·오래된 후보 보호 통과');
