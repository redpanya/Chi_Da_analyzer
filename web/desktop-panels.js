const GUTTER=10;
export function fitPanelWidths(values,available,minWidths,flexIndex=1){
  const sizes=minWidths.map((min,i)=>Math.max(min,Number.isFinite(Number(values?.[i]))?Number(values[i]):min));
  let excess=sizes.reduce((a,b)=>a+b,0)-available;
  for(const i of [flexIndex,...sizes.map((_,i)=>i).filter(i=>i!==flexIndex)]){
    const take=Math.min(Math.max(0,excess),sizes[i]-minWidths[i]);sizes[i]-=take;excess-=take;
  }
  if(excess<0)sizes[flexIndex]-=excess;
  return sizes.map(n=>Math.round(n));
}
const localPreferences={
  read(key){
    try{const name=encodeURIComponent('chida.panels.'+key)+'=',saved=document.cookie.split('; ').find(row=>row.startsWith(name));if(saved)return JSON.parse(decodeURIComponent(saved.slice(name.length)));}catch{/* 포트 공통 설정이 없으면 현재 브라우저 설정을 사용한다. */}
    try{return JSON.parse(localStorage.getItem('chida.panels.'+key));}catch{return null;}
  },
  write(key,value){
    try{document.cookie=encodeURIComponent('chida.panels.'+key)+'='+encodeURIComponent(JSON.stringify(value))+'; Path=/; Max-Age=31536000; SameSite=Strict';}catch{/* 저장 실패는 현재 폭 조절에 영향을 주지 않는다. */}
    try{localStorage.setItem('chida.panels.'+key,JSON.stringify(value));}catch{/* 저장소 사용이 막혀 있어도 폭 조절은 유지한다. */}
  },
};
export function bindDesktopPanels({container,panels,key,initial,minWidths,flexIndex=1,preferences=localPreferences}){
  let requested=[...initial],current=[...initial],destroyed=false,changed=false;
  const handles=[],original=container.style.gridTemplateColumns;
  container.classList.add('desktop-panels');
  const available=()=>Math.max(0,container.clientWidth-(panels.length-1)*GUTTER);
  function render(){
    if(!container.clientWidth)return;
    current=fitPanelWidths(requested,available(),minWidths,flexIndex);
    container.style.gridTemplateColumns=current.map(n=>n+'px').join(` ${GUTTER}px `);
    handles.forEach(({separator},i)=>{
      separator.setAttribute('aria-valuemin',minWidths[i]);
      separator.setAttribute('aria-valuemax',current[i]+current[i+1]-minWidths[i+1]);
      separator.setAttribute('aria-valuenow',current[i]);
      separator.setAttribute('aria-valuetext',`${current[i]}픽셀`);
    });
  }
  function persist(){
    changed=true;
    requested=[...current];
    Promise.resolve(preferences.write(key,[...current])).catch(()=>{});
    container.dispatchEvent(new CustomEvent('chida-panelresize',{bubbles:true,detail:{key,widths:[...current]}}));
  }
  function adjust(i,delta){
    const change=Math.max(minWidths[i]-current[i],Math.min(current[i+1]-minWidths[i+1],delta));
    requested=[...current];requested[i]+=change;requested[i+1]-=change;render();
  }
  function reset(){requested=[...initial];render();persist();}
  panels.slice(0,-1).forEach((panel,i)=>{
    const gutter=document.createElement('div');gutter.className='desktop-panel-gutter';
    const separator=document.createElement('div');separator.className='desktop-panel-separator';separator.tabIndex=0;
    separator.setAttribute('role','separator');separator.setAttribute('aria-orientation','vertical');
    separator.setAttribute('aria-label',`${panel.getAttribute('aria-label')||['목록','미리보기'][i]||'패널'} 폭 조절. 좌우 키로 조절, Home으로 초기화`);
    const controls=document.createElement('div');controls.className='desktop-panel-controls';
    for(const [label,text,callback] of [['왼쪽 패널 좁히기','−',()=>{adjust(i,-32);persist();}],['왼쪽 패널 넓히기','+',()=>{adjust(i,32);persist();}],['패널 폭 초기화','↺',reset]]){
      const button=document.createElement('button');button.type='button';button.textContent=text;button.title=label;button.setAttribute('aria-label',label);button.onclick=callback;controls.append(button);
    }
    separator.onkeydown=event=>{
      if(!['ArrowLeft','ArrowRight','Home'].includes(event.key))return;
      event.preventDefault();if(event.key==='Home')reset();else{adjust(i,(event.key==='ArrowLeft'?-1:1)*(event.shiftKey?40:8));persist();}
    };
    separator.onpointerdown=event=>{
      if(event.button!==0)return;event.preventDefault();separator.focus();separator.setPointerCapture(event.pointerId);
      let last=event.clientX;gutter.classList.add('dragging');
      separator.onpointermove=move=>{adjust(i,move.clientX-last);last=move.clientX;};
      const finish=()=>{separator.onpointermove=null;separator.onpointerup=null;separator.onpointercancel=null;gutter.classList.remove('dragging');persist();};
      separator.onpointerup=finish;separator.onpointercancel=finish;
    };
    gutter.append(separator,controls);panel.after(gutter);handles.push({gutter,separator});
  });
  const observer=new ResizeObserver(render);observer.observe(container);render();
  Promise.resolve(preferences.read(key)).then(value=>{if(!destroyed&&!changed&&Array.isArray(value)&&value.length===panels.length){requested=value;render();}}).catch(()=>{});
  return {reset,apply(value){if(Array.isArray(value)&&value.length===panels.length){changed=true;requested=[...value];render();}},widths:()=>[...current],destroy(){destroyed=true;observer.disconnect();handles.forEach(({gutter})=>gutter.remove());container.classList.remove('desktop-panels');container.style.gridTemplateColumns=original;}};
}
