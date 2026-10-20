import assert from 'node:assert/strict';
import {createSpeech} from '../web/speech.js';
import {getHelpContent} from '../web/help-content.js';

const nodes = new Map();
function node() {
  return {value:'', dataset:{}, children:[], textContent:'', disabled:false,
    append(...items){this.children.push(...items);}, replaceChildren(...items){this.children=items;},
    pause(){}, load(){}, addEventListener(){}, removeAttribute(){}, setAttribute(){}};
}
globalThis.document = {
  getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},
  createElement:node, querySelectorAll:()=>[],
};
const $ = id=>document.getElementById(id), calls=[];let rowsRequests=0;
let project={path:'/검증/vod-1',root:'/검증',vod_id:'1',metadata:{title:'검증'},locked:false,voices:{},
  tasks:{video:{state:'complete',assets:{playback:'media/original.mp4'}}},
  speech:{state:'idle',message:'',raw_audio:{track:1},options:{input_kind:'sam',sam_profile:'standard'},versions:[]}};
const details={tracks:[{index:1,channels:1}],duration_ms:10000,estimated_bytes:320000,
  model:{ready:true,engine:true,bytes:1,free_bytes:1},
  sam:{ready:false,engine:false,profiles:[
    {id:'standard',label:'표준',description:'기존 설정'},
    {id:'balanced',label:'균형',description:'계산 절반'},
    {id:'fast',label:'빠름',description:'발음 손상 주의'}],speed_note:'10초 실측, 로딩 제외'}};
let view;
view=createSpeech({player:{reset(){}},api:async(action,data)=>{
  if(action==='speech-info')return details;
  if(action==='speech-result'){rowsRequests++;return {items:[],total:0,next_cursor:null};}
  calls.push({action,data});return project;
},onProject:value=>view.setProject(value)});
const settle=async()=>{await Promise.resolve();await Promise.resolve();};
view.setProject(project);await settle();
assert.equal($('transcribe').disabled,false);
assert.equal($('speech-vad').value,'standard');
$('speech-vad').value='sensitive';$('speech-vad').onchange();
$('speech-prompt').value='사용자 용어';assert.match(getHelpContent('speech-options',id=>$(id).value).current,/sensitive/);
project={...project,speech:{...project.speech,updated_at:'폴링'}};view.setProject(project);
assert.equal($('speech-vad').value,'sensitive');assert.equal($('speech-prompt').value,'사용자 용어');
await $('transcribe').onclick();
assert.equal(calls.at(-1).data.input_kind,'original');
assert.deepEqual(calls.at(-1).data.asr_options,{vad:'sensitive',prompt:'사용자 용어'});
assert.equal(calls.at(-1).data.sam_profile,undefined);
$('speech-vad').value='off';$('speech-vad').onchange();assert.match(getHelpContent('speech-options',id=>$(id).value).current,/off/);
view.setProject({...project,locked:true});assert.equal($('speech-vad').disabled,true);assert.equal($('speech-prompt').disabled,true);
project={...project,path:'/검증/vod-2',speech:{...project.speech,options:{asr_options:{vad:'off',prompt:'다른 자료'}}}};
view.setProject(project);await settle();
assert.equal($('speech-vad').value,'off');assert.equal($('speech-prompt').value,'다른 자료');
assert.equal($('separate-speech').onclick,undefined);assert.equal($('prepare-sam').onclick,undefined);
const count=rowsRequests;view.setProject({...project,voices:{run:'새 화자 분석',revision:8,updated_at:'변경'}});await settle();
assert.equal(rowsRequests,count);
console.log('원음 전사·발화 검출·힌트·분리 제거·폴링 보존·잠금·VOD별 설정 복원 검사 통과');
