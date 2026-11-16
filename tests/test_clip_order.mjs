import assert from 'node:assert/strict';
import test from 'node:test';
import {Element,dom} from './polish_dom.mjs';
import {bindClipOrder} from '../web/clip-order.js';

for(const horizontal of [false,true])test(horizontal?'가로 카드 순서 변경':'세로 목록 순서 변경',()=>{
  dom();
  globalThis.window=new Element();
  for (const target of [document,window]) {
    target.removeEventListener=(type,fn)=>{target.listeners[type]=target.listeners[type].filter(listener=>listener!==fn);};
  }
  const create=document.createElement;
  document.createElement=tag=>{
    const node=create(tag);
    node.getBoundingClientRect=()=>({width:120,height:60});
    node.remove=()=>{node.parentElement.children=node.parentElement.children.filter(child=>child!==node);};
    return node;
  };
  globalThis.innerWidth=640;globalThis.innerHeight=400;
  const list=new Element(),moves=[],items=['가','나','다'].map(key=>{
    const row=new Element();row.dataset.orderKey=key;row.closest=()=>row;
    const title=new Element('strong'),time=new Element('small');
    title.textContent=key;time.textContent='00:15';row.append(title,time);
    row.setPointerCapture=()=>{row.captured=true;};
    row.hasPointerCapture=()=>row.captured;
    row.releasePointerCapture=()=>{row.captured=false;};
    row.classList=new Set();row.classList.remove=row.classList.delete;
    return row;
  });
  list.append(...items);
  globalThis.requestAnimationFrame=()=>1;globalThis.cancelAnimationFrame=()=>{};
  document.elementFromPoint=x=>items[x/100]||null;
  bindClipOrder(list,(key,index)=>moves.push([key,index]),horizontal);
  assert.equal(list.dataset.clipOrderAxis,horizontal?'horizontal':'vertical');
  const input=(type,x)=>{
    const host=type==='blur'?window:['pointerup','pointercancel','keydown'].includes(type)?document:list;
    host.dispatchEvent({type,isPrimary:true,button:0,pointerId:1,target:items[2],clientX:x,clientY:10,key:'Escape'});
  };
  for(const event of ['pointercancel','lostpointercapture','keydown','blur']){
    input('pointerdown',200);input('pointermove',202);
    assert.equal(document.body.children.length,0);
    input('pointermove',100);
    const preview=document.body.children[0];
    assert.equal(preview.attributes['aria-hidden'],'true');
    assert.deepEqual(preview.children.map(line=>line.textContent),['다','00:15']);
    assert.ok(items[2].classList.has('clip-order-source'));
    assert.ok(items[1].classList.has('clip-drop-target'));
    const previousPosition=preview.style.transform;
    input('pointermove',0);
    assert.deepEqual(document.body.children,[preview]);
    assert.notEqual(preview.style.transform,previousPosition);
    assert.ok(items[0].classList.has('clip-drop-target'));
    assert.equal(items[1].classList.size,0);
    input(event,0);
    assert.equal(items[2].captured,false);
    assert.equal(document.body.children.length,0);
    assert.ok(items.every(row=>!row.classList.size));
  }
  input('pointerdown',200);input('pointermove',202);input('pointerup',202);
  input('pointerdown',200);input('pointermove',300);input('pointerup',300);
  assert.deepEqual(moves,[]);
  input('pointerdown',200);input('pointermove',0);input('pointerup',0);
  assert.deepEqual(moves,[['다',0]]);
  assert.equal(document.body.children.length,0);
  assert.ok(items.every(row=>!row.classList.size));
});
