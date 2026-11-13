import assert from 'node:assert/strict';
import {availableResultModes,preferredResultMode,createResultNavigation,resultDrawer,bindSceneDetails,syncSceneDrawer} from '../web/result-flow.js';
import {bindSpeechResultLayout} from '../web/results-layout.js';

class Element{
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.style={};this.dataset={};this.listeners={};this.className='';this.clientWidth=1010;this.classes=new Set();this.classList={add:cls=>this.classes.add(cls),remove:cls=>this.classes.delete(cls)};}
  append(...children){for(const child of children){child.remove();this.children.push(child);child.parentElement=this;}}
  prepend(child){child.remove();this.children.unshift(child);child.parentElement=this;}
  before(child){child.remove();const i=this.parentElement.children.indexOf(this);this.parentElement.children.splice(i,0,child);child.parentElement=this.parentElement;}
  after(child){child.remove();const i=this.parentElement.children.indexOf(this);this.parentElement.children.splice(i+1,0,child);child.parentElement=this.parentElement;}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(child=>child!==this);this.parentElement=null;}
  setAttribute(key,value){this.attributes[key]=String(value);}getAttribute(key){return this.attributes[key];}
  querySelector(selector){const cls=selector.split('.').at(-1);return (selector.startsWith(':scope')?this.children:descendants(this)).find(n=>n.className.split(' ').includes(cls));}
  querySelectorAll(selector){return descendants(this).filter(n=>selector.split(',').some(tag=>n.tagName===tag.toUpperCase()));}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}dispatchEvent(event){for(const fn of this.listeners[event.type]||[])fn(event);}
  get isConnected(){return this===root.body||!!this.parentElement?.isConnected;}getClientRects(){return this.isConnected?[{}]:[];}
  show(){this.open=true;}close(){this.open=false;queueMicrotask(()=>this.dispatchEvent({type:'close'}));}
  focus(){this.focused=true;root.activeElement=this;}click(){if(!this.disabled)this.onclick?.();}setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;}
}
const descendants=node=>node.children.flatMap(child=>[child,...descendants(child)]);
const main=new Element('main'),events=new Map();
const root={cookie:'',body:new Element('body'),createElement:tag=>new Element(tag),getElementById:id=>descendants(root.body).find(n=>n.id===id),querySelector:selector=>selector==='dialog[open]'?descendants(root.body).find(n=>n.tagName==='DIALOG'&&n.open):null,addEventListener:(name,fn)=>events.set(name,fn)};root.body.append(main);
globalThis.document=root;globalThis.localStorage={getItem(){return null;},setItem(){throw Error('검사 중 저장소 쓰기 금지');}};
globalThis.ResizeObserver=class{observe(){}disconnect(){}};
const add=(id,parent=main,tag='div')=>{const el=new Element(tag);el.id=id;parent.append(el);return el;};
const speech=add('speech-panel'),search=add('speech-search',speech,'form'),follow=add('follow',speech);follow.className='speech-follow-tools';
const rows=add('transcript-rows',speech),pageTools=add('speech-pages',speech),prev=add('speech-prev',pageTools,'button');
const correction=add('correction',rows,'textarea');correction.value='아직 저장하지 않은 교정';correction.oninput=()=>{};const inputHandler=correction.oninput;
const contextPanel=add('context-panel'),legacy=add('legacy-tabs',contextPanel);legacy.className='review-tabs';add('context-view-panel',contextPanel);add('context-clips-panel',contextPanel);
const toolbars=new Map(),launches=[];
for(const [kind,panelId,startId,versionId,readyId] of [['transcript','speech-panel','speech-new','speech-version','speech-readiness'],['detail','context-view-panel','context-new','context-version','context-readiness'],['clips','context-clips-panel','clips-new','context-clips-version','clips-readiness']]){
  const toolbar=add(kind+'-toolbar',root.getElementById(panelId));toolbar.className='result-toolbar';
  const version=add(versionId,toolbar,'select');version.value='읽던 버전';version.onchange=()=>launches.push(kind+'-version');
  const start=add(startId,toolbar,'button');start.onclick=()=>launches.push(kind);
  const ready=add(readyId,root.getElementById(panelId),'p');ready.textContent='모델 준비됨';
  const history=kind==='transcript'?null:add(kind==='clips'?'clips-job-history':'context-job-history',root.getElementById(panelId),'details');
  if(history){history.hidden=kind!=='clips';add(kind+'-stop',history,'button').onclick=()=>launches.push(kind+'-stop');}
  toolbars.set(kind,{toolbar,version,start,ready,history});
}
const guidance=new Map([['speech-result-status','transcript'],['context-result-state','detail'],['context-clips-guidance','clips']].map(([id,kind])=>{const node=add(id);node.textContent='확인할 결과 안내';return [kind,node];}));
const all={path:'/test/vod-1',speech:{versions:[{id:'s',segment_count:3}]},context:{runs:['detail','timestamps','clips'].map(mode=>({id:mode,mode}))}};
const transcriptOnly={path:'/test/partial/vod-1',speech:{transcript:{id:'speech',segment_count:2}},context:{runs:[]}};
const empty={path:'/test/vod-2',speech:{versions:[{id:'pending',segment_count:0,complete:false}]},context:{runs:[]}};
const snapshot=structuredClone(all);
assert.deepEqual(availableResultModes(all),['transcript','detail','timestamps','clips']);
assert.deepEqual(availableResultModes(transcriptOnly),['transcript']);
assert.deepEqual(availableResultModes(empty),[]);
assert.deepEqual(availableResultModes({context:{inputs:{transcripts:[{id:'legacy'}]},runs:[{id:'legacy-result'}]}}),['transcript','detail']);
assert.equal(preferredResultMode(all),'clips');assert.equal(preferredResultMode(all,'detail'),'detail');assert.equal(preferredResultMode(empty),null);

let project=all,navigation,step,contextMode='clips';const selected=[],mounts=[];
const context={selectMode(mode){contextMode=mode;selected.push(mode);},mountUsage(...args){mounts.push(args);}};
navigation=createResultNavigation({root,getProject:()=>project,context,navigate:value=>{step=value;navigation.navigate(value);}});
const button=mode=>root.getElementById('result-tab-'+mode);
const nav=root.getElementById('analysis-results-nav');
assert.deepEqual(nav.children[0].children.map(n=>n.textContent),['전사 자막','상세 문맥','타임스탬프','클립 후보']);
assert.equal(legacy.hidden,true);
navigation.enter();assert.equal(step,6);assert.equal(navigation.mode(),'clips');assert.equal(contextMode,'clips');
const resultActions=nav.children.find(n=>n.className==='result-primary-actions'),settings=resultActions.children[0];
const launch=()=>resultActions.children.find(n=>n!==settings&&!n.hidden);
assert.equal(root.getElementById('result-options-clips').hidden,true);settings.onclick();assert.equal(root.getElementById('result-options-clips').hidden,false);
assert.equal(settings.getAttribute('aria-expanded'),'true');assert.equal(settings.getAttribute('aria-controls'),'result-drawer');
assert.equal(root.getElementById('result-options-clips').parentElement.className,'result-drawer-body');assert.equal(resultDrawer(root).dialog.open,true);
for(const [kind,{toolbar,version,start,ready}] of toolbars){assert.equal(toolbar.parentElement.id,'result-options-'+kind);assert.equal(ready.parentElement,toolbar.parentElement);assert.equal(root.getElementById(version.id),version);assert.equal(version.value,'읽던 버전');assert.equal(start.parentElement,kind==='transcript'?toolbar.parentElement:resultActions);assert.equal(start.hidden,kind!=='clips');}
assert.equal(launch(),toolbars.get('clips').start);launch().click();assert.equal(launches.at(-1),'clips');toolbars.get('clips').version.onchange();assert.equal(launches.at(-1),'clips-version');
assert.equal(root.getElementById('clips-job-history'),toolbars.get('clips').history);
assert.equal(toolbars.get('clips').history.parentElement.id,'result-options-clips');
assert.equal(toolbars.get('clips').history.hidden,false);
for(const [kind,node] of guidance){assert.equal(node.parentElement.id,'result-options-'+kind);assert.equal(node.textContent,'확인할 결과 안내');}
root.getElementById('clips-stop').click();assert.equal(launches.at(-1),'clips-stop');
assert.equal(toolbars.get('detail').history.parentElement.id,'result-options-detail');
assert.equal(toolbars.get('detail').history.hidden,true);
button('detail').onclick();assert.equal(navigation.mode(),'detail');assert.equal(step,6);
assert.equal(root.getElementById('result-options-clips').hidden,true);assert.equal(settings.getAttribute('aria-expanded'),'false');settings.onclick();assert.equal(root.getElementById('result-options-detail').hidden,false);
toolbars.get('detail').start.disabled=true;navigation.update();assert.equal(launch().disabled,true);const launchCount=launches.length;launch().click();assert.equal(launches.length,launchCount);toolbars.get('detail').start.disabled=false;
project=structuredClone(all);project.context.runs.push({id:'new-clips',mode:'clips'});navigation.update();
assert.equal(navigation.mode(),'detail'); // 폴링은 새 클립 결과가 생겨도 사용 중인 결과를 바꾸지 않는다.
button('transcript').onclick();assert.equal(step,3);assert.deepEqual(mounts.at(-1),['speech-results-preview']);
assert.equal(launch().textContent,'＋ 새 분석');launch().click();assert.equal(launches.at(-1),'detail');toolbars.get('transcript').start.click();assert.equal(launches.at(-1),'transcript');
button('detail').onclick();assert.deepEqual(mounts.at(-1),['context-preview']);
project=transcriptOnly;navigation.update();navigation.enter();assert.equal(step,3);
assert.equal(launch(),toolbars.get('detail').start);assert.equal(launch().hidden,false); // 전사만 있어도 새 AI 분석으로 진입한다.
assert.equal(button('clips').disabled,true);button('clips').onclick();assert.equal(step,3);assert.equal(navigation.mode(),'transcript');
project=all;navigation.update();navigation.enter();assert.equal(step,6);assert.equal(navigation.mode(),'detail');
button('detail').onkeydown({key:'End',preventDefault(){}});assert.equal(navigation.mode(),'clips');assert.equal(button('clips').focused,true);
events.get('context-mode-change')({detail:{mode:'timestamps'}});assert.equal(button('timestamps').attributes['aria-selected'],'true');
project=empty;navigation.update();navigation.enter();assert.equal(step,6);assert.equal(nav.children[1].hidden,false);assert.ok(nav.children[0].children.every(n=>n.disabled));
assert.equal(launch(),toolbars.get('detail').start);assert.equal(launch().hidden,false); // 결과가 없어도 새 분석 진입은 유지한다.
navigation.navigate(0);assert.equal(nav.hidden,true);
project=all;navigation.update();navigation.enter('transcript');navigation.navigate(10);
navigation.enter('timestamps');assert.equal(step,6);assert.equal(navigation.mode(),'timestamps');assert.equal(contextMode,'timestamps');

const workspace=root.getElementById('speech-results-workspace');
assert.equal(workspace.children.length,3); // 기존 결과 + 폭 조절 + 미리보기.
assert.equal(rows.parentElement.id,'speech-results-list');assert.equal(search.parentElement.id,'speech-results-tools');
assert.equal(follow.parentElement,search.parentElement);assert.equal(prev.parentElement,pageTools);assert.equal(pageTools.parentElement,search.parentElement);
assert.equal(root.getElementById('correction'),correction);assert.equal(correction.value,'아직 저장하지 않은 교정');assert.equal(correction.oninput,inputHandler);
assert.equal(bindSpeechResultLayout(root),workspace);assert.equal(workspace.children.length,3);
assert.deepEqual(all,snapshot); // 제공된 결과/전사 메타데이터는 수정하지 않는다.
// 닫기 이벤트가 늦게 와도 새 패널을 닫거나 옮긴 원래 노드를 분리하지 않는다.
const drawer=resultDrawer(root),source=add('scene'),detail=add('detail-content',source),field=add('draft',detail,'textarea');field.value='저장하지 않은 내용';field.dataset.draftKey='draft-key';field.selectionStart=2;field.selectionEnd=5;
const selection=add('selection',source,'button');selection.className='secondary scene-selection-button';
const more=bindSceneDetails(source,detail,{title:'장면',key:'scene-1'});
assert.equal(more.textContent,'내용근거');assert.equal(more.parentElement,selection.parentElement);assert.equal(more.parentElement.className,'play-actions scene-actions');
more.click();assert.equal(detail.parentElement.className,'result-drawer-body');field.focus();
drawer.close();more.click();await Promise.resolve();assert.equal(drawer.dialog.open,true);assert.equal(root.getElementById('draft'),field);assert.equal(field.value,'저장하지 않은 내용');
const replacement=add('new-scene'),replacementDetail=add('new-detail',replacement),replacementField=add('new-draft',replacementDetail,'textarea');replacementField.dataset.draftKey='draft-key';replacementField.value=field.value;field.focus();source.remove();
bindSceneDetails(replacement,replacementDetail,{title:'장면 갱신',key:'scene-1'});syncSceneDrawer();await Promise.resolve();
assert.equal(drawer.dialog.open,true);assert.equal(replacementDetail.parentElement.className,'result-drawer-body');assert.equal(root.activeElement,replacementField);assert.equal(replacementField.selectionStart,2);assert.equal(replacementField.selectionEnd,5);
replacement.remove();syncSceneDrawer();await Promise.resolve();assert.equal(drawer.dialog.open,false);
const motionSource=add('motion-scene'),motionDetail=add('motion-detail',motionSource),motionField=add('motion-field',motionDetail,'textarea'),animations=[];
motionField.value='보존할 교정';drawer.dialog.animate=()=>{const animation={cancelled:false,cancel(){this.cancelled=true;}};animations.push(animation);return animation;};
const motionMore=bindSceneDetails(motionSource,motionDetail,{title:'모션 확인',key:'motion'});motionMore.click();
const closeButton=descendants(drawer.dialog).find(n=>n.className==='result-drawer-close');closeButton.click();const closing=animations.at(-1);
assert.equal(drawer.dialog.inert,true);assert.equal(motionDetail.parentElement.className,'result-drawer-body');
motionMore.click();closing.onfinish();assert.equal(closing.cancelled,true);assert.equal(drawer.dialog.open,true);assert.equal(drawer.dialog.inert,false);
closeButton.click();animations.at(-1).onfinish();assert.equal(drawer.dialog.open,false);assert.equal(motionDetail.parentElement,motionSource);assert.equal(motionField.value,'보존할 교정');
console.log('분석 탐색: 4개 탭·가용성·버전/원본 DOM·오른쪽 설정·빠른 재열기·폴링 교정 커서·사라진 결과 패널 정리 검사 통과');
