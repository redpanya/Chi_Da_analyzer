import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const code = fs.readFileSync(new URL('../web/theme.js', import.meta.url), 'utf8');
class Events {
  constructor() { this.events = new Map(); }
  addEventListener(name, fn) { if (!this.events.has(name)) this.events.set(name, new Set()); this.events.get(name).add(fn); }
  removeEventListener(name, fn) { this.events.get(name)?.delete(fn); }
  dispatchEvent(event) { for (const fn of this.events.get(event.type) || []) fn(event); }
}
function setup({cookie='',storage=null,dark=false,blocked=false,cookieReadOnly=false}={}) {
  const document = new Events(), window = new Events(), media = new Events();
  const classes = new Set(); let savedCookie = cookie, stored = storage;
  document.documentElement = {dataset:{},classList:{toggle(name, value) {value ? classes.add(name) : classes.delete(name);}}};
  Object.defineProperty(document,'cookie',{get(){if(blocked)throw Error('denied');return savedCookie;},set(value){if(blocked)throw Error('denied');if(!cookieReadOnly)savedCookie=value.split(';')[0];}});
  window.localStorage = {getItem(){if(blocked)throw Error('denied');return stored;},setItem(k,v){if(blocked)throw Error('denied');stored=v;}};
  media.matches=dark;window.matchMedia=()=>media;
  vm.runInNewContext(code,{window,document,CustomEvent:class {constructor(type,options){this.type=type;Object.assign(this,options);}}});
  return {window,document,media,classes,theme:window.ChidaTheme, cookie:()=>savedCookie};
}
test('최초 기본은 다크이며 시스템 변화는 명시 선택을 덮지 않는다',()=>{
  const e=setup({dark:false});assert.equal(e.theme.getPreference(),'dark');assert.equal(e.theme.resolved(),'dark');assert(e.classes.has('wa-dark'));
  e.theme.setPreference('light'); e.media.matches=false;e.media.dispatchEvent({type:'change'});assert.equal(e.theme.resolved(),'light');
  e.theme.setPreference('system');e.media.matches=true;e.media.dispatchEvent({type:'change'});assert.equal(e.theme.resolved(),'dark');
  assert.equal(e.theme.setPreference('invalid'),false);assert.equal(e.theme.getPreference(),'system');
});
test('새 포트에서도 쿠키값을 사용하고 포커스 복귀 시 다른 창 변경을 반영한다',()=>{
  const e=setup({cookie:'chida_theme_preference=dark',storage:'light'});assert.equal(e.theme.resolved(),'dark');
  e.document.cookie='chida_theme_preference=light';e.window.dispatchEvent({type:'focus'});assert.equal(e.theme.resolved(),'light');
  e.theme.setPreference('dark');assert.equal(e.cookie(),'chida_theme_preference=dark');
});
test('저장소 차단 시 사용자가 선택한 현재 창 테마를 유지한다',()=>{
  const e=setup({blocked:true});e.theme.setPreference('dark');e.window.dispatchEvent({type:'focus'});assert.equal(e.theme.resolved(),'dark');
});
test('같은 포트 창간 변경과 설정 select는 연결되며 중복 리스너를 만들지 않는다',()=>{
  const e=setup(), select=new Events();
  const cleanup=e.theme.connect(select);assert.equal(cleanup,e.theme.connect(select));assert.equal(select.value,'dark');
  select.value='dark';select.dispatchEvent({type:'change'});assert.equal(e.theme.resolved(),'dark');
  e.window.dispatchEvent({type:'storage',key:'chida:theme',newValue:'light'});assert.equal(select.value,'light');
  cleanup();e.theme.setPreference('dark');assert.equal(select.value,'light');
});
test('미디어 및 편집 DOM을 읽거나 변경하지 않는다',()=>{
  const e=setup();assert.deepEqual(Object.keys(e.document.documentElement.dataset).sort(),['theme','themePreference']);
  assert(!code.includes('video'));assert(!code.includes('canvas'));assert(!code.includes('fetch('));
});

test('읽기 전용 쿠키의 오래된 값이 현재 선택을 되돌리지 않는다',()=>{
  const e=setup({cookie:'chida_theme_preference=light',cookieReadOnly:true});
  e.theme.setPreference('dark');e.window.dispatchEvent({type:'focus'});assert.equal(e.theme.resolved(),'dark');
});

test('기존 명시 light/system 선호는 기본 다크로 덮지 않는다',()=>{
  const light=setup({storage:'light',dark:true});assert.equal(light.theme.getPreference(),'light');assert.equal(light.theme.resolved(),'light');
  const system=setup({cookie:'chida_theme_preference=system',dark:false});assert.equal(system.theme.getPreference(),'system');assert.equal(system.theme.resolved(),'light');
  system.media.matches=true;system.media.dispatchEvent({type:'change'});assert.equal(system.theme.resolved(),'dark');
  const invalid=setup({storage:'bad',cookie:'chida_theme_preference=bad',dark:false});assert.equal(invalid.theme.resolved(),'dark');
});
