import assert from 'node:assert/strict';
import {createMiniPlayer} from '../web/mini-player.js';

let focused = null;
class Node {
  constructor(tag) { this.tagName=tag; this.children=[]; this.events={}; this.isConnected=true; }
  append(...items) { for (const item of items) { item.remove(); this.children.push(item); item.parentElement=this; } }
  remove() { if (this.parentElement) this.parentElement.children=this.parentElement.children.filter(n=>n!==this); this.parentElement=null; }
  before(item) { item.remove(); const p=this.parentElement; p.children.splice(p.children.indexOf(this),0,item); item.parentElement=p; }
  replaceWith(item) { this.before(item); this.remove(); }
  setAttribute() {} addEventListener(name,fn) { this.events[name]=fn; }
  focus(options) { focused=this; this.focusOptions=options; } getClientRects() { return [{}]; }
}
const body=new Node('body'), home=new Node('div'), nodes=new Map();
for (const id of ['video-result','video-unready']) {const node=new Node('div');node.id=id;nodes.set(id,node);home.append(node);}
body.append(home);
const original=[...home.children], audio={paused:false,pause(){this.paused=true;}};
globalThis.document={body,createElement:tag=>new Node(tag),createComment:()=>new Node('comment'),getElementById:id=>nodes.get(id),querySelectorAll:()=>[audio]};
const seeks=[],modes=[];let resets=0,explored=null;
const view=createMiniPlayer({player:{reset(){resets++;},previewMode(value){modes.push(value);},seek(...args){seeks.push(args);}},onExplore:row=>explored=row});
const panel=body.children.at(-1),[header,caption,media,openExplore]=panel.children,close=header.children[1];
const opener=new Node('button'),row={start_ms:1000,end_ms:4000,text:'선택한 대사'};
view.setProject({path:'/vod-1'});view.open(row,opener);
assert.equal(panel.hidden,false);assert.deepEqual(media.children,original);assert.equal(audio.paused,true);
assert.deepEqual(seeks.at(-1),[1000,true,4000]);assert.equal(focused,close);assert.match(caption.textContent,/00:00:01 ~ 00:00:04/);
const slots=[...home.children];view.open({...row,start_ms:2000},opener);assert.deepEqual(home.children,slots);assert.equal(media.children.length,2);
view.setProject({path:'/vod-1'});assert.equal(panel.hidden,false); // 폴링은 닫지 않는다.
panel.events.keydown({key:'Escape',preventDefault(){},stopPropagation(){}});
assert.equal(panel.hidden,true);assert.deepEqual(home.children,original);assert.equal(resets,1);assert.equal(focused,opener);assert.deepEqual(opener.focusOptions,{preventScroll:true});
view.open(row,opener);openExplore.onclick();assert.equal(explored,row);assert.equal(panel.hidden,true);assert.deepEqual(home.children,original);
view.open(row,opener);view.setProject({path:'/vod-2'});assert.equal(panel.hidden,true);assert.deepEqual(home.children,original);
view.open(row,opener);view.close(false);assert.equal(panel.hidden,true);assert.deepEqual(home.children,original);
const count=seeks.length;view.open({start_ms:NaN},opener);assert.equal(seeks.length,count);assert.equal(panel.hidden,true);
assert.equal(modes.at(-1),false);
console.log('단일 재생기 이동·반복 선택·기존 음성 중단·구간 재생·폴링 유지·닫기/초점 복귀·페이지/VOD 전환 복원 통과');
