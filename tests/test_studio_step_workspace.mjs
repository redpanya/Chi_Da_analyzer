import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {studioSteps,nextStudioStep,previewFrameGeometry,createStudioWorkspace,bindStudioSelection,studioReturnLinks} from '../web/studio-workspace.js';
import {createStudioInspector} from '../web/studio-inspector.js';

test('편집 단계 키보드 순서와 세로 영상의 높이 기준 맞춤',()=>{
  assert.deepEqual(studioSteps,['range','preset','frame','caption','export']);
  assert.equal(nextStudioStep('range','ArrowUp'),'export');
  assert.equal(nextStudioStep('preset','ArrowDown'),'frame');
  assert.equal(nextStudioStep('caption','Home'),'range');
  assert.equal(nextStudioStep('range','End'),'export');
  const portrait=previewFrameGeometry(620,900,'9:16');
  assert.equal(portrait.height,670);assert.equal(portrait.width/portrait.height,9/16);
  const landscape=previewFrameGeometry(430,710,'16:9');
  assert.equal(landscape.width,430);assert.equal(landscape.height,430/(16/9));
  const original=previewFrameGeometry(600,900,'original',4/3);
  assert.equal(original.width/original.height,4/3);
  assert.deepEqual(previewFrameGeometry(600,900,'bad'),previewFrameGeometry(600,900,'16:9'));
});

test('단계 패널 HTML의 ID·연결 대상과 설정 입력을 중복 없이 유지',()=>{
  const html=readFileSync(new URL('../web/clip-studio.html',import.meta.url),'utf8');
  assert.doesNotMatch(html,/<details|studio-drawer-heading/);
  assert.doesNotMatch(html,/💡|data-help=|id="(?:studio-help|inspector-help|inspector-help-content)"/);
  assert.doesNotMatch(html,/class="studio-header"|id="studio-project-title"/);
  const ids=[...html.matchAll(/\sid="([^"]+)"/g)].map(x=>x[1]);
  assert.equal(ids.length,new Set(ids).size);
  for(const match of html.matchAll(/\s(?:aria-controls|aria-labelledby|for)="([^"]+)"/g))
    for(const id of match[1].split(' '))assert.ok(ids.includes(id),'존재하는 연결 대상: '+id);
  for(const step of studioSteps)assert.ok(ids.includes('panel-'+step)&&ids.includes('tab-'+step));
  assert.match(html,/<div id="studio-presets" data-inline="true"/);
  for(const id of ['source-version','source-list','range-form','image-file','image-width','caption-font','caption-size','preset-apply','profile-undo','render-start'])assert.ok(ids.includes(id));
});

test('편집기 복귀는 진입 화면과 선택 VOD를 유지하고 준비 링크는 분리',()=>{
  const project={root:'/Volumes/테스트 자료/VOD',vod_id:'123'};
  for(const page of ['use','context','speech','prepare','report','external','library','register','jobs','settings','voices','explore']){
    const links=studioReturnLinks(project,page),url=new URL(links.back,'http://127.0.0.1:1234/session/clip-studio.html');
    assert.equal(url.pathname,'/session/');assert.equal(url.hash,'#'+page);
    assert.equal(url.searchParams.get('root'),project.root);assert.equal(url.searchParams.get('vod_id'),project.vod_id);
    assert.equal(new URL(links.prepare,url).hash,'#prepare');
  }
  assert.equal(studioReturnLinks(project,'use').label,'← 이전');
  assert.equal(studioReturnLinks(project,'use').aria,'작업 화면으로 돌아가기');
  for(const invalid of [undefined,null,'https://example.com','//example.com','../','__proto__','constructor'])
    assert.match(studioReturnLinks(project,invalid).back,/#use$/);
});

test('자막 내용·글꼴 색상·크기 위치는 별도로 열리며 입력 노드를 보존',()=>{
  const previous={document:globalThis.document,MutationObserver:globalThis.MutationObserver};
  const nodes=new Map(),buttons=new Map(),panels=[];let focused=null;
  class Node{
    constructor(){this.textContent='';this.value='';this.dataset={};this.hidden=false;this.children=[];this.attrs={};this.classes=new Set();this.classList={toggle:(key,on)=>on?this.classes.add(key):this.classes.delete(key),contains:key=>this.classes.has(key)};}
    setAttribute(k,v){this.attrs[k]=v;}
    get selectedOptions(){return [{textContent:this.value}];}
    append(...rows){for(const row of rows){if(row.parentElement)row.parentElement.children=row.parentElement.children.filter(x=>x!==row);this.children.push(row);row.parentElement=this;}}
    replaceChildren(...rows){this.children=[];this.append(...rows);}
    prepend(row){this.append(row);this.children=[row,...this.children.filter(x=>x!==row)];}
    insertBefore(row){this.prepend(row);}
    querySelector(){return this.children[0]||null;}
    focus(){focused=this;}
  }
  const $=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
  const keys=['sources','range-edit','layout','image','effects','volume','caption-content','caption-appearance','transcript','captions','font','caption-position'];
  for(const key of keys){const b=new Node();b.dataset.inspectorOpen=key;buttons.set(key,b);const p=$('inspector-'+key);p.dataset.inspector=key;panels.push(p);}
  const ratio=new Node();ratio.dataset.ratio='original';const body=new Node();
  globalThis.document={getElementById:$,createElement:()=>new Node(),addEventListener(){},dispatchEvent(){},querySelectorAll:s=>s==='[data-inspector]'?panels:s==='[data-inspector-open]'?[...buttons.values()]:[],querySelector:s=>s==='.inspector-body'?body:s==='[data-ratio][aria-pressed=true]'?ratio:buttons.get(/data-inspector-open="([^"]+)"/.exec(s)?.[1])||null};
  globalThis.MutationObserver=class{observe(){}};
  try{
    $('caption-size').value='27';$('caption-version').value='보존할 전사';$('brightness').value='0';$('contrast').value='1';$('saturation').value='1';$('effect-fade').value='0';
    const ui=createStudioInspector(),sample=$('caption-sample-dock');
    ui.setTab('caption');buttons.get('caption-appearance').onclick();
    assert.equal($('inspector-caption-appearance').hidden,false);assert.equal(sample.parentElement,$('inspector-caption-appearance'));
    assert.equal($('inspector-font').hidden,false);assert.equal($('inspector-caption-position').hidden,true);
    $('caption-size').value='29';$('inspector-back').onclick();
    assert.equal($('overview-caption').hidden,false);assert.equal(focused,buttons.get('caption-appearance'));assert.equal($('caption-size').value,'29');
    assert.equal(sample.parentElement,$('overview-caption'));
    buttons.get('caption-content').onclick();assert.equal($('inspector-transcript').hidden,false);assert.equal($('inspector-captions').hidden,false);
    $('inspector-close').onclick();assert.equal($('overview-caption').hidden,false);assert.equal(focused,buttons.get('caption-content'));assert.equal($('caption-version').value,'보존할 전사');
    ui.open('font');assert.equal($('inspector-caption-appearance').hidden,false);assert.equal($('inspector-caption-position').hidden,true);
    $('inspector-back').onclick();assert.equal($('overview-caption').hidden,false);
    ui.open('caption-position');assert.equal($('inspector-caption-position').hidden,false);assert.equal($('inspector-caption-appearance').hidden,true);assert.equal(sample.parentElement,$('inspector-caption-position'));
    $('inspector-back').onclick();
    ui.setTab('range');ui.open('sources');assert.equal($('inspector-sources').hidden,false);
    ui.setTab('preset');assert.ok(panels.every(p=>p.hidden));
  }finally{Object.assign(globalThis,previous);}
});

test('설정 패널을 닫는 중 다시 열어도 이전 애니메이션이 새 패널을 숨기지 않음',()=>{
  const previous={document:globalThis.document,ResizeObserver:globalThis.ResizeObserver};
  const nodes=new Map();let focused=null;const animations=[];
  class Node{
    constructor(){this.style={};this.hidden=false;this.inert=false;this.dataset={};this.children=[];this.clientWidth=840;this.attrs={};this.classes=new Set();this.classList={add:k=>this.classes.add(k),remove:k=>this.classes.delete(k),toggle(){}};}
    append(...rows){this.children.push(...rows);}
    after(){} remove(){} getAttribute(k){return this.attrs[k];}setAttribute(k,v){this.attrs[k]=v;}
    dispatchEvent(){}focus(){focused=this;}
    animate(){const animation={cancel(){this.cancelled=true;}};animations.push(animation);return animation;}
  }
  const $=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
  const body=new Node(),events=[];
  globalThis.document={body,cookie:'',createElement:()=>new Node(),getElementById:$,querySelector:$,addEventListener(){},dispatchEvent:e=>events.push(e)};
  globalThis.ResizeObserver=class{observe(){}disconnect(){}};
  try{
    const ui=createStudioWorkspace({onStep(){}}),panel=$('.inspector');
    ui.close();assert.equal(panel.inert,true);const pending=animations.at(-1);
    ui.setStep('frame');assert.equal(pending.cancelled,true);assert.equal(panel.inert,false);pending.onfinish();assert.equal(panel.hidden,false);
    ui.close();animations.at(-1).onfinish();assert.equal(panel.hidden,true);assert.ok(body.classes.has('studio-panel-closed'));assert.equal(events.at(-1).detail.panel,'');
    assert.equal(focused,$('tab-frame'));ui.setStep('caption');assert.equal(panel.hidden,false);assert.ok(!body.classes.has('studio-panel-closed'));
  }finally{Object.assign(globalThis,previous);}
});


test('구간 단계의 담은 목록은 기존 구간 선택 경로를 재사용하고 원본 목록을 변경하지 않음',()=>{
  const previous={document:globalThis.document,MutationObserver:globalThis.MutationObserver};let refresh,selected=0;
  const make=()=>({children:[],attrs:{},append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},setAttribute(k,v){this.attrs[k]=v;}});
  const source={getAttribute:()=> 'true',querySelector:s=>({textContent:s==='strong'?'1. 현재 장면':'00:01:00 · 00:00:30'}),click(){selected++;}};
  let rows=[source];const assembly={querySelectorAll:()=>rows},container=make(),count=make();
  globalThis.document={createElement:make};globalThis.MutationObserver=class{constructor(callback){refresh=callback;}observe(){}disconnect(){}};
  try{
    const ui=bindStudioSelection(assembly,container,count);
    assert.equal(count.textContent,'담은 구간 1개');assert.equal(container.children[0].attrs['aria-pressed'],'true');
    container.children[0].onclick();assert.equal(selected,1);assert.equal(rows[0],source);
    rows=[];refresh();assert.equal(count.textContent,'담은 구간 0개');assert.match(container.children[0].textContent,/직접 추가/);ui.destroy();
  }finally{Object.assign(globalThis,previous);}
});
