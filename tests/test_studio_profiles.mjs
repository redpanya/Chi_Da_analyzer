import test from 'node:test';
import {mixPresetRow,mixStudioURL} from '../web/mix-studio.js';
import assert from 'node:assert/strict';
import {profileState,presetOptions,studioProfiles} from '../web/studio-profiles.js';
const base={ratio:'16:9',caption:false,font:'auto',font_size:22,image:{asset:'same'},game:[0,0,100,100],mode:'joined'};
test('구간 전환은 초안을 변경하지 않고 현재 편집만 개별화',()=>{
  const model=profileState(base),a={id:'a'},b={id:'b'};
  model.shown(model.select(a));model.capture(base);assert.equal(a.options,undefined);
  model.capture({...base,ratio:'9:16',caption:true});assert.equal(a.options.ratio,'9:16');
  model.shown(model.select(b));model.capture(base);assert.equal(b.options,undefined);assert.equal(model.effective(a).caption,true);
  assert.equal(model.effective(b).font_size,22);
  assert.deepEqual(model.outputOptions({...base,mode:'separate',ratio:'4:5'}),{...base,mode:'separate'});
});
test('예전 초안의 기존 구간과 새로 담은 구간은 서로 다른 초기값으로 열리고 저장된다',()=>{
  const old={id:'old'},fresh={id:'new'},different={id:'override',options:{ratio:'1:1'}};
  const model=profileState(base,{ratio:'original',image:null},[old,different]);
  assert.equal(model.rowOptions(old),undefined);
  assert.deepEqual(model.rowOptions(different),{ratio:'1:1'});
  const initial=model.select(fresh);
  assert.equal(initial.image,null);
  assert.equal(initial.ratio,'original');
  model.shown(initial);model.capture({...initial,ratio:'4:5'});
  assert.deepEqual(model.rowOptions(fresh),{ratio:'4:5',image:null});
  assert.deepEqual(model.select(old),presetOptions(base));
  assert.deepEqual(model.outputOptions(initial),presetOptions(base));
});

test('프리셋 일괄 적용은 PNG까지 포함한 값의 사본이며 미선택 구간 보존',()=>{
  const model=profileState(base),a={id:'a'},b={id:'b'},c={id:'c'};
  const preset=presetOptions({...base,ratio:'1:1',game:[10,0,90,100]});
  assert.deepEqual(preset.image,base.image);assert.notEqual(preset.image,base.image);assert.equal(preset.mode,undefined);
  model.apply([a,b],preset);preset.game[0]=50;
  assert.equal(a.options.game[0],10);a.options.game[0]=20;assert.equal(b.options.game[0],10);
  assert.deepEqual(a.options.image,base.image);assert.equal(c.options,undefined);
});
test('구형 소수 크기와 PNG는 다른 속성을 직접 수정해도 보존',()=>{
  const row={id:'a',options:{font_size:27.5,image:{asset:'old',x:33}}},model=profileState(base);
  const display={...model.select(row),font_size:28};
  model.shown(display);assert.equal(model.capture(display),false);
  model.capture({...display,ratio:'4:5'});
  assert.deepEqual(row.options,{font_size:27.5,image:{asset:'old',x:33},ratio:'4:5'});
  assert.deepEqual(model.select(null),presetOptions(base));
  assert.equal(model.capture({...base,ratio:'1:1'}),false);
});

test('자막·PNG 준비 전에도 복원한 현재 구간과 담은 개수를 표시',()=>{
  const oldDocument=globalThis.document,elements=new Map();
  const el=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',hidden:false,options:[{},{},{}]});return elements.get(id);};
  globalThis.document={getElementById:el,querySelectorAll:()=>[]};
  try{
    const row={id:'saved',title:'복원한 구간'},before=structuredClone(row);
    let rows=[];let writes=0;let shown=structuredClone(base);
    const ui=studioProfiles({api:async()=>({presets:[]}),read:()=>shown,write:value=>{shown=value;writes++;},
      selection:()=>rows,onChange:()=>{},valid:()=>true,canSwitch:()=>true});
    ui.labels(null);assert.equal(el('profile-scope-badge').textContent,'선택 없음');
    rows=[row];ui.labels(row);
    assert.equal(el('profile-scope-badge').textContent,'현재 구간');
    assert.match(el('profile-active').textContent,/복원한 구간/);
    assert.equal(writes,0);assert.deepEqual(row,before);
    ui.init(base,row);el('studio-preset-list').onchange({target:el('studio-preset-list')});
    assert.equal(el('profile-scope-badge').textContent,'현재 구간');
    assert.match(el('profile-active').textContent,/복원한 구간/);
    assert.deepEqual(row,before);
  }finally{globalThis.document=oldDocument;}
});

for(const editor of ['클립','믹스'])test(editor+' 프리셋 대상의 개수와 제목이 적용 결과와 일치하고 되돌리기로 복원',async()=>{
  const oldDocument=globalThis.document,oldOption=globalThis.Option,elements=new Map();
  const el=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',hidden:false,options:[{},{},{}],
    replaceChildren(...items){this.options=items;},showModal(){},close(){}});return elements.get(id);};
  globalThis.document={getElementById:el,querySelectorAll:()=>[]};
  globalThis.Option=class{constructor(text,value){this.textContent=text;this.value=value;}};
  try{
    const initial={...base,layout:'split',image:{asset:'same',y:64}},
      a={id:'a',title:'현재',options:{...initial,layout:'single',image:{asset:'same',y:19}}},
      b={id:'b',title:'다른 구간',options:{...initial,image:null}};
    let shown=structuredClone(initial),allowed=true,ui,undo;
    const preset={id:'preset',name:'단일 화면',options:presetOptions({...base,layout:'single',ratio:'9:16'})};
    delete preset.options.image; // 이전 형식은 대상의 PNG를 유지
    ui=studioProfiles({api:async action=>action==='studio-preset-apply'?{options:preset.options}:{presets:[preset]},read:()=>shown,write:v=>{shown=v;},
      mix:editor==='믹스'?{presetRows:active=>[active,b].filter(Boolean)}:null,
      selection:()=>editor==='믹스'?[a]:[a,b],onChange:()=>ui.capture(),valid:()=>true,canSwitch:()=>allowed,onUndoPoint:(_,restore)=>{undo=restore;}});
    ui.init(initial,a);ui.preparePresets();await new Promise(resolve=>setImmediate(resolve));
    el('studio-preset-list').value=preset.id;
    for(const target of ['current','checked','all']){
      const before=structuredClone([a,b]);
      ui.check('b',true);el('profile-target').value=target;el('profile-target').onchange();
      const preview={current:'1. 현재',checked:'2. 다른 구간',all:'1. 현재\n2. 다른 구간'};
      assert.equal(el('preset-target-names').textContent,preview[target]);
      assert.equal(el('preset-target-count').textContent,'적용할 구간 '+(target==='all'?2:1)+'개');
      await el('preset-apply').onclick();
      assert.equal(a.options.ratio,target==='checked'?initial.ratio:'9:16');
      assert.equal(b.options.ratio,target==='current'?initial.ratio:'9:16');
      assert.equal(a.options.image.y,19);assert.equal(b.options.image,null);
      undo();assert.deepEqual([a,b],before);
    }
    el('profile-target').value='checked';ui.check('b',false);
    assert.equal(el('preset-apply').disabled,true);
    assert.equal(el('preset-target-names').textContent,'');
    assert.equal(el('preset-target-count').textContent,'적용할 구간 0개');
    el('profile-target').value='all';
    if(editor==='믹스'){
      b.problem='원본 영상을 찾을 수 없습니다';ui.labels();
      assert.equal(el('preset-apply').disabled,true);
      assert.match(el('preset-target-note').textContent,/다른 구간/);
      delete b.problem;ui.labels();
      assert.equal(el('preset-apply').disabled,false);
    }
    const before=structuredClone([a,b]);
    allowed=false;await el('preset-apply').onclick();
    assert.deepEqual([a,b],before);
  }finally{globalThis.document=oldDocument;globalThis.Option=oldOption;}
});

test('같은 프리셋 저장은 확인 전 전송하지 않고 취소·새 이름을 구분',async()=>{
  const previous={document:globalThis.document,Option:globalThis.Option},nodes=new Map(),calls=[];
  const $=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',options:[{},{},{}],open:false,
    replaceChildren(...items){this.options=items;},showModal(){this.open=true;},close(){this.open=false;}});return nodes.get(id);};
  globalThis.document={getElementById:$,querySelectorAll:()=>[]};
  globalThis.Option=class{constructor(text,value){this.textContent=text;this.value=value;}};
  try{
    const preset={id:'saved',name:'기존 프리셋',revision:3,options:presetOptions(base)};
    let shown=structuredClone(base);const row={id:'clip',title:'장면'};
    const api=async(action,data)=>{calls.push([action,data]);return {presets:[preset],id:preset.id};};
    const ui=studioProfiles({api,identity:()=>({root:'test',vod_id:'1'}),read:()=>shown,write:v=>shown=v,
      selection:()=>[row],onChange(){},valid:()=>true,canSwitch:()=>true});
    ui.init(base,row);ui.preparePresets();await new Promise(r=>setImmediate(r));
    $('studio-preset-list').value=preset.id;$('studio-preset-list').onchange();
    assert.equal($('studio-preset-name').value,preset.name);
    await $('preset-save').onclick();assert.equal($('studio-preset-overwrite').open,true);
    assert.equal(calls.filter(([a])=>a==='studio-preset-save').length,0);
    $('preset-overwrite-cancel').onclick();await $('preset-overwrite-confirm').onclick();
    assert.equal(calls.filter(([a])=>a==='studio-preset-save').length,0);
    await $('preset-save').onclick();await $('preset-overwrite-confirm').onclick();
    let sent=calls.at(-1)[1];assert.equal(sent.id,preset.id);assert.equal(sent.revision,3);assert.deepEqual(sent.options.image,base.image);
    assert.equal($('studio-preset-overwrite').open,false);
    $('studio-preset-name').value='새 이름';await $('preset-save').onclick();
    sent=calls.at(-1)[1];assert.equal(sent.id,undefined);assert.equal(sent.name,'새 이름');
    assert.equal(row.options,undefined);
    shown={...shown,ratio:'9:16'};ui.capture();
    await $('preset-save').onclick();
    assert.equal(calls.at(-1)[1].options.ratio,'9:16');
  }finally{Object.assign(globalThis,previous);}
});

test('PNG 준비 응답이 늦게 와도 그 사이 바꾼 구간 편집은 덮어쓰지 않음',async()=>{
  const previous={document:globalThis.document,Option:globalThis.Option},nodes=new Map();
  const $=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',options:[{},{},{}],replaceChildren(...items){this.options=items;},showModal(){},close(){}});return nodes.get(id);};
  globalThis.document={getElementById:$,querySelectorAll:()=>[]};globalThis.Option=class{constructor(text,value){this.textContent=text;this.value=value;}};
  try{
    const preset={id:'saved',name:'PNG 포함',revision:1,options:presetOptions({...base,ratio:'9:16'})};let finish;
    const api=async action=>action==='studio-preset-apply'?await new Promise(r=>finish=r):{presets:[preset]};
    let shown=structuredClone(base);const row={id:'clip',title:'장면'};
    const ui=studioProfiles({api,read:()=>shown,write:v=>shown=v,selection:()=>[row],onChange(){},valid:()=>true,canSwitch:()=>true});
    ui.init(base,row);ui.preparePresets();await new Promise(r=>setImmediate(r));
    $('studio-preset-list').value=preset.id;$('profile-target').value='current';const pending=$('preset-apply').onclick();
    shown={...shown,ratio:'1:1'};ui.capture();finish({options:preset.options});await pending;
    assert.equal(shown.ratio,'1:1');assert.equal(row.options.ratio,'1:1');assert.match($('profile-status').textContent,/편집 내용이 변경/);
    $('profile-target').value='checked';ui.check(row.id,true);
    const checkedApply=$('preset-apply').onclick();ui.check(row.id,false);
    finish({options:preset.options});await checkedApply;
    assert.equal(row.options.ratio,'1:1');assert.equal($('preset-apply').disabled,true);
    assert.equal($('preset-target-count').textContent,'적용할 구간 0개');
  }finally{Object.assign(globalThis,previous);}
});

test('믹스 진입과 이전 실행기의 구간 설정 호환',()=>{
  const key='817ae8530f824bc6b9f52cf8b51ad560',item={key,title:'둘째 구간',problem:''};
  const root='/원본/보관함';
  for(const entry of ['mix-studio.html',undefined]){
    const url=new URL(mixStudioURL(root,key,entry,'preset'),'http://localhost/');
    assert.equal(url.pathname,entry?'/mix-studio.html':'/clip-studio.html');
    assert.deepEqual(Object.fromEntries(url.searchParams),{root,mix:key,step:'preset'});
  }
  for(const profiles of [undefined,{}]){
    const row=mixPresetRow(item,profiles);
    assert.equal(row.id,key);
    assert.equal(row.options,undefined);
    assert.match(row.problem,/실행기를 다시 시작/);
  }
  const options={volume:45,ratio:'1:1'};
  assert.deepEqual(mixPresetRow(item,{[key]:options}),{id:key,title:item.title,problem:'',options});
  assert.equal(mixPresetRow({...item,problem:'원본 없음'},{}).problem,'원본 없음');
});
