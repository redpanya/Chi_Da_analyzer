import assert from 'node:assert/strict';
import {createExternal} from '../web/context-external.js';
class Element{
  value='';textContent='';disabled=false;hidden=false;children=[];checked=false;files=[];
  replaceChildren(...items){this.children=items;} append(...items){this.children.push(...items);}
}
const nodes=new Map();
globalThis.document={createElement:()=>new Element(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);}};
const $=id=>document.getElementById(id),calls=[];let next,opened=null;
const api=async(action,args)=>{calls.push({action,args});if(action.endsWith('-list'))return [];if(action.endsWith('-prompt'))return {prompt:'요청문'};if(next instanceof Error)throw next;return next;};
const view=createExternal({api,onResult:async run=>{opened=run;}});
const project={path:'/vod-1',root:'/test',vod_id:'1',metadata:{title:'가상 VOD'},context:{inputs:{transcripts:[{id:'a',label:'검증 전사',complete:true}]}}};
view.setProject(project);
const value={accepted:1,errors:[{file:'bad.json',chunk:'002',message:'근거 오류'}],missing:['002'],received:1,total:2,topics:[{start_ms:1000,title:'정상 주제'}],token:'valid',complete:false};
$('external-json').value='{}';$('external-json').oninput();next=value;
await $('external-preview').onclick();assert.equal($('external-import').disabled,true);assert.equal($('external-partial-label').hidden,false);
assert.match($('external-import-status').textContent,/부분 저장/);
assert.ok($('external-preview-result').children.some(e=>e.textContent.includes('bad.json · 묶음 002')));
$('external-partial').checked=true;$('external-partial').onchange();assert.equal($('external-import').disabled,false);
$('external-json').value='{"changed":true}';$('external-json').oninput();assert.equal($('external-import').disabled,true);assert.equal($('external-partial').checked,false);
next=Error('취소됨 · 작업 재개 필요');await $('external-preview').onclick();assert.match($('external-import-status').textContent,/취소됨/);assert.equal($('external-import').disabled,true);
const bytes=new Uint8Array([80,75,3,4]);$('external-file').files=[{name:'결과.zip',size:bytes.length,arrayBuffer:async()=>bytes.buffer}];
await $('external-file').onchange();assert.equal($('external-json').value,'');assert.match($('external-file-info').textContent,/ZIP/);assert.equal($('external-preview').disabled,false);
next={...value,errors:[]};await $('external-preview').onclick();assert.equal(calls.at(-1).args.archive,btoa('PK\x03\x04'));assert.equal($('external-import').disabled,false);
next={run:'saved',mode:'detail'};await $('external-import').onclick();assert.equal(opened,'saved');
assert.equal(calls.find(c=>c.action.endsWith('-import-files')).args.archive,btoa('PK\x03\x04'));
assert.equal($('external-import').disabled,true);
$('external-file').files=[{name:'too-big.zip',size:11*1024**2}];await $('external-file').onchange();
assert.equal($('external-import').disabled,true);assert.equal($('external-preview').disabled,true);assert.match($('external-import-status').textContent,/10MiB/);
view.setProject({...project,path:'/vod-2'});assert.equal($('external-json').value,'');assert.equal($('external-file-info').textContent,'');
next={...value,accepted:0,errors:[{file:'bad.json',chunk:'',message:'잘못된 JSON'}]};$('external-json').value='{';$('external-json').oninput();await $('external-preview').onclick();
assert.equal($('external-import').disabled,true);assert.equal($('external-partial-label').hidden,true);
console.log('외부 파일 UI: ZIP 선택·오류 표시·부분 저장 동의·편집/파일 교체/프로젝트 전환 무효화 검사 통과');
