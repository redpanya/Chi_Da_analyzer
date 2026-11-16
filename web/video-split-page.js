import {createVideoSplit} from './video-split.js';

// 메뉴를 왕복해도 같은 화면과 입력값을 유지한다.
export function createVideoSplitPage({root,workQueue}){
 let controller=null,loading=null;
 async function mount(){
  // 업데이트 도중 이전 문서와 새 스크립트가 함께 열리면 분할 도구만 복구한다.
  if(!root.querySelector('#split-video')){
   const response=await fetch('./');
   if(!response.ok)throw Error('영상 나누기 화면을 불러오지 못했습니다.');
   const section=new DOMParser().parseFromString(await response.text(),'text/html').querySelector('#video-split-page');
   if(!section?.querySelector('#split-video'))throw Error('영상 나누기 화면을 확인할 수 없습니다.');
   root.replaceChildren(...section.childNodes);
  }
  controller=createVideoSplit({root,workQueue});
 }
 function show(visible){
  root.hidden=!visible;
  if(!visible)controller?.pause();
  else if(!controller&&!loading)loading=mount().catch(error=>{
   const message=document.createElement('p'),retry=document.createElement('button');
   message.textContent=error.message;message.setAttribute('role','alert');
   retry.textContent='다시 불러오기';retry.onclick=()=>show(true);
   root.replaceChildren(message,retry);
  }).finally(()=>{loading=null;});
  return loading;
 }
 return {show,pause(){controller?.pause();}};
}
