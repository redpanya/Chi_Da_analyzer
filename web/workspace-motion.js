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
export function navigateDocument(href,root=document,win=window){
 const target=new URL(href,win.location.href);
 const node=root.querySelector('.studio-grid')||root.querySelector('main');
 if(!node){win.location.assign(target.href);return;}
 // 실제 탐색을 사용해야 미저장 편집의 beforeunload 보호가 유지된다.
 return animateUI(node,[{opacity:1,transform:'translateY(0)'},{opacity:.65,transform:'translateY(-8px)'}],{duration:160},()=>win.location.assign(target.href));
}
export function bindDocumentMotion(root=document,win=window){
 win.addEventListener('pageshow',()=>{
  enterView(root.querySelector('.studio-grid')||root.querySelector('main'),0);
 });
 root.addEventListener('click',event=>{
  if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
  const link=event.target.closest?.('a[aria-current="page"][href]');
  if(!link||link.hasAttribute('download')||(link.target&&link.target!=='_self'))return;
  const target=new URL(link.href,win.location.href),current=new URL(win.location.href);
  if(target.origin===current.origin&&target.pathname===current.pathname&&target.search===current.search&&(!target.hash||target.hash===current.hash))event.preventDefault();
 });
 // document의 편집 저장 확인이 취소한 링크는 해당 처리 결과를 따른다.
 win.addEventListener('click',event=>{
  if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
  const link=event.target.closest?.('a[href]');
  if(!link||link.hasAttribute('download')||(link.target&&link.target!=='_self'))return;
  const target=new URL(link.href,win.location.href),current=new URL(win.location.href);
  const pages=['./','index.html','clip-studio.html','video-split.html'].map(path=>new URL(path,current).pathname);
  if(target.origin!==current.origin||target.pathname===current.pathname||!pages.includes(target.pathname))return;
  event.preventDefault();navigateDocument(target.href,root,win);
 });
 }
reducedMotion?.addEventListener('change',()=>{if(reducedMotion.matches)[...motions.values()].forEach(animation=>animation.finish());});
