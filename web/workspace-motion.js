// 빠른 왕복에서는 이전 완료 콜백을 버려 새로 연 패널을 닫지 않는다.
export const reducedMotion=globalThis.matchMedia?.('(prefers-reduced-motion: reduce)');
const motions=new Map();
export function cancelMotion(node){motions.get(node)?.cancel();motions.delete(node);}
export function animateUI(node,frames,options={},finished){
 if(!node)return;cancelMotion(node);
 if(reducedMotion?.matches||!node.animate){finished?.();return;}
 const animation=node.animate(frames,{duration:240,easing:'cubic-bezier(.2,.8,.2,1)',...options});motions.set(node,animation);
 animation.onfinish=()=>{if(motions.get(node)!==animation)return;motions.delete(node);finished?.();};
 return animation;
}
export function enterView(node,direction=1){return animateUI(node,[{opacity:0,transform:`translate${direction===0?'Y':'X'}(${direction===0?8:direction*12}px)`},{opacity:1,transform:'translate(0)'}],{duration:260});}
export function bindDocumentMotion(root=document,win=window){
 const classes=root.documentElement.classList;
 if('CSSViewTransitionRule' in win){
  win.addEventListener('pagereveal',event=>{
   if(event.viewTransition){
    const panel=root.querySelector(root.body.classList.contains('studio-workspace')?'.studio-grid':'main');
    animateUI(panel,[{translate:'0 4px'},{translate:'0 0'}],{duration:150});
   }
  });
 }else classes.add('document-motion-fallback');
 root.addEventListener('click',event=>{
  if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
  const link=event.target.closest?.('a[aria-current="page"][href]');
  if(!link||link.hasAttribute('download')||(link.target&&link.target!=='_self'))return;
  const target=new URL(link.href,win.location.href),current=new URL(win.location.href);
  if(target.origin===current.origin&&target.pathname===current.pathname&&target.search===current.search&&(!target.hash||target.hash===current.hash))event.preventDefault();
 });
}
reducedMotion?.addEventListener('change',()=>{if(reducedMotion.matches)[...motions.values()].forEach(animation=>animation.finish());});
