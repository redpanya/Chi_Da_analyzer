import test from 'node:test';
import assert from 'node:assert/strict';
import {profileState,presetOptions,studioProfiles} from '../web/studio-profiles.js';
const base={ratio:'16:9',caption:false,font:'auto',font_size:22,image:{asset:'same'},game:[0,0,100,100],mode:'joined'};
test('구간 전환은 초안을 변경하지 않고 현재 편집만 개별화',()=>{
  const model=profileState(base),a={id:'a'},b={id:'b'};
  model.shown(model.select(a));model.capture(base);assert.equal(a.options,undefined);
  model.capture({...base,ratio:'9:16',caption:true});assert.equal(a.options.ratio,'9:16');
  model.shown(model.select(b));model.capture(base);assert.equal(b.options,undefined);assert.equal(model.effective(a).caption,true);
  model.shown(model.setScope('common'));model.capture({...base,font_size:30});
  assert.equal(model.effective(b).font_size,30);assert.equal(model.effective(a).font_size,22);
  assert.equal(model.common({...base,mode:'separate'}).mode,'separate');
});
test('프리셋 일괄 적용은 다른 구간과 PNG를 유지하는 값의 사본',()=>{
  const model=profileState(base),a={id:'a'},b={id:'b'},c={id:'c'};
  const preset=presetOptions({...base,ratio:'1:1',game:[10,0,90,100]});
  assert.equal(preset.image,undefined);assert.equal(preset.mode,undefined);
  model.apply([a,b],preset);preset.game[0]=50;
  assert.equal(a.options.game[0],10);a.options.game[0]=20;assert.equal(b.options.game[0],10);
  assert.deepEqual(a.options.image,base.image);assert.equal(c.options,undefined);
  model.reset([a]);assert.equal(a.options,undefined);assert.equal(b.options.ratio,'1:1');
});
test('공통 편집 후 구간 선택은 PNG를 포함한 실제 출력값을 표시하고 초안은 보존',()=>{
  const initial={...base,layout:'split',image:{asset:'same',x:50,y:64,width:80}},
    row={id:'individual',options:{layout:'single',image:{asset:'same',x:33,y:19,width:60}}},
    inherited={id:'inherited'},before=structuredClone(row),model=profileState(initial);
  model.select(row);model.shown(model.setScope('common'));
  model.capture({...initial,image:{...initial.image,y:70}});
  const display=model.select(row);model.shown(display);model.capture(display);
  assert.equal(model.scope(),'clip');assert.deepEqual(display,model.effective(row));
  assert.deepEqual(row,before);assert.equal(model.common({}).image.y,70);
  model.setScope('common');const shared=model.select(inherited);model.shown(shared);model.capture(shared);
  assert.equal(shared.image.y,70);assert.equal(inherited.options,undefined);
});

test('프리셋 적용·초기화·저장 확인 UI는 공통 편집을 종료하고 개별 출력과 일치',async()=>{
  const oldDocument=globalThis.document,oldOption=globalThis.Option,elements=new Map();
  const el=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',hidden:false,options:[{},{},{}],
    replaceChildren(...items){this.options=items;},showModal(){},close(){}});return elements.get(id);};
  globalThis.document={getElementById:el,querySelectorAll:()=>[]};
  globalThis.Option=class{constructor(text,value){this.textContent=text;this.value=value;}};
  try{
    const initial={...base,layout:'split',image:{asset:'same',y:64}},
      a={id:'a',title:'현재',options:{...initial,layout:'single',image:{asset:'same',y:19}}},
      b={id:'b',title:'다른 구간',options:{...initial,image:null}};
    let shown=structuredClone(initial),allowed=true,ui;
    const preset={id:'preset',name:'단일 화면',options:presetOptions({...base,layout:'single',ratio:'9:16'})};
    ui=studioProfiles({api:async()=>({presets:[preset]}),read:()=>shown,write:v=>{shown=v;},
      selection:()=>[a,b],onChange:()=>ui.capture(),valid:()=>true,canSwitch:()=>allowed});
    ui.init(initial,a);el('open-studio-presets').onclick();await new Promise(resolve=>setImmediate(resolve));
    el('studio-preset-list').value=preset.id;
    const common=()=>{el('profile-scope').value='common';el('profile-scope').onchange();
      assert.equal(el('profile-preview-note').hidden,false);assert.equal(shown.image.y,64);};
    const matches=()=>{assert.equal(el('profile-scope').value,'clip');assert.equal(el('profile-preview-note').hidden,true);
      assert.deepEqual(shown,{...ui.common(shown),...a.options});};
    for(const target of ['current','checked','all']){
      common();ui.check('b',true);el('profile-target').value=target;el('preset-apply').onclick();matches();
      assert.equal(a.options.image.y,19);assert.equal(b.options.image,null);
    }
    common();const before=JSON.stringify([a,b,ui.common(shown)]);
    allowed=false;assert.equal(ui.previewCurrent(),false);el('preset-apply').onclick();
    assert.equal(el('profile-scope').value,'common');assert.equal(JSON.stringify([a,b,ui.common(shown)]),before);
    allowed=true;assert.equal(ui.previewCurrent(),true);matches();
    assert.equal(JSON.stringify([a,b,ui.common(shown)]),before);
    common();el('profile-preview-current').onclick();matches();
    common();el('profile-target').value='current';el('profile-reset').onclick();matches();
    assert.equal(a.options,undefined);assert.equal(shown.image.y,64);assert.equal(b.options.image,null);
  }finally{globalThis.document=oldDocument;globalThis.Option=oldOption;}
});
