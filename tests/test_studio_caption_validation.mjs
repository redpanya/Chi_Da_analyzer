import assert from 'node:assert/strict';
import {studioDecorations} from '../web/studio-decorations.js';
class El extends EventTarget{
  constructor(){super();this.value='';this.textContent='';this.children=[];this.dataset={};this.style={};this.classList={toggle(){},remove(){}};this.width=660;this.height=180;this.open=false;}
  append(...rows){this.children.push(...rows);}replaceChildren(...rows){this.children=rows;}setAttribute(){}get options(){return this.children;}
  getContext(){return {clearRect(){},drawImage(){}};}
}
const nodes=new Map(),$=id=>{if(!nodes.has(id))nodes.set(id,new El());return nodes.get(id);};
globalThis.document=new EventTarget();document.getElementById=$;document.createElement=()=>new El();
globalThis.window=new EventTarget();globalThis.Option=class extends El{constructor(label,value){super();this.textContent=label;this.value=value;}};
globalThis.ResizeObserver=class{observe(){}};globalThis.MutationObserver=class{observe(){}};
globalThis.createImageBitmap=async()=>({width:660,height:180,close(){}});
for(const id of ['image-x','image-y','image-width','image-opacity'])$(id).value='50';
$('caption-text').textContent='안녕 하세요';$('caption-version').value='transcript';
$('inspector-font').hidden=true;$('panel-caption').hidden=true;
let enabled=true,changed=0,pending=[];
const options=()=>({caption:enabled,sidecar:false,font:$('caption-font').value,caption_language:'ko',ratio:'original',size:'source',image:null,style:'soft',font_size:32});
const api=async(action,data)=>{
  if(action==='studio-fonts')return {fonts:[{id:'a',label:'A',languages:['ko'],full_korean:true},{id:'b',label:'B',languages:['ko'],full_korean:true}],languages:{ko:{sample:'한글 예시 123'}}};
  assert.equal(action,'studio-decoration-preview');return new Promise((resolve,reject)=>pending.push({data,resolve,reject}));
};
const ui=studioDecorations({api,identity:()=>({}),video:Object.assign(new El(),{videoWidth:640,videoHeight:360}),read:options,onChange:()=>changed++});
const tick=()=>new Promise(r=>setTimeout(r,125)),flush=()=>new Promise(r=>setImmediate(r));
const settle=async(rows,fail=false)=>{for(const r of rows)fail?r.reject(new Error('검사 실패')):r.resolve({png:'AA=='});await flush();};
await ui.init({font:'a'});assert.equal(ui.blocked(),true);await tick();assert.equal(pending.length,2);
await settle(pending.splice(0));assert.equal(ui.blocked(),false);assert.match($('decoration-state').textContent,/문장 렌더링 확인 완료/);
// 새 설정은 응답 전부터 막고, 실패해도 기존 선택은 지우지 않는다.
$('caption-font').value='b';document.dispatchEvent(new Event('change'));assert.equal(ui.blocked(),true);await tick();
await settle(pending.splice(0),true);assert.equal(ui.blocked(),true);assert.equal($('caption-font').value,'b');
enabled=false;assert.equal(ui.blocked(),false);enabled=true;
// A -> B -> A로 빠르게 변경해도 이전 A 응답으로 최신 검사를 통과시키지 않는다.
for(const font of ['a','b','a']){$('caption-font').value=font;document.dispatchEvent(new Event('change'));await tick();}
assert.equal(pending.length,6);await settle(pending.splice(0,4));assert.equal(ui.blocked(),true);
await settle(pending.splice(0));assert.equal(ui.blocked(),false);assert.ok(changed>4);
window.dispatchEvent(new Event('pagehide'));
console.log('실제 자막 검사 대기·실패 차단, 자막 해제, 빠른 글꼴 변경의 오래된 응답 무시 검사 통과');
