import test from 'node:test';
import assert from 'node:assert/strict';
import {bindOutsideDismiss} from '../web/panel-dismiss.js';

function fixture(){
  const listeners=new Map(),panel={open:true,getBoundingClientRect:()=>({left:700,right:1000,top:0,bottom:800})};
  let modal=null,closed=0;
  const root={querySelector:()=>modal,addEventListener(name,fn,capture){assert.equal(capture,true);listeners.set(name,fn);}};
  bindOutsideDismiss(panel,()=>{closed++;panel.open=false;},{root});
  const fire=(type,{target={},path=[target],x=100,y=100,button=0}={})=>listeners.get(type)?.({target,composedPath:()=>path,clientX:x,clientY:y,button});
  return {panel,fire,setModal:value=>modal=value,get closed(){return closed;}};
}
test('바깥 클릭은 한 번 닫고 패널 내부 클릭은 유지',()=>{
  const f=fixture();
  f.fire('pointerdown',{path:[{},f.panel]});f.fire('click',{path:[{},f.panel]});assert.equal(f.closed,0);
  f.fire('pointerdown');f.fire('click');assert.equal(f.closed,1);
  f.fire('click');assert.equal(f.closed,1);
});
test('패널을 연 클릭과 키보드 클릭은 즉시 닫지 않음',()=>{
  const f=fixture();f.panel.open=false;f.fire('pointerdown');f.panel.open=true;f.fire('click');assert.equal(f.closed,0);
  f.fire('click');assert.equal(f.closed,0);
});
test('내부에서 시작한 드래그와 취소된 포인터는 유지',()=>{
  const f=fixture();f.fire('pointerdown',{path:[{},f.panel]});f.fire('click');assert.equal(f.closed,0);
  f.fire('pointerdown');f.fire('click',{x:160});assert.equal(f.closed,0);
  f.fire('pointerdown');f.fire('pointercancel');f.fire('click');assert.equal(f.closed,0);
  f.fire('pointerdown',{button:2});f.fire('click',{button:2});assert.equal(f.closed,0);
});
test('모달 배경은 좌표로 구분하고 중첩 확인창은 닫지 않음',()=>{
  const f=fixture();f.setModal(f.panel);
  f.fire('pointerdown',{target:f.panel,x:800});f.fire('click',{target:f.panel,x:800});assert.equal(f.closed,0);
  f.setModal({});f.fire('pointerdown');f.fire('click');assert.equal(f.closed,0);
  f.setModal(f.panel);f.fire('pointerdown',{target:f.panel});f.fire('click',{target:f.panel});assert.equal(f.closed,1);
});
