import assert from 'node:assert/strict';
import {createCaptionDesign} from '../web/studio-caption-design.js';
const base={text_color:'#ffffff',outline:true,outline_color:'#000000',outline_width:2,shadow:false,shadow_color:'#000000',shadow_opacity:70,shadow_blur:2,shadow_x:1,shadow_y:2,box:false,box_color:'#101010',box_opacity:86,box_padding:6};
const bounds={outline_width:[0,8],shadow_opacity:[0,100],shadow_blur:[0,8],shadow_x:[-10,10],shadow_y:[-10,10],box_opacity:[0,100],box_padding:[0,24]};
class Field extends EventTarget{
  constructor(key,value){super();this.dataset={design:key};this.type=typeof value==='boolean'?'checkbox':typeof value==='number'?'number':'color';this.value=value;this.checked=value;}
  set value(v){this.raw=String(v);}get value(){return this.raw;}
  get valueAsNumber(){return this.raw.trim()?Number(this.raw):NaN;}
  get validity(){const n=this.valueAsNumber,b=bounds[this.dataset.design];return {valid:!b||(Number.isFinite(n)&&n>=b[0]&&n<=b[1])};}
}
globalThis.Option=class{constructor(label,value){this.textContent=label;this.value=value;this.dataset={};}remove(){select.options=select.options.filter(o=>o!==this);}};
const fields=Object.entries(base).map(([k,v])=>new Field(k,v)),nodes=new Map();
const host={querySelectorAll:()=>fields,querySelector:key=>{if(!nodes.has(key))nodes.set(key,{});return nodes.get(key);}};
const select=new EventTarget();select.value='basic';select.options=[new Option('기본 자막','basic'),new Option('박스 자막','box')];select.append=o=>select.options.push(o);
const note={},error={},ui=createCaptionDesign(host,select,note,error),definitions={basic:base,box:{...base,box:true},point:{...base,text_color:'#ffb0b5',outline_color:'#cd515c'}};
const edit=(key,value)=>{const f=fields.find(f=>f.dataset.design===key);if(f.type==='checkbox')f.checked=value;else f.value=value;f.dispatchEvent(new Event('input'));};
ui.init(definitions,{style:'point'});assert.equal(select.value,'point');assert.equal(select.options.length,3);assert.equal(select.options[2].disabled,true);assert.equal(ui.read(),null);assert.match(note.textContent,/기존 자막 디자인/);
edit('text_color','#7947de');assert.equal(select.value,'basic');assert.equal(select.options.length,2);assert.equal(ui.read().text_color,'#7947de');assert.equal(ui.read().outline_color,'#cd515c');
edit('shadow',true);edit('shadow_x',-2.5);assert.equal(ui.read().shadow,true);assert.equal(ui.read().shadow_x,-2.5);
const previous=ui.read();edit('outline_width','');assert.equal(ui.valid(),false);assert.deepEqual(ui.read(),previous);assert.ok(error.textContent);
edit('outline_width',9);assert.equal(ui.valid(),false);edit('outline_width',0);assert.equal(ui.valid(),true);assert.equal(error.textContent,'');
const saved=ui.read();ui.init(definitions,{style:'basic',caption_design:saved});assert.deepEqual(ui.read(),saved);assert.notEqual(ui.read(),saved);
select.value='box';select.dispatchEvent(new Event('change'));assert.equal(ui.read(),null);assert.equal(fields.find(f=>f.dataset.design==='box').checked,true);assert.equal(fields.find(f=>f.dataset.design==='text_color').value,'#ffffff');
assert.equal(base.text_color,'#ffffff');assert.equal(definitions.point.text_color,'#ffb0b5');
const template={id:'a'.repeat(32),name:'내 디자인',style:'box',design:{...base,box:true,text_color:'#fe5069'}};
ui.templates([template]);select.value='template:'+template.id;select.dispatchEvent(new Event('input'));
assert.equal(ui.style(),'box');assert.deepEqual(ui.read(),template.design);select.dispatchEvent(new Event('change'));
assert.equal(ui.style(),'box');assert.deepEqual(ui.read(),template.design);assert.equal(ui.selected().id,template.id);assert.equal(ui.savable(),true);
edit('shadow_x',-3);assert.match(note.textContent,/맞춤 변경됨/);assert.equal(template.design.shadow_x,1);
const applied=ui.read();ui.templates([]);assert.equal(ui.selected(),undefined);assert.equal(ui.style(),'box');assert.deepEqual(ui.read(),applied);
assert.equal(select.options.length,2);assert.equal(ui.snapshot().text_color,'#fe5069');
ui.templates([template],template.id);assert.deepEqual(ui.read(),template.design);
select.value='basic';select.dispatchEvent(new Event('change'));assert.equal(ui.selected(),undefined);assert.equal(ui.read(),null);assert.deepEqual(ui.snapshot(),base);
ui.init(definitions,{style:'point'});assert.equal(ui.savable(),false);assert.equal(ui.style(),'point');assert.equal(ui.read(),null);
edit('text_color','#7947de');assert.equal(ui.savable(),true);edit('shadow_x','');assert.equal(ui.savable(),false);
console.log('맞춤 자막: 기존 디자인 유지·명시적 전환·옵션 편집·잘못된 값 차단·초안 복원·템플릿 재선택 검사 통과');
