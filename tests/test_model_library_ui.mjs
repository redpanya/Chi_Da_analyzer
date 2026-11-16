import assert from 'node:assert/strict';
import {createModelLibrary} from '../web/model-library.js';

class Element {
  children = [];
  attributes = {};
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(key, value) { this.attributes[key] = value; }
  getClientRects() { return [{}]; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}
const elements = new Map();
const el = id => {
  if (!elements.has(id)) elements.set(id, new Element());
  return elements.get(id);
};
globalThis.document = {getElementById: el, createElement: () => new Element()};

let root = '/models';
const item = {id:'whisper', label:'Whisper large-v3-turbo-q5_0', type:'model', supported:true};
const requiredWhisper = '(필수) Whisper large-v3-turbo-q5_0';
let otherItems = [];
let ready = false;
let job = {state:'idle'};
const calls = [];
const library = createModelLibrary(async (name, data) => {
  assert.equal(name, 'model-library');
  if (data.action) {
    calls.push(data);
    assert.equal(data.root, root);
    assert.equal(data.id, item.id);
    if (data.action === 'install') job = {state:'running', id:item.id, action:'install', progress:{bytes:1024,total_bytes:65536}};
    if (data.action === 'cancel') { ready = true; job = {state:'complete'}; } // 설치가 중단 요청 직전에 완료된 경우
    if (data.action === 'delete') { ready = false; job = {state:'complete'}; }
  }
  return {root, items:[...otherItems, {...item, ready, present:ready, can_install:!ready, can_delete:ready}], job};
});
const sections = () => el('model-library-items').children;
const rows = section => section.children[1].children;
const rowName = row => row.children[0].children[0].textContent;
const action = () => rows(sections()[0]).find(row => rowName(row) === requiredWhisper).children[1].children[0];
library.rootChanged(root);
await library.refresh();
assert.deepEqual(sections().map(section => section.children[0].textContent), ['음성 전사']);
assert.equal(action().attributes['aria-label'], requiredWhisper + ' 설치');
await action().onclick();
assert.deepEqual(calls.at(-1), {action:'install', id:'whisper', root:'/models'});
assert.match(el('model-library-notice').textContent, /1 KiB \/ 64 KiB/);
assert.equal(action().textContent, '중단');
await action().onclick();
assert.equal(action().textContent, '삭제');
assert.equal(action().attributes['aria-label'], requiredWhisper + ' 삭제');
action().onclick();
assert.equal(el('model-delete-dialog').open, true);
el('model-delete-cancel').onclick();
assert.equal(calls.length, 2);
action().onclick();
root = '/new-models';
library.rootChanged(root);
assert.equal(el('model-delete-dialog').open, false);
await el('model-delete-confirm').onclick();
assert.equal(calls.length, 2);
await library.refresh();
action().onclick();
await el('model-delete-confirm').onclick();
assert.deepEqual(calls.at(-1), {action:'delete', id:'whisper', root:'/new-models'});
assert.equal(action().textContent, '설치');

const oldModel = 'legacy-qwen3.5-4b-q4_k_m';
const categories = {
  '음성 전사': ['whisper', 'vad'],
  '화자 구분': ['sherpa', 'tool-sherpa', 'pyannote', 'tool-pyannote', 'fluid', 'tool-fluid'],
  'AI 문맥 분석': ['gemma', oldModel]
};
otherItems = Object.values(categories).flat().filter(id => id !== item.id).map(id => ({
  id, label:id, type:id.startsWith('tool-') ? 'tool' : 'model', supported:true,
  ready:id === oldModel, present:id === oldModel, can_delete:id === oldModel, can_install:id !== oldModel
}));
root = '/mixed-models';
library.rootChanged(root);
await library.refresh();
assert.deepEqual(sections().map(section => section.children[0].textContent), Object.keys(categories));
for (const section of sections()) {
  const name = section.children[0].textContent;
  const groupRows = rows(section);
  const expectedLabels = {whisper:requiredWhisper, gemma:'(필수) gemma'};
  assert.deepEqual(groupRows.map(rowName).sort(), categories[name].map(id => expectedLabels[id] || id).sort());
  for (const row of groupRows) {
    const [, description, status] = row.children[0].children;
    assert.ok(description.textContent.trim(), rowName(row));
    assert.match(status.textContent, /설치됨|미설치/);
    if (rowName(row) === '(필수) gemma') assert.equal(row.children[1].children[0].attributes['aria-label'], '(필수) gemma 설치');
    if (rowName(row) === 'tool-sherpa') assert.match(description.textContent, /발화 검출/);
    if (rowName(row) === oldModel) assert.deepEqual(row.children[1].children.map(button => button.textContent), ['삭제']);
  }
}
