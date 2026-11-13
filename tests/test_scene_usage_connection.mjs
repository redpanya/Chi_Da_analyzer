import assert from 'node:assert/strict';
import {createSceneUsage} from '../web/scene-usage.js';

// 기존 가상 DOM의 ID map은 분리된 노드도 반환했다. 여기서는 실제 document처럼
// 연결된 body 트리에서만 ID를 찾아 첫 setItems 호출 시의 분리 오류를 재현한다.
class Element{
  constructor(tag='div'){this.tagName=tag;this.children=[];this.attributes={};}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(node=>node!==this);this.parentElement=null;}
  append(...nodes){for(const node of nodes){node.remove();this.children.push(node);node.parentElement=this;}}
  before(node){if(!this.parentElement)return;node.remove();const parent=this.parentElement;parent.children.splice(parent.children.indexOf(this),0,node);node.parentElement=parent;}
  replaceChildren(...nodes){for(const node of [...this.children])node.remove();this.append(...nodes);}
  setAttribute(key,value){this.attributes[key]=value;}
}
const body=new Element('body');
const find=(node,id)=>node.id===id?node:node.children.map(child=>find(child,id)).find(Boolean)||null;
globalThis.document={body,createElement:tag=>new Element(tag),getElementById:id=>find(body,id)};
const original=new Element(),otherTab=new Element(),comments=new Element(),fallback=new Element('textarea');
comments.id='context-comment-panel';fallback.id='context-copy-fallback';fallback.value='작성 중 댓글';
comments.append(fallback);original.append(comments);body.append(original,otherTab);

const detached=new Element();detached.append(comments);
assert.equal(document.getElementById('context-copy-fallback'),null);
assert.throws(()=>{document.getElementById('context-copy-fallback').hidden=true;},TypeError);
original.append(comments);

const usage=createSceneUsage({api:async()=>({draft:null}),player:{seek(){}},comments,onOpenEditor(){}});
// mount와 setProject보다 앞서 기존 context-copy.setItems가 ID를 조회한다.
assert.equal(document.getElementById('context-copy-fallback'),fallback);
document.getElementById('context-copy-fallback').hidden=true;
usage.setProject({path:'/vod-1',root:'/saved',vod_id:'1'});
usage.mount(otherTab);assert.equal(document.getElementById('context-copy-fallback'),fallback);
usage.mount(original);assert.equal(document.getElementById('context-comment-panel'),comments);
assert.equal(fallback.value,'작성 중 댓글');assert.equal(body.children.length,2);
console.log('댓글 초기 배치: 분리 노드 ID 조회 오류 재현·mount 전 연결·탭 이동·작성 중 내용 보존 통과');
