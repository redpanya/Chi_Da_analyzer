import assert from 'node:assert/strict';
import {createVoices} from '../web/voices.js';

const nodes=new Map();
globalThis.cancelAnimationFrame=()=>{};
function node(){return {value:'',dataset:{},children:[],disabled:false,textContent:'',
  append(...v){this.children.push(...v);},replaceChildren(...v){this.children=v;},
  pause(){},load(){},addEventListener(){},removeAttribute(){},setAttribute(){},getAttribute(){return '';}};}
globalThis.document={getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},createElement:node,querySelectorAll:()=>[]};
const $=id=>document.getElementById(id),calls=[];
const base={engine:true,ready:true,supported:true,free_bytes:1e9,manual_speakers:true};
const result={run:null,revision:0,speakers:[],items:[],total:0,next_cursor:null,model:base,
  diarization_models:{sherpa:{...base,resume:true},fluid:{...base,resume:false},pyannote:{...base,resume:false,ready:false}},stem:null};
let project={root:'/검증',path:'/검증/vod-1',vod_id:'1',model_root:'/모델',metadata:{title:'검증'},locked:false,
  voices:{runs:[],stems:[],state:'idle'},speech:{transcript:{complete:true}}};
const view=createVoices({api:async(action,data)=>{if(action==='voices-result')return result;calls.push({action,data});return project;},
  player:{},showVideo(){},showExplore(){},onProject(value){project=value;view.setProject(value);}});
const settle=async()=>{await Promise.resolve();await Promise.resolve();};
view.setProject(project);await settle();
assert.equal($('voices-run').disabled,false);
assert.match($('voices-model').textContent,/바로 사용 가능/);
$('voices-backend').value='pyannote';$('voices-backend').onchange();
assert.equal($('voices-run').disabled,true);assert.equal($('voices-prepare').disabled,false);
assert.match($('voices-model').textContent,/최초 다운로드 시 HF 로그인/);
assert.equal($('voices-model').dataset.ready,'false');
await $('voices-prepare').onclick();assert.equal(calls.at(-1).data.options.backend,'pyannote');
$('voices-backend').value='fluid';$('voices-number').value='4';$('voices-backend').onchange();
assert.equal($('voices-number').disabled,false);assert.match($('voices-resume-hint').textContent,/처음부터/);
await $('voices-run').onclick();assert.deepEqual(calls.at(-1).data.options,{backend:'fluid',speakers:4});
project={...project,voices:{...project.voices,updated_at:'폴링'}};view.setProject(project);await settle();
assert.equal($('voices-backend').value,'fluid');
project={...project,locked:true};view.setProject(project);
assert.equal($('voices-backend').disabled,true);assert.equal($('voices-run').disabled,true);
project={...project,path:'/검증/vod-2',locked:false,voices:{runs:[],stems:[],backend:'fluid'}};view.setProject(project);await settle();
assert.equal($('voices-backend').value,'fluid');assert.equal($('voices-number').disabled,false);
project={...project,path:'/검증/이전-nemo',voices:{runs:[],stems:[],backend:'nemo'}};view.setProject(project);await settle();
assert.equal($('voices-backend').value,'sherpa');
console.log('화자 엔진 UI: 준비 안내·잠금·선택 유지·제거된 엔진 선택 복구 통과');
