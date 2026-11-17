// 실제 폼에 이벤트를 대신 보내지 않고, 설명과 강조 표시만 관리한다.
export function createCoachmark({next,back,skip,disable,library,refresh}){
  const card=document.createElement('section');
  card.className='coachmark';card.tabIndex=-1;
  card.setAttribute('role','region');
  card.setAttribute('aria-labelledby','coachmark-title');
  card.setAttribute('popover','manual');
  card.innerHTML='<p class="coachmark-group"></p><h2 id="coachmark-title"></h2><p id="coachmark-text" aria-live="polite"></p><div class="coachmark-actions"><button type="button" data-library>바로 보관함 열기</button><button type="button" data-back>이전</button><button type="button" data-next class="primary"></button></div><div class="coachmark-dismiss"><button type="button" data-skip>이 안내 건너뛰기</button><button type="button" data-disable>모든 안내 끄기</button></div>';
  card.querySelector('[data-library]').onclick=library;
  card.querySelector('[data-back]').onclick=back;
  card.querySelector('[data-next]').onclick=next;
  card.querySelector('[data-skip]').onclick=skip;
  card.querySelector('[data-disable]').onclick=disable;
  let target=null,frame=0,oldDescription=null;
  const resize=new ResizeObserver(schedule);
  function position(){
    frame=0;
    if(!target)return;
    if(!target.isConnected||!target.getClientRects().length){refresh();return;}
    const r=target.getBoundingClientRect(),w=card.offsetWidth,h=card.offsetHeight;
    if(!CSS.supports('position-anchor: --coachmark-focus')){
      const view=document.documentElement;
      const edges=[r.top,view.clientWidth-r.right,view.clientHeight-r.bottom,r.left];
      card.style.setProperty('--coachmark-inset',edges.map(n=>`clamp(0px, ${n-4}px, 100%)`).join(' '));
    }
    const pad=10,gap=12,limit=(n,max)=>Math.max(pad,Math.min(n,max-pad));
    let x=limit(r.left,innerWidth-w),y=r.bottom+gap;
    if(y+h+pad>innerHeight){
      if(r.top>=h+gap+pad)y=r.top-h-gap;
      else if(r.right+w+gap+pad<=innerWidth){x=r.right+gap;y=limit(r.top,innerHeight-h);}
      else if(r.left>=w+gap+pad){x=r.left-w-gap;y=limit(r.top,innerHeight-h);}
      else y=r.top+r.height/2>innerHeight/2?pad:innerHeight-h-pad;
    }
    card.style.left=Math.round(x)+'px';
    card.style.top=Math.round(limit(y,innerHeight-h))+'px';
  }
  function schedule(){if(target&&!frame)frame=requestAnimationFrame(position);}
  function hide(){
    if(!target)return;
    target.classList.remove('coachmark-target');
    if(oldDescription===null)target.removeAttribute('aria-describedby');
    else target.setAttribute('aria-describedby',oldDescription);
    target=null;resize.disconnect();cancelAnimationFrame(frame);frame=0;
    document.removeEventListener('scroll',schedule,true);window.removeEventListener('resize',schedule);
    document.removeEventListener('keydown',key,true);
    card.remove();document.body.classList.remove('coachmark-rail');
  }
  function key(e){
    if(e.key==='Escape'&&!e.isComposing){e.preventDefault();e.stopPropagation();skip();}
  }
  return {hide,show(el,step,group,{first=false,label='다음',waiting=false,blocked=false,shortcut=false}={}){
    const restore=card.contains(document.activeElement),opening=!target;
    hide();
    target=el;
    document.body.classList.toggle('coachmark-rail',!!el.closest('.step-primary'));
    el.classList.add('coachmark-target');
    oldDescription=el.getAttribute('aria-describedby');
    el.setAttribute('aria-describedby',[oldDescription,'coachmark-text'].filter(Boolean).join(' '));
    card.querySelector('.coachmark-group').textContent=group;
    card.querySelector('h2').textContent=step.title;
    card.querySelector('#coachmark-text').textContent=step.text;
    const btn=card.querySelector('[data-next]');
    card.querySelector('[data-library]').hidden=!shortcut;
    btn.textContent=label;btn.hidden=waiting;btn.disabled=blocked;
    card.querySelector('[data-back]').hidden=first;
    card.querySelector('.coachmark-actions').hidden=first&&waiting;
    (el.closest('dialog[open]')||document.body).append(card);
    card.showPopover?.();
    const r=el.getBoundingClientRect();
    if(step.tab||r.top<0||r.bottom>innerHeight||r.left<0||r.right>innerWidth)el.scrollIntoView({block:step.tab?'nearest':'center',inline:'nearest',behavior:'instant'});
    position();resize.observe(el);resize.observe(card);
    document.addEventListener('scroll',schedule,true);window.addEventListener('resize',schedule);
    document.addEventListener('keydown',key,true);
    if(restore)(waiting?el:btn).focus?.({preventScroll:true});
    else if(opening&&document.activeElement===document.body)card.focus({preventScroll:true});
  }};
}
