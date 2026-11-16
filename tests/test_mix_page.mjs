import assert from 'node:assert/strict';
import {createMixPage} from '../web/mix-clips.js';
import {dom} from './polish_dom.mjs';

const $=dom(),list=$('mix-list'),requests=[];
$('mix-page').hidden=true;
$('mix-editor-open').removeAttribute=key=>delete $('mix-editor-open')[key];
let root='A';
const page=createMixPage({getRoot:()=>root,api:()=>new Promise((resolve,reject)=>requests.push({resolve,reject}))});
const draft=title=>({items:[{key:'r',title,start_ms:0,end_ms:1000}],job:{state:'idle'}});

let shown=page.show(true);
requests.shift().resolve({...draft('원래 제목'),job:{state:'complete',file:'믹스.mp4'}});await shown;
const first=list.children[0];
page.show(false);shown=page.show(true);
assert.equal(list.children[0],first);assert.equal($('mix-clear').disabled,true);
assert.equal($('mix-result').hidden,false);assert.equal($('mix-open-folder').disabled,true);
requests.shift().resolve(draft('갱신한 제목'));await shown;
assert.equal(list.querySelector('strong').textContent,'1. 갱신한 제목');assert.equal($('mix-clear').disabled,false);

page.show(false);shown=page.show(true);
root='B';const other=page.show(true);
assert.equal(list.children.length,0);
requests.shift().resolve(draft('이전 보관함'));await shown;
assert.equal(list.children.length,0);assert.equal($('mix-clear').disabled,true);
requests.shift().resolve(draft('다른 보관함'));await other;
assert.equal(list.querySelector('strong').textContent,'1. 다른 보관함');

page.show(false);shown=page.show(true);
requests.shift().reject(new Error('폴더 연결 실패'));await shown;
assert.equal(list.children.length,0);assert.equal($('mix-save').disabled,true);
assert.equal($('mix-status').textContent,'폴더 연결 실패');
