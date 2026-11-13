import test from 'node:test';
import assert from 'node:assert/strict';
import {connectDeletion} from '../web/project-delete.js';

function setup(){
 const elements=new Map();const $=id=>{if(!elements.has(id))elements.set(id,{id,value:'',disabled:false,open:false,listeners:{},focus(){},showModal(){this.open=true;},close(){this.open=false;for(const fn of this.listeners.close||[])fn();},addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}});return elements.get(id);};
 globalThis.document={getElementById:$};
 const selected={root:'/fake/active',path:'/fake/active/vod-1',vod_id:'1',metadata:{title:'작업 중인 다른 VOD'}};
 const target={root:'/fake/library',path:'/fake/library/vod-9',vod_id:'9',metadata:{title:'삭제 요청 대상'}};
 const calls=[],promises=[],removed=[];let current=selected;
 const controller=connectDeletion({getProject:()=>current,onDeleted:entry=>removed.push(entry),api:async(action,data)=>{calls.push([action,data]);if(action==='delete-preview')return new Promise(resolve=>promises.push(resolve));assert.equal(action,'delete-project');return {};}});
 const preview={vod_id:'9',path:target.path,title:'삭제 요청 대상',bytes:1024,token:'fake-token'};
 return {$,controller,target,selected,calls,promises,removed,preview,select:value=>current=value};
}

test('보관함 행의 삭제 모달은 현재 열린 VOD와 별개로 요청한 대상만 삭제한다',async()=>{
 const f=setup(),opening=f.controller.open(f.target);assert.equal(f.$('delete-dialog').open,true);assert.equal(f.$('delete-confirm').disabled,true);
 f.promises.shift()(f.preview);await opening;assert.equal(f.removed.length,0);
 f.$('delete-confirmation').value='9';f.$('delete-confirmation').oninput();assert.equal(f.$('delete-confirm').disabled,false);
 await f.$('delete-form').onsubmit({preventDefault(){}});
 assert.equal(f.removed.length,1);assert.equal(f.removed[0].path,f.target.path);
 assert.deepEqual(f.calls[1],['delete-project',{root:f.target.root,vod_id:'9',token:'fake-token',confirmation:'9'}]);
});

test('취소한 모달의 늦은 응답과 이전 행의 응답은 삭제 대상을 바꾸지 못한다',async()=>{
 const f=setup(),first=f.controller.open(f.target);f.$('delete-cancel').onclick();f.promises.shift()(f.preview);await first;assert.equal(f.$('delete-dialog').open,false);
 const old=f.controller.open(f.target),other={...f.target,vod_id:'10',path:'/fake/library/vod-10'},next=f.controller.open(other);
 const [resolveOld,resolveNew]=f.promises;resolveNew({...f.preview,vod_id:'10',path:other.path,token:'next-token'});await next;resolveOld(f.preview);await old;
 f.$('delete-confirmation').value='10';await f.$('delete-form').onsubmit({preventDefault(){}});
 assert.equal(f.calls.at(-1)[1].token,'next-token');assert.equal(f.removed[0].path,other.path);
});

test('서버 미리보기 대상 불일치나 확인 번호 불일치는 삭제 요청을 보내지 않는다',async()=>{
 const f=setup(),opening=f.controller.open(f.target);f.promises.shift()({...f.preview,path:'/fake/other/vod-9'});await opening;
 assert.equal(f.$('delete-confirm').disabled,true);assert.match(f.$('delete-error').textContent,/대상이 바뀌/);
 await f.$('delete-form').onsubmit({preventDefault(){}});assert.equal(f.calls.length,1);
 const retry=f.controller.open(f.target);f.promises.shift()(f.preview);await retry;f.$('delete-confirmation').value='1';await f.$('delete-form').onsubmit({preventDefault(){}});assert.equal(f.calls.length,2);
});

test('기존 선택 VOD 삭제 진입은 작업 대상이 바뀌면 계속 차단한다',async()=>{
 const f=setup();f.select(f.target);const opening=f.$('delete-project').onclick();f.promises.shift()(f.preview);await opening;
 f.$('delete-confirmation').value='9';f.select(f.selected);await f.$('delete-form').onsubmit({preventDefault(){}});assert.equal(f.calls.length,1);assert.match(f.$('delete-error').textContent,/선택한 VOD가 바뀌/);
});
