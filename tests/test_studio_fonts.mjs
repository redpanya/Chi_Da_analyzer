import assert from 'node:assert/strict';
import {matchingFonts,studioFonts} from '../web/studio-fonts-ui.js';
import {dom,Element} from './polish_dom.mjs';
const fonts=[{id:'a',label:'Korean Regular',languages:['ko','en']},{id:'b',label:'English Bold',languages:['en']},{id:'c',label:'Japanese',languages:['ja']}];
const before=JSON.stringify(fonts);
assert.deepEqual(matchingFonts(fonts,'ko').map(f=>f.id),['a']);
assert.deepEqual(matchingFonts(fonts,'en','  BOLD ').map(f=>f.id),['b']);
assert.deepEqual(matchingFonts(fonts,'ko','English'),[]);
assert.deepEqual(matchingFonts(fonts,'zh-CN'),[]);
assert.equal(JSON.stringify(fonts),before);
console.log('언어별 글꼴 필터·이름 검색·빈 목록·원본 불변 검사 통과');

const {fontFamilies,chooseFace}=await import('../web/studio-fonts-ui.js');
const familyFaces=[
 {id:'light',family_id:'same',family_name:'예시',label:'예시 Light',style:'Light',weight:300,languages:['ko','en']},
 {id:'regular',family_id:'same',family_name:'예시',label:'예시 Regular',style:'Regular',weight:400,languages:['ko','en']},
 {id:'bold',family_id:'same',family_name:'예시',label:'예시 Bold',style:'Bold',weight:700,languages:['en']},
 {id:'copy',family_id:'same',family_name:'예시',label:'예시 Regular',style:'Regular',weight:400,languages:['ko','en']},
 {id:'other',family_id:'other-vendor',family_name:'예시',label:'예시 Regular',style:'Regular',weight:400,languages:['ko','en']}
];
assert.equal(fontFamilies(familyFaces,'ko').length,2);
assert.deepEqual(fontFamilies(familyFaces,'ko')[0].faces.map(f=>f.id),['light','regular','copy']);
assert.equal(fontFamilies(familyFaces,'en','Bold')[0].faces.length,4);
assert.equal(chooseFace(familyFaces.slice(0,3)).id,'regular');
assert.equal(chooseFace(familyFaces.slice(0,3),{weight:700}).id,'bold');
assert.equal(chooseFace(familyFaces.slice(0,4),familyFaces[3]).id,'copy');
assert.equal(fontFamilies(familyFaces,'ko','찾을 수 없음').length,0);
console.log('계열 묶음·변형별 언어 필터·중복 ID 보존·굵기 선택 검사 통과');

const $=dom();
globalThis.window=new EventTarget();
globalThis.Option=class extends Element {
  constructor(label,value){super('option');this.textContent=label;this.value=value;}
};
const panel=$('panel-caption'), list=$('font-preview-list');
panel.hidden=true;
list.closest=selector=>{
  assert.equal(selector,'[hidden]');
  return panel.hidden?panel:null;
};
const catalog=Array.from({length:10},(_,i)=>({id:'font'+i,label:'글꼴 '+i,languages:['ko']}));
let requested=0;
const picker=studioFonts({identity:()=>({}),onChange(){},api:async name=>{
  if(name==='studio-fonts')return {fonts:catalog,languages:{}};
  assert.equal(name,'studio-decoration-preview');
  requested++;
  return new Promise(()=>{}); // 예시 이미지가 도착하기 전에도 카드는 선택할 수 있다.
}});
await picker.init();
assert.equal(requested,0);
panel.hidden=false;
document.dispatchEvent(new Event('studio-inspector-change'));
const families=()=>list.children.filter(node=>node.tagName==='BUTTON').map(node=>node.dataset.family);
assert.deepEqual(families(),['auto',...catalog.slice(0,8).map(face=>face.id)]);
$('font-next').onclick();
assert.deepEqual(families(),['auto','font8','font9']);
$('font-search').value='글꼴 2';
$('font-search').oninput();
assert.deepEqual(families(),['auto','font2']);
list.children[1].onclick();
assert.equal($('caption-font').value,'font2');
