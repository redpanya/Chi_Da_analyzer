export class Element{
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.style={};this.attributes={};this.listeners={};this.value='';this.textContent='';this.classList={toggle(){}};}
  append(...nodes){for(const n of nodes){this.children.push(n);n.parentElement=this;}}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  before(...nodes){this.beforeNodes=nodes;}after(...nodes){this.afterNodes=nodes;}
  setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,fn){(this.listeners[k]||=[]).push(fn);}
  dispatchEvent(e){for(const fn of this.listeners[e.type]||[])fn(e);}
  querySelectorAll(tag){return this.children.flatMap(c=>[...(c.tagName===tag.toUpperCase()?[c]:[]),...c.querySelectorAll(tag)]);}
  querySelector(selector){return selector==='.inspector-body'?this.body:this.querySelectorAll(selector)[0]||null;}
  showModal(){this.open=true;}close(){this.open=false;}scrollIntoView(){this.scrolled=true;}
  get selectedOptions(){return [{textContent:this.value}];}
}
export function dom(){const nodes=new Map(),document=new Element('document');document.body=new Element('body');document.createElement=tag=>new Element(tag);document.getElementById=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};globalThis.document=document;return id=>document.getElementById(id);}
