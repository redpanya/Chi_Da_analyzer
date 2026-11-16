import {captureProfileOptions} from './studio-edit-undo.js';
// 편집 대상과 프리셋은 값의 사본으로 분리한다. 구간 선택/재생만으로 초안을 바꾸지 않는다.
export const clipKeys=['ratio','fit','x','y','layout','split','game','face','volume','brightness','contrast','saturation','fade','caption','style','caption_design','font','caption_language','font_size','position','caption_x','caption_y','image'];
const clone=value=>structuredClone(value);
export const clipOptions=value=>Object.fromEntries(clipKeys.filter(k=>k in value).map(k=>[k,clone(value[k])]));
export const presetOptions=clipOptions;
export function profileState(initial,newOptions={},savedRows=[]){
  const base=clipOptions(initial);
  let current=null,shown={};
  const saved=new WeakSet(savedRows);
  const newDefaults=Object.keys(newOptions).length?newOptions:null;
  function rowOptions(row){
    if(!row||saved.has(row)||!newDefaults)return row?.options;
    return {...newDefaults,...row.options};
  }
  const effective=row=>({...clone(base),...clone(rowOptions(row)||{})});
  return {
    effective,rowOptions,current:()=>current,
    outputOptions:global=>({...global,...clone(base)}),
    shown:value=>{shown=clipOptions(value);},
    capture(value){
      if(!current)return false;
      const next=clipOptions(value);
      const changes=Object.entries(next).filter(([key,v])=>JSON.stringify(v)!==JSON.stringify(shown[key]));
      if(!changes.length)return false;
      current.options={...current.options,...Object.fromEntries(changes)};
      shown=next;return true;
    },
    select(row){current=row;return effective(row);},
    apply(rows,preset){for(const row of rows)row.options={...clipOptions(effective(row)),...clone(preset)};},
  };
}

const $=id=>document.getElementById(id);
export function studioProfiles({api,identity=()=>({}),mix=false,read,write,selection,onChange,valid,canSwitch,onUndoPoint=()=>{}}){
  let model=null,restoring=false,presets=[],busy=false;const checked=new Set();
  let pendingSave=null;
  const dialog=$('studio-presets'),status=$('profile-status');
  const membersFor=row=>mix?mix.presetRows(row):selection();
  function targets(members=membersFor(model?.current())){
    const mode=$('profile-target').value;
    if(mode==='all')return members;
    if(mode==='checked')return members.filter(row=>checked.has(row.id));
    return members.filter(row=>row.id===model?.current()?.id);
  }
  function capture(){if(!model||restoring)return;model.capture(read());labels();}
  function labels(row=model?.current()){
    const members=membersFor(row);
    for(const id of checked)if(!members.some(r=>r.id===id))checked.delete(id);
    $('profile-active').textContent=row?row.title:'구간을 먼저 선택하세요';
    $('profile-active').title=$('profile-active').textContent;
    $('profile-scope-badge').textContent=row?(mix?'현재 믹스 구간':'현재 구간'):'선택 없음';
    if(!model)return;
    const rows=targets(members),indices=new Map(members.map((clip,i)=>[clip.id,i+1]));
    const names=rows.map(clip=>`${indices.get(clip.id)}. ${clip.title}`).join('\n');
    const count=`적용할 구간 ${rows.length}개`;
    if($('preset-target-count').textContent!==count)$('preset-target-count').textContent=count;
    if($('preset-target-names').textContent!==names)$('preset-target-names').textContent=names;
    const unavailable=rows.find(clip=>clip.problem);
    const emptyNote=$('profile-target').value==='checked'
      ?(mix?'미리보기 아래 믹스 구간에서 적용할 구간을 체크하세요.':'미리보기 아래 담은 구간에서 적용할 구간을 체크하세요.')
      :'적용할 구간을 먼저 담아 주세요.';
    $('preset-target-note').textContent=unavailable?`${unavailable.title} / ${unavailable.problem}`:rows.length?'':emptyNote;
    $('preset-apply').textContent=`${rows.length}개 구간에 적용`;
    $('preset-apply').disabled=busy||!rows.length||!!unavailable||!presets.some(p=>p.id===$('studio-preset-list').value);
    $('preset-delete').disabled=busy||!$('studio-preset-list').value;
    $('preset-save').disabled=busy||!row;
  }
  function show(value){restoring=true;try{write({...read(),...clipOptions(value)});model.shown(read());}finally{restoring=false;}labels();}
  function undoPoint(label,rows){
    const restore=captureProfileOptions(rows);
    return ()=>{onUndoPoint(label,()=>{restore();show(model.select(model.current()));onChange();status.textContent=label+'을 되돌렸습니다.';});};
  }
  function setList(items,id=$('studio-preset-list').value){
    presets=items;$('studio-preset-list').replaceChildren(new Option('저장한 프리셋 선택',''),...items.map(p=>new Option(p.name,p.id)));
    if(items.some(p=>p.id===id))$('studio-preset-list').value=id;labels();
  }
  async function load(){try{setList((await api('studio-preset-list',{})).presets);}catch(e){status.textContent=e.message;}}
  function preparePresets(){if(!model||!canSwitch())return false;capture();labels();status.textContent='';void load();return true;}
  async function action(fn){if(busy)return;busy=true;labels();try{await fn();}catch(e){status.textContent=e.message;}finally{busy=false;labels();}}
  $('profile-target').onchange=()=>labels();
  $('studio-presets-close').onclick=()=>{if(dialog.dataset?.inline==='true')document.dispatchEvent(new CustomEvent('studio-close-presets'));else dialog.close();};
  $('studio-preset-list').onchange=()=>{const preset=presets.find(p=>p.id===$('studio-preset-list').value);$('studio-preset-name').value=preset?.name||'';labels();};
  async function save(payload){
    const value=await api('studio-preset-save',payload);
    setList(value.presets,value.id);$('studio-preset-name').value=payload.name;
    status.textContent='화면, 자막, PNG 설정을 프리셋으로 저장했습니다.';
  }
  $('preset-save').onclick=()=>action(async()=>{
    if(!canSwitch())return;
    capture();
    if(!model.current())throw Error('저장할 구간을 선택하세요.');
    if(!valid())throw Error('화면과 자막 입력값을 확인한 뒤 프리셋을 저장하세요.');
    const name=$('studio-preset-name').value.normalize('NFC').trim();
    if(!name)throw Error('프리셋 이름을 입력하세요.');
    const payload={...identity(),name,options:presetOptions(model.effective(model.current()))},selected=presets.find(p=>p.id===$('studio-preset-list').value);
    if(selected?.name===name){
      pendingSave={...payload,id:selected.id,revision:selected.revision||1};
      $('preset-overwrite-name').textContent=name;$('preset-overwrite-error').textContent='';$('studio-preset-overwrite').showModal();
    }else await save(payload);
  });
  $('preset-overwrite-cancel').onclick=()=>{pendingSave=null;$('studio-preset-overwrite').close();};
  $('studio-preset-overwrite').addEventListener?.('cancel',e=>{if(busy)e.preventDefault();else pendingSave=null;});
  $('preset-overwrite-confirm').onclick=()=>action(async()=>{
    if(!pendingSave)return;
    $('preset-overwrite-confirm').disabled=$('preset-overwrite-cancel').disabled=true;
    try{await save(pendingSave);pendingSave=null;$('studio-preset-overwrite').close();}
    catch(e){$('preset-overwrite-error').textContent=e.message;throw e;}
    finally{$('preset-overwrite-confirm').disabled=$('preset-overwrite-cancel').disabled=false;}
  });
  $('preset-apply').onclick=()=>action(async()=>{
    if(!canSwitch())return;
    capture();const preset=presets.find(p=>p.id===$('studio-preset-list').value);if(!preset)return;
    const rows=targets(),before=JSON.stringify([read(),rows]),current=model.current();
    if(!rows.length||rows.some(row=>row.problem))return;
    const value=await api('studio-preset-apply',{...identity(),id:preset.id,revision:preset.revision||1});
    const now=targets();
    if(current!==model.current()||before!==JSON.stringify([read(),now])||rows.some((row,i)=>row!==now[i])||$('studio-preset-list').value!==preset.id)throw Error('프리셋 준비 중 편집 내용이 변경됐습니다. 적용 대상을 확인하고 다시 적용하세요.');
    const remember=undoPoint('프리셋 적용',rows);model.apply(rows,value.options);show(model.select(model.current()));onChange();remember();
    $('studio-preset-name').value=preset.name;
    status.textContent=`${rows.length}개 구간에 ‘${preset.name}’ 적용${'image' in value.options?' (PNG 설정 포함)':''}`;
  });
  $('preset-delete').onclick=()=>{$('preset-delete-name').textContent=$('studio-preset-list').selectedOptions[0].textContent;$('studio-preset-delete').showModal();};
  $('preset-delete-cancel').onclick=()=>$('studio-preset-delete').close();
  $('preset-delete-confirm').onclick=()=>action(async()=>{
    const value=await api('studio-preset-delete',{id:$('studio-preset-list').value});setList(value.presets);
    $('studio-preset-delete').close();status.textContent='프리셋을 제거했습니다. 구간에 적용한 설정은 그대로 유지됩니다.';
  });
  return {capture,labels,preparePresets,rowOptions:row=>model?model.rowOptions(row):row.options,restoring:()=>restoring,outputOptions:value=>model?model.outputOptions(value):value,
    checked:id=>checked.has(id),check(id,value){value?checked.add(id):checked.delete(id);labels();},
    select(row){if(!model)return;show(model.select(row));onChange();},
    init(value,row,newOptions){model=profileState(value,newOptions,selection());show(model.select(row));},
  };
}
