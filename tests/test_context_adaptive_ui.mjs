import assert from 'node:assert/strict';
import {interpretationDetails} from '../web/context-interpretations.js';
import {canCopyContext} from '../web/context-copy.js';

class Element{
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';}
  append(...nodes){this.children.push(...nodes);}
}
globalThis.document={createElement:tag=>new Element(tag)};
let sought;
const original='<img src=x onerror=alert(1)> 원문';
const item={input:{evidence:[{id:'S1',start_ms:1200,end_ms:2400,text:original}]},
  interpretations:[{status:'applied',original_text:original,proposed_text:'요약용 해석',reason:'앞뒤 발언',evidence:['S1']}],
  omissions:[{source_id:'S1',role:'aside',status:'referenced',reason:'요약 근거로 유지'}],
  held_claims:[{text:'확인 필요 주장',reason:'부정 의미 확인',evidence:['S1']}],review_issues:['자료 확인']};
const before=JSON.stringify(item),tree=interpretationDetails(item,{seek(...args){sought=args;}});
const nodes=[];function visit(node){nodes.push(node);node.children.forEach(visit);}visit(tree);
assert(nodes.some(x=>x.textContent==='원문: '+original));
assert(nodes.some(x=>x.textContent==='요약 근거로 유지'));
nodes.find(x=>x.tag==='button').onclick();assert.deepEqual(sought,[1200,true,2400]);
assert.equal(JSON.stringify(item),before);
assert.equal(canCopyContext({grounding_state:'complete',evidence_review:true,copy_ready:true}),true);
assert.equal(canCopyContext({grounding_state:'review',copy_ready:false}),false);
assert.equal(canCopyContext({grounding_state:'pending',copy_ready:false}),false);
assert.equal(canCopyContext({grounding_state:'complete',parallel:true}),true);
assert.equal(canCopyContext({grounding_state:'complete',time_review:true}),false);
item.interpretations[0].part_id='검토부분';item.interpretations[0].owner_id='원래문맥';
let rejected;
const editable=interpretationDetails(item,{seek(){}},async change=>{rejected=change;});
const rejectButton=editable.children.find(x=>x.tag==='button');
await rejectButton.onclick();assert.equal(rejected,item.interpretations[0]);assert.equal(rejectButton.disabled,false);
const unchanged=interpretationDetails({...item,interpretations:[{...item.interpretations[0],proposed_text:original}]},{seek(){}});
assert.match(unchanged.children[0].textContent,/문맥 보완 0개/);
console.log('문맥 보완·생략·보류 표시, 원문 문자 처리, 원음 이동, 부분 완료 선택 검사 통과');
