import test from 'node:test';
import assert from 'node:assert/strict';
import {fitPanelWidths} from '../web/desktop-panels.js';
import {createEditUndo,captureProfileOptions} from '../web/studio-edit-undo.js';
import {profileState} from '../web/studio-profiles.js';
import {sourcePage} from '../web/studio-source-pages.js';

test('패널은 작은 데스크톱에서도 최소 폭을 지키고 중앙을 남은 폭으로 배치',()=>{
  const min=[210,360,280],sizes=fitPanelWidths([260,520,320],1004,min);
  assert.equal(sizes.reduce((a,b)=>a+b,0),1004);
  sizes.forEach((size,i)=>assert.ok(size>=min[i]));
  const wide=fitPanelWidths([260,520,320],1738,min);
  assert.deepEqual(wide,[260,1158,320]);
  const corrupt=fitPanelWidths([null,'bad',1e9],1004,min);
  assert.equal(corrupt.reduce((a,b)=>a+b,0),1004);corrupt.forEach((n,i)=>assert.ok(n>=min[i]));
  assert.deepEqual(fitPanelWidths([300,450],500,[340,300],0),[340,300]);
});
test('프리셋 되돌리기는 상속 여부와 PNG 개별 배치까지 복원하고 다른 구간을 유지',()=>{
  const base={ratio:'16:9',image:{asset:'png',x:20,y:30}},model=profileState(base);
  const a={id:'a'},b={id:'b',options:{ratio:'1:1',image:{asset:'png',x:60,y:10}}},other={id:'c',options:{ratio:'9:16'}};
  const before=structuredClone([a,b,other]),restore=captureProfileOptions([a,b]);
  const states=[],undo=createEditUndo(label=>states.push(label));
  model.apply([a,b],{ratio:'9:16'});undo.record('프리셋 적용',restore);
  assert.equal(b.options.image.x,60);assert.equal(undo.undo(),true);assert.deepEqual([a,b,other],before);
  assert.equal(undo.undo(),false);assert.deepEqual(states,['프리셋 적용','']);
});
test('마지막 한 단계만 복구하고 공통 복귀도 사본으로 되돌림',()=>{
  const a={options:{game:[10,20,30,40]}},restore=captureProfileOptions([a]),undo=createEditUndo();
  undo.record('이전',()=>assert.fail('덮인 작업은 실행되면 안 됨'));
  delete a.options;undo.record('공통 복귀',restore);undo.undo();assert.deepEqual(a.options.game,[10,20,30,40]);
  a.options.game[0]=99;restore();assert.equal(a.options.game[0],10);
});
test('500개 넘는 구간은 50개씩 중복·누락 없이 탐색하고 현재 구간 페이지로 이동',()=>{
  const rows=Array.from({length:555},(_,i)=>({id:String(i),title:'구간 '+i}));
  const pages=Array.from({length:12},(_,i)=>sourcePage(rows,i));
  assert.equal(pages[11].rows.length,5);assert.deepEqual(pages.flatMap(page=>page.rows),rows);
  assert.equal(sourcePage(rows,0,50,'503').page,10);
  assert.equal(sourcePage(rows.slice(0,1),11).page,0);
  assert.deepEqual(sourcePage([],20),{page:0,pages:1,total:0,rows:[]});
});
