// 편집 대상과 프리셋은 값의 사본으로 분리한다. 구간 선택/재생만으로 초안을 바꾸지 않는다.
export const clipKeys=['ratio','fit','x','y','layout','split','game','face','volume','brightness','contrast','saturation','fade','caption','style','caption_design','font','caption_language','font_size','position','caption_x','caption_y','image'];
const clone=value=>structuredClone(value);
export const clipOptions=value=>Object.fromEntries(clipKeys.filter(k=>k in value).map(k=>[k,clone(value[k])]));
export const presetOptions=value=>Object.fromEntries(Object.entries(clipOptions(value)).filter(([k])=>k!=='image'));
export function profileState(initial){
  let base=clone(initial),current=null,scope='clip',shown='';
  const effective=row=>({...clone(base),...clone(row?.options||{})});
  return {
    effective,scope:()=>scope,current:()=>current,
    common:global=>({...clone(global),...clipOptions(base)}),
    shown:value=>{shown=JSON.stringify(clipOptions(value));},
    capture(value){
      const next=clipOptions(value),key=JSON.stringify(next);if(key===shown)return false;
      if(scope==='common')base={...base,...next};else if(current)current.options=next;else return false;
      shown=key;return true;
    },
    // 구간을 확인할 때는 출력과 같은 개별 적용값으로 돌아온다.
    select(row){current=row;scope='clip';return effective(row);},
    setScope(value){scope=value;return scope==='common'?clone(base):effective(current);},
    apply(rows,preset){for(const row of rows)row.options={...clipOptions(effective(row)),...clone(preset)};},
    reset(rows){for(const row of rows)delete row.options;},
  };
}

const $=id=>document.getElementById(id);
export function studioProfiles({api,read,write,selection,onChange,valid,canSwitch}){
  let model=null,restoring=false,presets=[],busy=false;const checked=new Set();
  const dialog=$('studio-presets'),status=$('profile-status');
  function capture(){if(!model||restoring)return;model.capture(read());labels();}
  function labels(){
    if(!model)return;
    const row=model.current(),members=selection();
    for(const id of checked)if(!members.some(r=>r.id===id))checked.delete(id);
    $('profile-active').textContent=model.scope()==='common'?'공통 기본값 · 개별 설정 없는 구간에 적용':row?`${row.title} · ${row.options?'개별 설정':'공통 기본값 사용'}`:'구간을 먼저 선택하세요';
    $('profile-active').title=$('profile-active').textContent;
    $('profile-preview-label').textContent=model.scope()==='common'?'공통 기본값 미리보기':'현재 구간 미리보기';
    $('profile-preview-note').hidden=model.scope()!=='common';
    $('profile-target').options[1].textContent=`체크한 구간 ${checked.size}개`;
    $('profile-target').options[2].textContent=`담은 전체 ${members.length}개`;
    $('preset-apply').disabled=busy||!presets.some(p=>p.id===$('studio-preset-list').value);
    $('preset-delete').disabled=busy||!$('studio-preset-list').value;
    $('preset-save').disabled=busy||!model.current()&&model.scope()!=='common';
    for(const badge of document.querySelectorAll('[data-profile-badge]')){
      const clip=members.find(r=>r.id===badge.dataset.profileBadge);badge.textContent=clip?.options?'개별 설정':'공통 기본값';
    }
  }
  function show(value){restoring=true;try{write({...read(),...clipOptions(value)});model.shown(read());$('profile-scope').value=model.scope();}finally{restoring=false;}labels();}
  function previewCurrent(){
    if(!model||model.scope()==='clip')return true;
    if(!canSwitch())return false;
    capture();show(model.select(model.current()));onChange();return true;
  }
  function targets(){
    const all=selection(),mode=$('profile-target').value;
    const rows=mode==='all'?all:mode==='checked'?all.filter(r=>checked.has(r.id)):all.filter(r=>r.id===model.current()?.id);
    if(!rows.length)throw Error(mode==='current'?'현재 구간을 먼저 담아 주세요.':'적용할 구간을 체크해 주세요.');return rows;
  }
  function setList(items,id=$('studio-preset-list').value){
    presets=items;$('studio-preset-list').replaceChildren(new Option('저장한 프리셋 선택',''),...items.map(p=>new Option(p.name,p.id)));
    if(items.some(p=>p.id===id))$('studio-preset-list').value=id;labels();
  }
  async function load(){try{setList((await api('studio-preset-list',{})).presets);}catch(e){status.textContent=e.message;}}
  async function action(fn){busy=true;labels();try{await fn();}catch(e){status.textContent=e.message;}finally{busy=false;labels();}}
  $('profile-scope').onchange=()=>{if(!model)return;if(!canSwitch()){$('profile-scope').value=model.scope();return;}const scope=$('profile-scope').value;capture();show(model.setScope(scope));onChange();};
  $('profile-preview-current').onclick=previewCurrent;
  $('open-studio-presets').onclick=()=>{if(!model||!canSwitch())return;capture();status.textContent='';dialog.showModal();void load();};
  $('studio-presets-close').onclick=()=>dialog.close();
  $('studio-preset-list').onchange=labels;
  $('preset-save').onclick=()=>action(async()=>{
    capture();if(!valid())throw Error('화면·자막 입력값을 확인한 뒤 프리셋을 저장하세요.');
    const value=await api('studio-preset-save',{name:$('studio-preset-name').value,options:presetOptions(read())});
    setList(value.presets,value.id);$('studio-preset-name').value='';status.textContent='현재 화면·자막 설정을 프리셋으로 저장했습니다.';
  });
  $('preset-apply').onclick=()=>{try{
    if(!canSwitch())return;
    capture();const preset=presets.find(p=>p.id===$('studio-preset-list').value);if(!preset)return;
    const rows=targets();model.apply(rows,preset.options);show(model.select(model.current()));onChange();
    status.textContent=`${rows.length}개 구간에 ‘${preset.name}’ 적용 · PNG는 구간별 배치 유지 · 현재 구간의 출력 설정을 표시합니다. 편집 초안을 저장하면 유지됩니다.`;
  }catch(e){status.textContent=e.message;}};
  $('profile-reset').onclick=()=>{try{if(!canSwitch())return;capture();const rows=targets();model.reset(rows);show(model.select(model.current()));onChange();status.textContent=`${rows.length}개 구간을 공통 기본값으로 되돌렸습니다.`;}catch(e){status.textContent=e.message;}};
  $('preset-delete').onclick=()=>{$('preset-delete-name').textContent=$('studio-preset-list').selectedOptions[0].textContent;$('studio-preset-delete').showModal();};
  $('preset-delete-cancel').onclick=()=>$('studio-preset-delete').close();
  $('preset-delete-confirm').onclick=()=>action(async()=>{
    const value=await api('studio-preset-delete',{id:$('studio-preset-list').value});setList(value.presets);
    $('studio-preset-delete').close();status.textContent='프리셋을 제거했습니다. 구간에 적용한 설정은 그대로 유지됩니다.';
  });
  return {capture,labels,previewCurrent,restoring:()=>restoring,common:value=>model?model.common(value):value,
    checked:id=>checked.has(id),check(id,value){value?checked.add(id):checked.delete(id);labels();},
    select(row){if(!model)return;show(model.select(row));onChange();},
    init(value,row){model=profileState(value);show(model.select(row));},
  };
}
