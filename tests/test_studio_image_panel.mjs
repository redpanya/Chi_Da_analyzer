import assert from 'node:assert/strict';
import {studioImageEditor} from '../web/studio-image-editor.js';
let draws=0,requests=0;
class Element extends EventTarget {
  constructor(){super();this.children=[];this.style={};this.dataset={};this.classList={toggle(){},remove(){}};this.hidden=false;this.width=0;this.height=0;}
  setAttribute(){} append(...items){this.children.push(...items);}getContext(){return {clearRect(){},drawImage(){draws++;}};}
}
const nodes=new Map(),$=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
globalThis.document=new EventTarget();document.getElementById=$;document.createElement=()=>new Element();
globalThis.window=new EventTarget();globalThis.ResizeObserver=class{observe(){}};
globalThis.createImageBitmap=async()=>({close(){}});
const image={asset:'test',x:50,y:50,width:30,opacity:100},before=JSON.stringify(image);
const editor=studioImageEditor({api:async()=>{requests++;return {png:'AA==',width_px:100,height_px:100};},identity:()=>({}),read:()=>({image}),size:()=>[1920,1080],locked:()=>false,onChange(){}});
await editor.sync();const box=$('preview-frame').children[1];
assert.equal(box.hidden,true);assert.ok(draws>0);assert.equal(editor.blocked(),false);
const switchPanel=panel=>document.dispatchEvent(new CustomEvent('studio-inspector-change',{detail:{panel}}));
switchPanel('image');assert.equal(box.hidden,false);const openDraws=draws;
switchPanel('font');assert.equal(box.hidden,true);assert.ok(draws>openDraws);
switchPanel('');assert.equal(box.hidden,true);assert.equal(requests,1);assert.equal(JSON.stringify(image),before);
console.log('PNG 패널에서만 핸들 표시·닫은 뒤 합성 유지·추가 로딩 없음·원래 옵션 보존 검사 통과');
