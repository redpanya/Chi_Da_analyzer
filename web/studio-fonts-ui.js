// 계열은 미리보기에서, 실제 설치 변형은 굵기·스타일 옵션에서 선택한다.
const $=id=>document.getElementById(id);
export function matchingFonts(fonts,language,query=''){
  const term=query.trim().toLocaleLowerCase();
  return fonts.filter(f=>f.languages.includes(language)&&`${f.family_name||''} ${f.label}`.toLocaleLowerCase().includes(term));
}
export function fontFamilies(fonts,language,query=''){
  const groups=new Map();
  for(const f of matchingFonts(fonts,language)){
    const id=f.family_id||f.family||f.id;
    if(!groups.has(id))groups.set(id,{id,label:f.family_name||f.family||f.label,faces:[]});
    groups.get(id).faces.push(f);
  }
  const term=query.trim().toLocaleLowerCase();
  return [...groups.values()].filter(g=>`${g.label} ${g.faces.map(f=>f.label).join(' ')}`.toLocaleLowerCase().includes(term));
}
export function chooseFace(faces,current){
  const same=faces.find(f=>f.id===current?.id);if(same)return same;
  return [...faces].sort((a,b)=>{
    const score=f=>[Number(Boolean(f.italic)!==Boolean(current?.italic)),Math.abs((f.weight??400)-(current?.weight??400))];
    const x=score(a),y=score(b);return x[0]-y[0]||x[1]-y[1]||a.label.localeCompare(b.label)||a.id.localeCompare(b.id);
  })[0];
}
export function studioFonts({api,identity,onChange}){
  const value=$('caption-font'),language=$('caption-language'),note=$('caption-font-note'),list=$('font-preview-list'),variant=$('font-variant');
  let fonts=[],languages={},page=0,loading=false,failed=false,serial=0,loadSerial=0,cache=new Map();
  const current=()=>fonts.find(f=>f.id===value.value);
  const opened=()=>!$('inspector-font').hidden&&!$('panel-caption').hidden&&$('font-options').open;
  function sample(){return languages[language.value]?.sample||'오늘도 즐거운 방송입니다! 123';}
  function notify(){value.dispatchEvent(new Event('change',{bubbles:true}));onChange();}
  function choices(){
    const face=current(),group=fontFamilies(fonts,language.value).find(g=>g.faces.some(f=>f.id===value.value));
    $('font-selected').textContent=value.value==='auto'?'기본 글꼴 · 언어에 맞춰 선택':`${face?.family_name||face?.family||'이전 글꼴'} · ${face?.style||'다시 선택 필요'}`;
    variant.replaceChildren();
    if(group){
      const sorted=[...group.faces].sort((a,b)=>a.weight-b.weight||Number(a.italic)-Number(b.italic)||a.label.localeCompare(b.label)||a.id.localeCompare(b.id));
      for(const f of sorted){
        const duplicate=sorted.filter(x=>x.style===f.style).length>1;
        const suffix=duplicate?` · ${f.font_version||f.font_format||'설치본'} · ${f.id.slice(0,6)}`:'';
        variant.append(new Option((f.style||f.label)+suffix,f.id));
      }
      variant.value=value.value;
    }else variant.append(new Option(value.value==='auto'?'자동 선택':'선택한 글꼴 확인 필요',value.value));
    variant.disabled=loading||failed||!group||group.faces.length<2;
    variant.hidden=!group||group.faces.length<2;
    $('font-variant-single').hidden=!variant.hidden;
    $('font-variant-single').textContent=face?.style||(value.value==='auto'?'자동 선택':'선택한 글꼴 확인 필요');
    note.textContent=loading?'설치 글꼴의 언어 지원을 확인하고 있습니다…':failed?'글꼴 목록을 불러오지 못했습니다. 다시 불러오기를 눌러주세요.':!matchingFonts(fonts,language.value).length?'선택 언어를 지원하는 글꼴이 없습니다. 설치 후 다시 불러오세요.':value.value==='auto'?'선택 언어의 기본 글꼴을 사용합니다.':!face?'이전에 선택한 글꼴이 없습니다. 다시 선택하세요.':!face.languages.includes(language.value)?'기존 글꼴은 선택 언어 지원이 확인되지 않았습니다. 다른 글꼴을 선택하세요.':language.value==='ko'&&!face.full_korean?'한글 기본 2,350자·자모 지원 · 드문 글자·외국어·기호는 실제 문장에서 확인합니다.':'선택한 글꼴과 굵기로 미리보기·저장에 적용합니다.';
  }
  function select(id,family){
    if(value.value!==id){value.value=id;notify();}else void previews();
    list.querySelector(`[data-family="${family}"]`)?.focus({preventScroll:true});
  }
  async function previews(){
    const ticket=++serial;list.replaceChildren();
    const all=fontFamilies(fonts,language.value,$('font-search').value),pages=Math.ceil(all.length/8);
    page=Math.max(0,Math.min(page,pages-1));
    $('font-page').textContent=`${all.length}개 계열 · ${all.length?page+1:0}/${pages}쪽`;
    $('font-prev').disabled=loading||page===0;$('font-next').disabled=loading||(page+1)*8>=all.length;
    if(!opened())return;
    if(loading||failed){list.textContent=loading?'글꼴 목록을 불러오는 중…':'목록을 불러오지 못했습니다. 설치 글꼴 다시 불러오기를 눌러주세요.';return;}
    const lang=language.value,text=sample(),face=current();
    const visible=[{id:'auto',label:'기본 글꼴 · 언어에 맞춰 선택',face:{id:'auto',style:'자동 선택',full_korean:true}},...all.slice(page*8,(page+1)*8).map(g=>({...g,face:chooseFace(g.faces,face)}))];
    for(const g of visible){
      const button=document.createElement('button');button.type='button';button.className='font-choice';button.dataset.family=g.id;
      const selected=g.id==='auto'?value.value==='auto':g.faces.some(f=>f.id===value.value);button.setAttribute('aria-pressed',String(selected));
      button.disabled=!matchingFonts(fonts,lang).length;
      const title=document.createElement('span');title.textContent=`${selected?'✓ ':''}${g.label} · ${g.face.style}`;
      const canvas=document.createElement('canvas');canvas.width=560;canvas.height=120;canvas.setAttribute('aria-hidden','true');
      const state=document.createElement('small');state.textContent='미리보기 준비 중…';button.append(title,canvas,state);button.onclick=()=>select(g.face.id,g.id);list.append(button);
      Object.assign(g,{canvas,state});
    }
    if(!all.length){const empty=document.createElement('p');empty.className='small';empty.textContent='검색 결과가 없습니다. 검색어를 바꿔 주세요.';list.append(empty);}
    // 파일 대신 저장 렌더러의 PNG만 받고, 보이는 계열만 순서대로 준비한다.
    for(const g of visible){
      if(ticket!==serial)break;
      const key=lang+':'+g.face.id;
      try{
        let png=cache.get(key);
        if(!png){const result=await api('studio-decoration-preview',{...identity(),text,size:[560,120],options:{caption:true,style:'basic',font:g.face.id,caption_language:lang,font_size:30,position:'center'}});png=result.png;if(cache.size>=96)cache.delete(cache.keys().next().value);cache.set(key,png);}
        if(ticket!==serial)break;
        const bytes=Uint8Array.from(atob(png),c=>c.charCodeAt(0));const bitmap=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
        if(ticket===serial){g.canvas.getContext('2d').drawImage(bitmap,0,0);g.state.textContent='클릭하여 선택';}bitmap.close();
      }catch(e){if(ticket===serial){g.state.textContent='미리보기 실패 · '+e.message;const retry=document.createElement('button');retry.type='button';retry.textContent='예시 다시 시도';retry.onclick=()=>void previews();g.canvas.parentElement.after(retry);}}
    }
  }
  async function load(selected=value.value,refresh=false){
    const ticket=++loadSerial;loading=true;failed=false;serial++;value.value=selected;choices();language.disabled=$('font-refresh').disabled=true;void previews();
    try{const data=await api('studio-fonts',{...identity(),refresh});if(ticket!==loadSerial)return;fonts=data.fonts;languages=data.languages;if(refresh)cache.clear();}
    catch(e){if(ticket!==loadSerial)return;failed=true;}
    finally{if(ticket===loadSerial){loading=false;language.disabled=$('font-refresh').disabled=false;choices();void previews();onChange();}}
  }
  value.addEventListener('change',()=>{choices();void previews();});
  variant.onchange=()=>{value.value=variant.value;notify();};
  language.addEventListener('change',()=>{if(!current()?.languages.includes(language.value))value.value='auto';page=0;notify();});
  $('font-refresh').onclick=()=>load(value.value,true);
  $('font-search').oninput=()=>{page=0;void previews();};
  $('font-prev').onclick=()=>{page--;void previews();};$('font-next').onclick=()=>{page++;void previews();};
  document.addEventListener('studio-inspector-change',()=>{if(opened())void previews();else serial++;});
  $('font-options').addEventListener('toggle',()=>{if(opened())void previews();else serial++;});
  window.addEventListener('pagehide',()=>{serial++;});window.addEventListener('pageshow',()=>{if(fonts.length)void previews();});
  return {sample,blocked:()=>loading||failed||!matchingFonts(fonts,language.value).length||(value.value!=='auto'&&!fonts.some(f=>f.id===value.value&&f.languages.includes(language.value))),
    async init(options={}){language.value=options.caption_language||'ko';await load(options.font||'auto');}};
}
