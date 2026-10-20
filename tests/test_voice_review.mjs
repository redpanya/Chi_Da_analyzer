import assert from 'node:assert/strict';
import {createVoiceReview} from '../web/voice-review.js';

const nodes=new Map();
function node(tag='div'){return {tag,value:'',textContent:'',children:[],disabled:false,hidden:false,attributes:{},
  append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},setAttribute(key,value){this.attributes[key]=value;}};}
globalThis.document={getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},createElement:node,createTextNode:text=>({textContent:text})};
const $=id=>document.getElementById(id),calls=[],heard=[],jumps=[];let searches=0;
const view=createVoiceReview({listen:(...v)=>heard.push(v),save:(...v)=>calls.push(v),search:()=>searches++,jump:v=>jumps.push(v)});
const row={id:'failed-1',start_ms:12000,end_ms:14500,reason:'short',text:'확인할 전사'};
const result={run:'run-a',revision:3,failed:2,reasons:{short:'음성 근거 부족'},speakers:[{id:'speaker-a',default:'A화자',name:'김모모'}],
  failed_review:{items:[row],total:2,cursor:0,next_cursor:100,group:'speaker-a',query:'확인',samples:[row],groups:[{id:'speaker-a',name:'김모모',count:2}]}};
view.reset();view.render(result);view.setDisabled(false,true);
const controls=()=>$('voice-failed-rows').children[0].children.at(-2);
const editor=()=>$('voice-failed-rows').children[0].children.at(-1);
const target=()=>editor().children[1].children[1],save=()=>editor().children[2];
assert.equal(save().disabled,true);
controls().children[0].onclick();assert.deepEqual(heard.at(-1)[0].sample,row);
controls().children[1].onclick();assert.equal(jumps.at(-1),12000);
target().value='speaker-a';target().onchange();save().onclick();
assert.deepEqual(calls.at(-1),[{segment_id:'failed-1'},'speaker-a',{run:'run-a',revision:3}]);
view.render(result);assert.equal(target().value,'speaker-a');
target().value='__new__';target().onchange();save().onclick();assert.equal(calls.at(-1)[1],'__new__');
const groupTarget=$('voice-failed-group-target');groupTarget.value='speaker-a';groupTarget.onchange();
$('voice-failed-group-assign').onclick();assert.deepEqual(calls.at(-1),[{candidate_speaker:'speaker-a',query:'확인'},'speaker-a',{run:'run-a',revision:3}]);
view.render(result);assert.equal(groupTarget.value,'speaker-a');
const before=calls.length;view.setDisabled(true,false);save().onclick();$('voice-failed-group-assign').onclick();
assert.equal(calls.length,before);assert.equal(target().disabled,true);assert.equal(controls().children[0].disabled,true);assert.equal($('voice-failed-group-samples').children[0].disabled,true);
$('voice-failed-query').value='실패 이유';$('voice-failed-search').onsubmit({preventDefault(){}});
assert.equal(view.request().failed_query,'실패 이유');assert.equal(view.request().failed_cursor,0);
$('voice-failed-next').onclick();assert.equal(view.request().failed_cursor,100);
$('voice-failed-prev').onclick();assert.equal(view.request().failed_cursor,0);assert.equal(searches,3);
view.render({...result,run:'다른 분석'});assert.equal(target().value,'');assert.equal(groupTarget.value,'');
view.render({...result,failed:0,failed_review:{items:[],total:0,cursor:0,next_cursor:null,groups:[]}});
assert.match($('voice-failed-empty').textContent,/검토할.*없습니다/);assert.equal($('voice-failed-group-review').hidden,true);
view.reset();assert.equal(view.request().failed_query,'');assert.equal(view.request().failed_group,'');assert.equal($('voice-failed-rows').children.length,0);
console.log('실패 검토 UI: 음성 범위·발언 ID·묶음/검색 스냅샷·일괄 저장·잠금·새 화자·독립 페이지·버전 초기화 통과');
