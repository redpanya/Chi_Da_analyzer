// 재생 위치는 표시만 갱신한다. 목록을 움직이는 동작은 사용자가 켠 경우에만 실행한다.
export function resultPlayback({host,bar,media,visible=()=>true,followPage=()=>{}}){
  const label=document.createElement('label');label.className='result-follow';
  const input=document.createElement('input');input.type='checkbox';input.setAttribute('aria-label','재생 위치 따라가기');
  const text=document.createElement('span');text.textContent='재생 위치 따라가기';label.append(input,text);bar.append(label);
  let active=null;
  function update(){
    if(!visible())return;
    const at=media.currentTime*1000;if(!Number.isFinite(at))return;
    if(input.checked&&!media.paused)followPage(at);
    let next=null;
    for(const card of host.querySelectorAll('article[data-start]')){
      const playing=Number(card.dataset.start)<=at&&at<Number(card.dataset.end);
      card.classList.toggle('is-playing',playing);
      if(playing){card.setAttribute('aria-current','true');next??=card;}else card.removeAttribute('aria-current');
    }
    if(next!==active){active=next;if(input.checked&&!media.paused)active?.scrollIntoView({block:'nearest',behavior:'instant'});}
  }
  for(const event of ['timeupdate','seeked','play','pause'])media.addEventListener(event,update);
  input.onchange=()=>{active=null;update();};
  return {refresh:update,reset(){active=null;input.checked=false;}};
}
