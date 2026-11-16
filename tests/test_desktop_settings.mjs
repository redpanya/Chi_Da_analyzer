import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {bindDesktopSettings} from '../web/desktop-settings.js';

const html = await readFile(new URL('../web/index.html', import.meta.url), 'utf8');
function settingsFixture() {
  const fields = new Map();
  for (const [id] of [...html.matchAll(/id="(?:desktop-[\w-]+|web-[\w-]+)"/g)]) {
    const selector = '#' + id.slice(4, -1);
    fields.set(selector, {
      textContent: '', hidden: true, removeAttribute(name) {delete this[name];}
    });
  }
  return {querySelector: key => fields.get(key)};
}
const settle = () => new Promise(done => setImmediate(done));

test('브라우저에는 데스크톱 명령과 폴링을 연결하지 않는다', () => {
  const panel = settingsFixture();
  const change = bindDesktopSettings(panel, undefined);
  change(true);
  assert.equal(panel.querySelector('#desktop-update').hidden, true);
  assert.equal(panel.querySelector('#desktop-licenses').onclick, undefined);
  assert.match(html, /네이버 및 치지직과 제휴 관계가 없습니다/);
  assert.match(html, /id="desktop-update" hidden/);
});

test('플랫폼별 업데이트 단계 및 설정에서 나갈 때의 폴링', async () => {
  const panel = settingsFixture(), calls = [], events = new Map();
  const field = suffix => panel.querySelector('#desktop-update-' + suffix);
  let state = {phase:'idle', platform:'darwin', currentVersion:'1.2.0'}, reads = 0;
  const bridge = {state:async () => {reads++; return state;}};
  for (const action of ['check','download','cancel','reveal','apply','notices']) {
    bridge[action] = async () => {calls.push(action);};
  }
  globalThis.window = globalThis.document = {addEventListener:(name, fn) => events.set(name, fn)};
  const change = bindDesktopSettings(panel, bridge);
  const show = async next => {change(false);Object.assign(state, next);change(true);await settle();};
  try {
    assert.equal(reads, 0);
    await show({});
    assert.equal(field('version').textContent, '현재 버전 1.2.0');
    assert.match(field('guide').textContent, /DMG/);
    assert.equal(field('check').hidden, false);
    for(const action of ['download','apply','cancel','reveal']) assert.equal(field(action).hidden,true);
    await field('check').onclick();
    await show({phase:'available',version:'1.3.0'});
    assert.match(field('version').textContent, /1\.3\.0/);
    assert.equal(field('download').textContent, 'DMG 다운로드');
    await field('download').onclick();
    await show({phase:'downloading',received:75,size:100});
    assert.equal(field('progress').value,75);
    assert.match(field('status').textContent,/75%/);
    assert.equal(field('cancel').hidden,false);
    await field('cancel').onclick();
    await show({phase:'downloaded'});
    assert.equal(field('reveal').hidden, false);
    assert.equal(field('apply').hidden, true);
    await field('reveal').onclick();
    await show({phase:'ready',platform:'win32'});
    assert.match(field('guide').textContent,/재실행/);
    assert.equal(field('apply').hidden, false);
    assert.equal(field('reveal').hidden, true);
    await field('apply').onclick();
    await panel.querySelector('#desktop-licenses').onclick();
    assert.deepEqual(calls,['check','download','cancel','reveal','apply','notices']);
    await show({phase:'error',message:'검증 실패'});
    assert.equal(field('status').textContent,'검증 실패');
    assert.equal(field('check').hidden,false);
    events.get('pagehide')();
    let last = reads;
    change(true); await settle();
    assert.equal(reads,last);
    events.get('pageshow')();await settle();
    assert.equal(reads,last+1);
    change(false); last = reads;
    events.get('visibilitychange')(); await settle();
    assert.equal(reads,last);
  } finally {change(false);delete globalThis.window;delete globalThis.document;}
});
