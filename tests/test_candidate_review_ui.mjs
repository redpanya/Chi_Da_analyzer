import assert from 'node:assert/strict';
import {dom,Element} from './polish_dom.mjs';
import {createCandidateReview} from '../web/context-review.js';
import {reviewCounts,reviewState} from '../web/context-review-model.js';
import {resultPlayback} from '../web/result-playback.js';
import {resultBrowser} from '../web/result-browser.js';

dom();const flush=()=>new Promise(resolve=>setImmediate(resolve));
const a={id:'a',title:'<script>원문 그대로</script>',start_ms:0,end_ms:1000},b={id:'b',title:'두 번째',start_ms:1000,end_ms:2000};
const host=new Element(),pending=[];let redraws=0;
const api=(action,args)=>new Promise((resolve,reject)=>pending.push({action,args,resolve,reject}));
const review=createCandidateReview({api,host,onChange(){redraws++;}}),project={path:'/보관함/vod-1',root:'/보관함',vod_id:'1'};
assert.deepEqual(reviewCounts([a,b],{a:'accepted'}),{accepted:1,unreviewed:1,held:0,excluded:0});
assert.equal(reviewState({}, {id:'__proto__'}),'unreviewed');
review.setSource(project,'run-1',[a,b]);assert.equal(pending[0].action,'context-review');
assert.equal(review.control(a).children[0].disabled,true);
pending[0].resolve({revision:4,items:{a:'accepted'}});await flush();
assert.equal(review.control(a).children[0].value,'accepted');
const bar=host.beforeNodes[0],filter=bar.children[0].children[0].children[0];
filter.value='accepted';filter.onchange();assert.deepEqual(review.filtered(),[a]);
let select=review.control(b).children[0];select.value='held';select.onchange();
assert.deepEqual(pending.at(-1).args.change,{revision:4,item:'b',status:'held'});
pending.at(-1).reject(Error('다른 창에서 변경했습니다'));await flush();
assert.match(bar.children[1].textContent,/저장하지 못했습니다/);assert.equal(review.control(a).children[0].disabled,true);
assert.equal(review.state(b),'unreviewed'); // 실패한 저장을 완료로 표시하지 않는다.
bar.children[0].children[2].onclick();pending.at(-1).resolve({revision:5,items:{a:'accepted',b:'excluded'}});await flush();
assert.equal(review.state(b),'excluded');assert.equal(filter.value,'accepted');
review.setSource(project,'run-1',[a,b]);assert.equal(pending.length,3); // 폴링으로 검토·필터를 다시 읽지 않는다.
review.setSource({...project,path:'/보관함/.download-ranges/range/vod-1'},'run-1',[b]);const old=pending.at(-1);
review.setSource(project,'run-2',[a]);const fresh=pending.at(-1);
fresh.resolve({revision:0,items:{a:'held'}});await flush();old.resolve({revision:99,items:{a:'excluded'}});await flush();
assert.equal(review.state(a),'held');assert.ok(redraws>3);

// 검토 메모는 AI/댓글과 별도, 폴링·다른 창 충돌 후에도 미저장 초안을 보존한다.
let memo=review.memo(a);memo.open=true;memo.ontoggle();
let field=memo.children[1].children[0];field.value='<script>메모</script>\n영상 확인';field.oninput();
review.setSource(project,'run-2',[a]);memo=review.memo(a);
assert.equal(memo.open,true);assert.equal(memo.children[1].children[0].value,field.value);
memo.children[3].onclick();assert.equal(pending.at(-1).args.change.note,field.value);
pending.at(-1).reject(Error('다른 창 변경'));await flush();
assert.equal(review.memo(a).children[1].children[0].value,field.value);
bar.children[0].children[2].onclick();pending.at(-1).resolve({revision:2,items:{a:'accepted'},notes:{a:'다른 창의 메모'}});await flush();
memo=review.memo(a);assert.equal(memo.children[1].children[0].value,field.value);
memo.children[3].onclick();pending.at(-1).resolve({revision:3,items:{a:'accepted'},notes:{a:field.value}});await flush();
memo=review.memo(a);assert.match(memo.children[0].textContent,/저장됨/);assert.doesNotMatch(memo.children[2].textContent,/저장하지/);
select=review.control(a).children[0];select.value='held';select.onchange();assert.equal(Object.hasOwn(pending.at(-1).args.change,'note'),false);
pending.at(-1).resolve({revision:4,items:{a:'held'},notes:{a:field.value}});await flush();
assert.equal(review.memo(a).children[1].children[0].value,field.value);

// 결과 검색·페이지는 버전별 유지, 재생 위치 이동은 사용자가 켠 경우에만 수행한다.
const column=new Element(),list=new Element();column.append(list);
const items=Array.from({length:60},(_,i)=>({id:String(i),title:'장면 '+i,start_ms:i*1000,end_ms:(i+1)*1000}));
let page=[];const browser=resultBrowser(list,()=>{page=browser.slice(items);});
browser.setScope('version-a');page=browser.slice(items);browser.bar.children[3].children[2].onclick();assert.equal(page[0].id,'25');
browser.setScope('');browser.slice([]);browser.setScope('version-b');page=browser.slice(items);assert.equal(page[0].id,'0');
browser.bar.children[0].value='장면 4';browser.bar.children[0].oninput();assert.equal(page.length,11);
browser.setScope('version-a');page=browser.slice(items);assert.equal(page[0].id,'25');
browser.setScope('version-b');page=browser.slice(items);assert.equal(page.length,11);
const card=new Element('article');card.dataset={start:1000,end:2000};let highlighted=false,scrolls=0;
card.classList.toggle=(_,v)=>highlighted=v;card.removeAttribute=k=>delete card.attributes[k];card.scrollIntoView=()=>scrolls++;
const timeline=new Element(),media=new Element('video'),toolbar=new Element();timeline.querySelectorAll=()=>[card];media.currentTime=1.5;media.paused=false;
let follows=0;const playback=resultPlayback({host:timeline,bar:toolbar,media,followPage(){follows++;}});
media.dispatchEvent({type:'timeupdate'});assert(highlighted);assert.equal(scrolls,0);assert.equal(follows,0);
const follow=toolbar.children[0].children[0];follow.checked=true;follow.onchange();assert.equal(scrolls,1);assert.equal(follows,1);
media.paused=true;media.currentTime=5;media.dispatchEvent({type:'seeked'});assert.equal(highlighted,false);assert.equal(follows,1);
playback.reset();assert.equal(follow.checked,false);
console.log('후보 검토 분리·필터·충돌 복구·오래된 응답 차단·버전별 탐색 보존·옵트인 재생 따라가기 검사 통과');
