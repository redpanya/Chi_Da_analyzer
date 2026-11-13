import {createVideoSplit} from './video-split.js';
import {enterView} from './workspace-motion.js';

// 메뉴를 왕복해도 같은 화면과 입력값을 유지한다.
export function createVideoSplitPage({root,workQueue}){
 let controller=null,loading=null;
 async function mount(){
  root.textContent='영상 나누기를 불러오는 중입니다.';
  try{
   const response=await fetch('video-split.html');
   if(!response.ok)throw Error('영상 나누기 화면을 불러오지 못했습니다.');
   const main=new DOMParser().parseFromString(await response.text(),'text/html').querySelector('main');
   if(!main?.querySelector('#split-video'))throw Error('영상 나누기 화면을 확인할 수 없습니다.');
   root.replaceChildren(...main.childNodes);
   controller=createVideoSplit({root,workQueue});
   if(!root.hidden)enterView(root,0);
  }catch(error){
   const message=document.createElement('p'),retry=document.createElement('button');
   message.textContent=error.message;message.setAttribute('role','alert');
   retry.textContent='다시 불러오기';retry.onclick=()=>show(true);
   root.replaceChildren(message,retry);
  }finally{loading=null;}
 }
 function show(visible){
  root.hidden=!visible;
  if(!visible)controller?.pause();
  else if(!controller&&!loading)loading=mount();
  return loading;
 }
 return {show,pause(){controller?.pause();}};
}
