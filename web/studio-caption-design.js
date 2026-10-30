// 템플릿은 시작값이다. 기존 다중 효과는 직접 수정하기 전까지 그대로 보존한다.
export function createCaptionDesign(host,select,note,error){
  const fields=[...host.querySelectorAll('[data-design]')];
  let catalog={},design=null,templates=[];
  const selected=()=>templates.find(t=>'template:'+t.id===select.value);
  const same=(a,b)=>Object.keys(a).every(k=>a[k]===b[k]);
  const legacy=()=>!selected()&&!['basic','box'].includes(select.value);
  function values(){return Object.fromEntries(fields.map(f=>[f.dataset.design,f.type==='checkbox'?f.checked:f.type==='number'?f.valueAsNumber:f.value]));}
  function status(){
    const template=selected();
    note.textContent=legacy()?'기존 자막 디자인을 유지합니다. 아래 옵션을 수정하면 단일 테두리·그림자의 맞춤 디자인으로 전환됩니다.':template?`${template.name} · ${same(design,template.design)?'저장한 색상·효과':'맞춤 변경됨 · 원래 템플릿은 유지'}`:design?'맞춤 설정 · 담은 모든 구간에 적용':'템플릿 기본값 · 아래 옵션을 직접 조절할 수 있습니다.';
    for(const group of ['outline','shadow','box']){
      const enabled=fields.find(f=>f.dataset.design===group).checked;
      host.querySelector(`[data-design-state="${group}"]`).textContent=enabled?'켜짐':'꺼짐';
      host.querySelector(`[data-design-controls="${group}"]`).hidden=!enabled&&!fields.some(f=>f.dataset.design.startsWith(group+'_')&&!f.validity.valid);
    }
  }
  function show(value){
    for(const field of fields){const v=value[field.dataset.design];if(field.type==='checkbox')field.checked=v;else field.value=v;}
    error.textContent='';status();
  }
  function cleanLegacy(){for(const option of [...select.options])if(option.dataset.legacy)option.remove();}
  // select는 input을 먼저 보낸다. 공통 미리보기가 읽기 전에 선택값을 적용한다.
  for(const kind of ['input','change'])select.addEventListener(kind,()=>{cleanLegacy();const template=selected();design=template?{...template.design}:null;show(design||catalog[select.value]);});
  for(const field of fields)field.addEventListener('input',()=>{
    const invalid=fields.some(f=>!f.validity.valid);
    error.textContent=invalid?'자막 효과 수치는 각 입력란에 표시된 범위 안에서 입력하세요.':'';
    if(!invalid){
      design=values();
      if(legacy()){select.value=design.box?'box':'basic';cleanLegacy();}
    }
    status();
  });
  return {read:()=>design?{...design}:null,valid:()=>fields.every(f=>f.validity.valid),
    style:()=>selected()?(design.box?'box':'basic'):select.value,
    selected,savable:()=>!legacy()&&fields.every(f=>f.validity.valid),
    snapshot:()=>({... (design || catalog[select.value])}),
    templates(items,selectId){
      const previous=select.value,wasTemplate=Boolean(selected());templates=items;
      for(const option of [...select.options])if(option.dataset.template)option.remove();
      for(const item of items){const option=new Option('내 템플릿 · '+item.name,'template:'+item.id);option.dataset.template='true';select.append(option);}
      const match=selectId?items.find(t=>t.id===selectId):items.find(t=>'template:'+t.id===previous);
      // 삭제된 템플릿의 적용값은 유지하고 이름 참조만 해제한다.
      select.value=match?'template:'+match.id:wasTemplate?(design?.box?'box':'basic'):previous;
      if(selectId&&match){design={...match.design};show(design);}else status();
    },
    init(definitions,options={}){
      catalog=definitions;design=options.caption_design?{...options.caption_design}:null;cleanLegacy();
      const style=options.style||'basic';
      if(!catalog[style])throw Error('자막 디자인 설정을 불러오지 못했습니다. 페이지를 새로 열어주세요.');
      if(!['basic','box'].includes(style)){const legacy=new Option('기존 디자인 유지',style);legacy.disabled=true;legacy.dataset.legacy='true';select.append(legacy);}
      select.value=style;show(design||catalog[style]);
    }};
}
