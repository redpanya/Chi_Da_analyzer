import assert from 'node:assert/strict';
import {bindResultLayouts,moveResultTimeline} from '../web/results-layout.js';

class Element{
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.style={};this.attributes={};this.classes=new Set();this.classList={add:name=>this.classes.add(name),remove:name=>this.classes.delete(name)};this.clientWidth=1010;this.listeners={};}
  append(...children){for(const child of children){child.remove();this.children.push(child);child.parentElement=this;}}
  prepend(child){child.remove();this.children.unshift(child);child.parentElement=this;}
  after(child){child.remove();const at=this.parentElement.children.indexOf(this);this.parentElement.children.splice(at+1,0,child);child.parentElement=this.parentElement;}
  before(child){child.remove();const at=this.parentElement.children.indexOf(this);this.parentElement.children.splice(at,0,child);child.parentElement=this.parentElement;}
  getAttribute(key){return this.attributes[key];}setAttribute(key,value){this.attributes[key]=value;}
  querySelector(){return this.workspace;}addEventListener(type,fn){this.listeners[type]=fn;}dispatchEvent(event){this.lastEvent=event;this.listeners[event.type]?.(event);}
  focus(){}setPointerCapture(){}remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(child=>child!==this);this.parentElement=null;}
}
const nodes=new Map(),observers=[];
globalThis.document={cookie:'',createElement:tag=>new Element(tag),getElementById:id=>nodes.get(id)};
globalThis.localStorage={getItem(){return null;},setItem(){}};
globalThis.CustomEvent=class{constructor(type,options){this.type=type;Object.assign(this,options);}};
globalThis.ResizeObserver=class{constructor(fn){this.fn=fn;observers.push(this);}observe(){}disconnect(){}};
for(const id of ['context-view-panel','context-clips-panel']){
  const section=new Element(),workspace=new Element(),list=new Element(),preview=new Element();
  list.append(new Element('article'));preview.append(new Element('video'));workspace.append(list,preview);section.workspace=workspace;nodes.set(id,section);
}
const bindings=bindResultLayouts();await Promise.resolve();
const detailBox=nodes.get('context-view-panel').workspace,clipBox=nodes.get('context-clips-panel').workspace;
detailBox.children[1].children[0].onkeydown({key:'ArrowLeft',preventDefault(){}});
assert.equal(detailBox.style.gridTemplateColumns,'442px 10px 558px');
assert.equal(clipBox.style.gridTemplateColumns,detailBox.style.gridTemplateColumns);
const speech=new Element();speech.workspace=new Element();const speechList=new Element(),speechPreview=new Element();speechList.append(new Element('article'));speechPreview.append(new Element('video'));speech.workspace.append(speechList,speechPreview);nodes.set('speech-panel',speech);
bindResultLayouts();await Promise.resolve();
assert.equal(speech.workspace.style.gridTemplateColumns,detailBox.style.gridTemplateColumns);
speech.workspace.children[1].children[0].onkeydown({key:'ArrowRight',preventDefault(){}});
assert.equal(detailBox.style.gridTemplateColumns,'450px 10px 550px');
assert.equal(clipBox.style.gridTemplateColumns,detailBox.style.gridTemplateColumns);
bindResultLayouts();assert.equal(bindings.length,2);
for(const id of nodes.keys()){
  const box=nodes.get(id).workspace;assert.equal(box.children.length,3);assert.equal(box.children[1].className,'desktop-panel-gutter');
  assert.equal(box.children[0].children[0].tagName,'ARTICLE');assert.equal(box.children[2].children[0].tagName,'VIDEO');
  assert.equal(box.style.gridTemplateColumns,'450px 10px 550px');
  const separator=box.children[1].children[0];assert.equal(separator.attributes['aria-valuemin'],320);
}
bindResultLayouts();assert.equal(nodes.get('context-view-panel').workspace.children.length,3); // 다시 열어도 핸들을 중복 추가하지 않는다.
nodes.get('context-view-panel').workspace.clientWidth=640;observers[0].fn();
assert.equal(bindings[0].widths().reduce((a,b)=>a+b,0),630);assert.ok(bindings[0].widths()[0]>=320);assert.ok(bindings[0].widths()[1]>=300);
const original=new Element(),timeline=new Element(),notes=new Element(),error=new Element(),detail=new Element(),clips=new Element(),video1=new Element(),video2=new Element();
original.append(notes,error,timeline);detail.append(video1);clips.append(video2);timeline.zoom='2분';timeline.selection='candidate-a';
for(const [key,value] of Object.entries({'context-preview':detail,'context-clips-preview':clips,'context-video':video1,'context-clips-video':video2,'explore-notes':notes,'explore-message':error}))nodes.set(key,value);
document.querySelector=()=>timeline;
moveResultTimeline('context-preview');const panel=timeline.parentElement;assert.equal(panel.parentElement,detail);assert.equal(panel.children[0].tagName,'SUMMARY');assert.equal(notes.parentElement,panel);
const usage=new Element('section');detail.append(usage);moveResultTimeline('context-preview');assert.deepEqual(detail.children,[video1,usage,panel]);
panel.open=true;moveResultTimeline('context-clips-preview');assert.equal(timeline.parentElement,panel);assert.equal(panel.parentElement,clips);assert.equal(panel.open,true);
clips.append(usage);moveResultTimeline('context-clips-preview');assert.deepEqual(clips.children,[video2,usage,panel]);
moveResultTimeline();assert.equal(timeline.parentElement,original);assert.equal(notes.parentElement,original);assert.equal(error.parentElement,original);assert.equal(timeline.zoom,'2분');assert.equal(timeline.selection,'candidate-a');
moveResultTimeline('context-preview');assert.equal(timeline.parentElement,panel);assert.equal(panel.open,true);
console.log('장면 탐색 공유 두 열 폭과 늦게 열린 전사 연결·키보드·최소 폭·중복 방지·영상/목록 노드 보존 검사 통과');
