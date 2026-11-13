// 패널 밖에서 시작하고 끝난 클릭만 닫기로 처리한다. 내부 드래그와 중첩 확인창은 제외한다.
export function bindOutsideDismiss(panel,dismiss,{root=document,isOpen=()=>panel.open}={}){
  let start=null;
  const outside=event=>{
    if(event.target===panel){
      const r=panel.getBoundingClientRect();
      return event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom;
    }
    return !event.composedPath().includes(panel);
  };
  const available=()=>{
    const modal=root.querySelector('dialog:modal');
    return isOpen()&&(!modal||modal===panel);
  };
  root.addEventListener('pointerdown',event=>{
    start=event.button===0&&available()&&outside(event)?event:null;
  },true);
  root.addEventListener('pointercancel',()=>{start=null;},true);
  root.addEventListener('click',event=>{
    const down=start;start=null;
    if(down&&event.button===0&&available()&&outside(event)&&Math.hypot(event.clientX-down.clientX,event.clientY-down.clientY)<=8)dismiss();
  },true);
}
