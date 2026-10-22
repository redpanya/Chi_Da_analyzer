import assert from 'node:assert/strict';
import {createContextInputs} from '../web/context-inputs.js';
const nodes=new Map();
const node=()=>({value:'',disabled:false,children:[],replaceChildren(...items){this.children=items;}});
globalThis.document={getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},createElement:node};
const $=id=>document.getElementById(id);
let changes=0;
const view=createContextInputs(()=>changes++);
const a={id:'a',label:'한국어 · 원음 · 표준',complete:true}, b={id:'b',label:'한국어 · 원음 · 민감',complete:true};
const project={path:'/vod-1',locked:false,context:{inputs:{transcripts:[a,b,{id:'unfinished',label:'일부',complete:false}],
  speakers:[{id:'va',label:'sherpa · 2명',transcript_run:'a'},{id:'vb',label:'FluidAudio · 3명',transcript_run:'b'}],
  transcript_run:'a',speaker_run:'va'}}};
view.setProject(project);
assert.deepEqual(view.selection(),{transcript_run:'a',speaker_run:'va'});
assert.deepEqual($('context-speaker').children.map(r=>r.value),['','va']);
assert.equal($('context-transcript').children.at(-1).disabled,true);
$('context-transcript').value='b';$('context-transcript').onchange();
assert.deepEqual(view.selection(),{transcript_run:'b',speaker_run:null});
$('context-speaker').value='vb';$('context-speaker').onchange();
view.setProject(project);
assert.deepEqual(view.selection(),{transcript_run:'b',speaker_run:'vb'});
view.setProject({...project,locked:true});assert.equal($('context-transcript').disabled,true);
view.setProject({...project,context:{inputs:{...project.context.inputs,transcripts:[a]}}});
assert.equal(view.ready(),false);assert.equal(view.selection().transcript_run,'');
view.setProject({...project,path:'/vod-2'});
assert.deepEqual(view.selection(),{transcript_run:'a',speaker_run:'va'});
assert.equal(changes,2);
console.log('문맥 입력 선택: 연결된 화자만 표시·설명·폴링 보존·삭제 후 재선택·VOD 전환·잠금 통과');
