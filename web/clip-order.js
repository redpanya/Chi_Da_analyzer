// 포인터가 목록 밖으로 나가거나 취소되면 기존 순서를 유지한다.
export function bindClipOrder(list, move, horizontal=false) {
  let drag, target, frame, suppressClick=false;
  list.dataset.clipOrderAxis=horizontal?'horizontal':'vertical';
  function liftCard() {
    const preview=document.createElement('div');
    preview.className='clip-order-preview';
    preview.setAttribute('aria-hidden','true');
    for (const tag of ['strong','small']) {
      const original=drag.row.querySelector(tag);
      if (original) {
        const line=document.createElement(tag);
        line.textContent=original.textContent;
        preview.append(line);
      }
    }
    document.body.append(preview);
    drag.preview=preview;
    drag.previewSize=preview.getBoundingClientRect();
    drag.row.classList.add('clip-order-source');
  }
  function mark(row) {
    if (row===target) return;
    target?.classList.remove('clip-drop-target');
    target=row;
    target?.classList.add('clip-drop-target');
  }
  function rowAt(x,y) {
    const row=document.elementFromPoint(x,y)?.closest('[data-order-key]');
    return row?.parentElement===list && row!==drag.row ? row : null;
  }
  function scrollHost() {
    if (horizontal) return list;
    for (let node=list.parentElement;node;node=node.parentElement) {
      if (/auto|scroll/.test(getComputedStyle(node).overflowY) && node.scrollHeight>node.clientHeight) return node;
    }
    return document.scrollingElement;
  }
  function trackEdge() {
    if (!drag.row.isConnected || !list.getClientRects().length) {
      finish({pointerId:drag.id});
      return;
    }
    const {x,y,host}=drag;
    const rect=host.getBoundingClientRect(), pos=horizontal?x:y;
    const start=Math.max(0,horizontal?rect.left:rect.top);
    const end=Math.min(horizontal?innerWidth:innerHeight,horizontal?rect.right:rect.bottom);
    const delta=pos<start+28?-10:pos>end-28?10:0;
    if (delta && x>=rect.left && x<=rect.right && y>=rect.top && y<=rect.bottom) {
      host.scrollBy(horizontal?delta:0,horizontal?0:delta);
      mark(rowAt(x,y));
    }
    frame=requestAnimationFrame(trackEdge);
  }
  list.addEventListener('pointerdown',e=>{
    if (drag || !e.isPrimary || e.button!==0) return;
    suppressClick=false;
    const grip=e.target.closest('[data-clip-grip]'),row=grip?.closest('[data-order-key]');
    if (!row || row.parentElement!==list || list.children.length<2) return;
    drag={row,grip,id:e.pointerId,startX:e.clientX,startY:e.clientY,host:scrollHost()};
    grip.setPointerCapture(e.pointerId);
    document.addEventListener('pointerup',finish,true);
    document.addEventListener('pointercancel',finish,true);
    document.addEventListener('keydown',interrupt);
    window.addEventListener('blur',interrupt);
  });
  list.addEventListener('pointermove',e=>{
    if (drag?.id!==e.pointerId) return;
    if (!drag.preview) {
      if (Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)<5) return;
      liftCard();
    }
    drag.x=e.clientX;drag.y=e.clientY;
    const {width,height}=drag.previewSize;
    const left=Math.max(4,Math.min(drag.x+12,innerWidth-width-4));
    const top=drag.y+12+height<=innerHeight-4 ? drag.y+12 : Math.max(4,drag.y-height-12);
    drag.preview.style.transform=`translate3d(${left}px,${top}px,0)`;
    mark(rowAt(drag.x,drag.y));
    if (!frame) frame=requestAnimationFrame(trackEdge);
  });
  function finish(e) {
    if (drag?.id!==e.pointerId) return;
    const row=e.type==='pointerup' && drag.preview && rowAt(e.clientX,e.clientY);
    const key=drag.row.dataset.orderKey;
    suppressClick=!!drag.preview;
    drag.preview?.remove();
    drag.row.classList.remove('clip-order-source');
    document.removeEventListener('pointerup',finish,true);
    document.removeEventListener('pointercancel',finish,true);
    document.removeEventListener('keydown',interrupt);
    window.removeEventListener('blur',interrupt);
    const {grip,id}=drag;
    cancelAnimationFrame(frame);frame=0;drag=null;mark(null);
    if (grip.hasPointerCapture(id)) grip.releasePointerCapture(id);
    if (row) move(key,Array.from(list.children).indexOf(row));
  }
  function interrupt(e) {
    if (drag && (e.type==='blur' || e.key==='Escape')) finish({pointerId:drag.id});
  }
  list.addEventListener('lostpointercapture',finish);
  list.addEventListener('click',e=>{
    if (suppressClick && e.detail) {e.preventDefault();e.stopPropagation();suppressClick=false;}
  },true);
}
