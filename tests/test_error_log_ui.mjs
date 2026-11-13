import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createErrorLogUI} from '../web/error-log-ui.js';

class Element{
  value='';disabled=false;children=[];textContent='';hidden=false;checked=false;listeners={};attributes={};
  append(...values){this.children.push(...values);}
  replaceChildren(...values){this.children=values;}
  before(){}
  setAttribute(key,value){this.attributes[key]=value;}
  addEventListener(type,fn){this.listeners[type]=fn;}
}
const event=(id,vod_id,operation='speech')=>({event_id:id,vod_id,operation,summary:'테스트 오류',message:'테스트 내용',at:new Date().toISOString(),count:1,code:null});
const sample=[event('a','123'),event('b',123,'context'),event('c','1234'),event('d','456'),event('e',null)];
function setup(){
  const elements=new Map(),el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  globalThis.document={getElementById:el,createElement:()=>new Element()};
  let project={root:'/library',path:'/library/vod-123',vod_id:'123'},hold=null;
  const requests=[],pending=[];
  const response=(action,data)=>action==='error-log-export'?{events:sample.filter(r=>data.ids.includes(r.event_id))}:{events:sample,enabled:true,limit:1000};
  const api=async(action,data)=>{requests.push({action,data});if(hold===action)return new Promise(resolve=>pending.push(()=>resolve(response(action,data))));return response(action,data);};
  const ui=createErrorLogUI({api,getProject:()=>project});
  const setProject=p=>{project=p;ui.setProject();};
  const rows=()=>el('error-log-rows').children;
  return {ui,el,rows,requests,pending,setProject,hold:action=>{hold=action;}};
}

test('선택한 VOD 번호의 정확한 일치만 표시하고 JSON도 동일 범위로 만든다',async()=>{
  const t=setup();await t.ui.refresh();
  assert.equal(t.rows().length,2);assert.match(t.el('error-log-state').textContent,/VOD 123 오류 기록 2건/);
  await t.el('error-export-check').onclick();
  assert.deepEqual(t.requests.at(-1).data.ids,['a','b']);
  assert.deepEqual(JSON.parse(t.el('error-export-preview').value).events.map(r=>r.event_id),['a','b']);
  const checkbox=t.rows()[0].children[0].children[0];checkbox.checked=true;checkbox.onchange();
  assert.equal(t.el('error-export-save').disabled,true);
  await t.el('error-export-check').onclick();assert.deepEqual(t.requests.at(-1).data.ids,['b']);
  t.el('error-filter-operation').value='speech';t.el('error-filter-operation').listeners.input();
  assert.equal(t.rows().length,1);await t.el('error-export-check').onclick();assert.deepEqual(t.requests.at(-1).data.ids,['a']);
});

test('VOD 변경 즉시 선택과 첨부 사본을 지우고 늦은 조회와 JSON 결과를 무시한다',async()=>{
  const t=setup();await t.ui.refresh();await t.el('error-export-check').onclick();t.el('error-email-consent').checked=true;
  t.hold('error-log-list');const old=t.ui.refresh();
  t.setProject({root:'/other',vod_id:'456'});
  assert.equal(t.rows().length,0);assert.equal(t.el('error-export-preview').value,'');assert.equal(t.el('error-email-consent').checked,false);assert.equal(t.el('error-email').hidden,true);
  t.pending.shift()();await old;assert.equal(t.rows().length,0);
  t.hold(null);await t.ui.refresh();assert.equal(t.rows().length,1);assert.match(t.el('error-log-state').textContent,/VOD 456/);
  t.hold('error-log-export');const exporting=t.el('error-export-check').onclick();
  t.setProject({root:'/different-library',vod_id:'456'});t.pending.shift()();await exporting;
  assert.equal(t.el('error-export-preview').value,'');assert.equal(t.el('error-export-save').disabled,true);
});

test('VOD 미선택과 기록이 없는 VOD는 빈 목록이고 저장 설정은 유지한다',async()=>{
  const t=setup();await t.ui.refresh();t.setProject(null);await t.ui.refresh();
  assert.equal(t.requests.at(-1).action,'error-log-config');assert.equal(t.rows().length,0);assert.equal(t.el('error-log-enabled').checked,true);
  assert.match(t.el('error-log-state').textContent,/VOD를 선택/);assert.equal(t.el('error-export-check').disabled,true);
  t.setProject({root:'/library',vod_id:'789'});await t.ui.refresh();assert.match(t.el('error-log-state').textContent,/789 오류 기록 0건/);
  const count=t.requests.length;await t.el('error-export-check').onclick();assert.equal(t.requests.length,count);
});

test('조회 중 필터를 바꿔도 목록을 표시하고 첨부 생성 중 선택을 바꾸면 사본을 폐기한다',async()=>{
  const t=setup();t.hold('error-log-list');const reading=t.ui.refresh();
  t.el('error-filter-operation').value='speech';t.el('error-filter-operation').listeners.input();
  t.pending.shift()();await reading;assert.equal(t.rows().length,1);
  t.hold('error-log-export');const exporting=t.el('error-export-check').onclick();
  t.el('error-filter-operation').value='context';t.el('error-filter-operation').listeners.input();
  t.pending.shift()();await exporting;assert.equal(t.el('error-export-preview').value,'');assert.equal(t.el('error-export-save').disabled,true);
});
