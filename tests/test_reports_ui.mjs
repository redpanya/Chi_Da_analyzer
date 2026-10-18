import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createReports} from '../web/reports.js';
const downloads=[];
class Element{value='';disabled=false;children=[];textContent='';hidden=false;append(...v){this.children.push(...v);if(!this.value&&v[0]?.value)this.value=v[0].value;}replaceChildren(){this.children=[];this.value='';}click(){downloads.push(this);}}
const elements=new Map();globalThis.document={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement(){return new Element();}};
const el=id=>document.getElementById(id),calls=[];
const hardware={os:'테스트 OS',cpu:'실행 당시 CPU',os_version:'1',architecture:'arm64'};
const payload={schema:2,vod_id:'15655103',report_id:'a',hardware,stages:[],counts:{chat_messages:10}};
let resolvePreview=null,delayPreview=false;
const api=async(action,data)=>{
 calls.push({action,data});
 if(action==='report-config')return {hardware:{...hardware,cpu:'현재 CPU'}};
 if(action==='reports')return [{id:'a',created_at:'2026-10-18'}];
 if(action==='report-read')return {payload:structuredClone(payload),events:[],details:[{stage:'download',message:'첨부하면 안 되는 상세 로그'}]};
 if(action==='report-preview'){
  if(delayPreview)return new Promise(resolve=>{resolvePreview=resolve;});
  return {payload:structuredClone(payload)};
 }
 throw Error(action);
};
const controller=createReports({api,getProject:()=>({root:'/test',vod_id:'15655103'})});
await controller.refresh();
assert.equal(el('report-save').disabled,true);
assert.match(el('report-hardware').textContent,/현재 CPU/);
assert.match(el('report-run-hardware').textContent,/실행 당시 CPU/);
assert.match(el('report-vod').textContent,/15655103/);
await el('report-preview').onclick();
assert.equal(el('report-save').disabled,false);
assert.equal(JSON.parse(el('report-payload').value).vod_id,'15655103');
assert.doesNotMatch(el('report-payload').value,/상세 로그/);
let savedBlob;URL.createObjectURL=blob=>{savedBlob=blob;return 'blob:test';};URL.revokeObjectURL=()=>{};
payload.counts.chat_messages=999;
el('report-save').onclick();
assert.equal(downloads[0].download,'chida-report-vod-15655103-a.json');
assert.equal(JSON.parse(await savedBlob.text()).counts.chat_messages,10);
assert.match(el('report-notice').textContent,/전송되지 않았습니다/);
await controller.refresh();assert.equal(el('report-save').disabled,true);
delayPreview=true;const pending=el('report-preview').onclick();controller.clear();resolvePreview({payload});await pending;
assert.equal(el('report-save').disabled,true);assert.equal(el('report-payload').value,'');
assert.equal(calls.filter(c=>c.action==='report-submit').length,0);
const html=readFileSync(new URL('../web/index.html',import.meta.url),'utf8');
assert.match(html,/mailto:redpanyaday@gmail.com/);assert.match(html,/작업한 VOD 번호/);
assert.doesNotMatch(html,/id="report-(send|consent|server)"/);
console.log('리포트 UI: 이메일 안내·VOD 번호·실행 당시 사양·고정 사본 저장·전환 시 초기화·자동 제출 없음 통과');
