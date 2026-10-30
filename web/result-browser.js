import {timecode} from './player.js';
export const resultText=item=>[typeof item.summary==='string'?item.summary:'',item.title,item.summary?.title,...(item.summary?.context||[]).map(r=>r.text),...(item.summary?.chat||[]).map(r=>r.text),item.reason,timecode(item.start_ms)].filter(Boolean).join(' ').toLowerCase();
export function filteredResults(rows,query,itemOf=r=>r){const q=query.trim().toLowerCase();return q?rows.filter(r=>resultText(itemOf(r)).includes(q)):rows;}
export function lazyDetails(details,build){let loaded=false;details.addEventListener('toggle',()=>{if(details.open&&!loaded){loaded=true;build();}});return details;}
export function resultBrowser(host,onChange,{itemOf=r=>r,keyOf=r=>r.id}={}){
  let page=0,rows=[],filtered=[];
  const bar=document.createElement('div');bar.className='play-actions result-browser';
  function make(tag,text='',parent=bar){const n=document.createElement(tag);n.textContent=text;parent.append(n);return n;}
  const search=make('input');search.type='search';search.placeholder='제목·본문·시각 검색';search.setAttribute('aria-label','결과 전체 검색');
  const clock=make('input');clock.placeholder='HH:MM:SS';clock.setAttribute('aria-label','결과 시각 찾기');clock.size=10;
  const jump=make('button','시각 찾기'),pages=make('div');pages.className='result-pagination';
  const prev=make('button','이전',pages),count=make('span','',pages),next=make('button','다음',pages);
  const message=make('span');message.setAttribute('role','status');host.before(bar);
  function turnPage(delta){
    page+=delta;onChange();host.scrollTop=0;
    // 고정된 도구 막대 자체가 아닌 목록 열의 시작으로 이동한다.
    host.parentElement.scrollIntoView({block:'start',behavior:'instant'});
  }
  search.oninput=()=>{page=0;onChange();};prev.onclick=()=>turnPage(-1);next.onclick=()=>turnPage(1);
  const size=25;
  function locate(index){page=Math.floor(Math.max(0,index)/size);onChange();const row=host.querySelectorAll('article')[Math.max(0,index)%size];row?.scrollIntoView({block:'nearest'});}
  jump.onclick=()=>{const match=/^(\d{1,3}):([0-5]\d):([0-5]\d)$/.exec(clock.value.trim());if(!match){message.textContent='시각은 HH:MM:SS로 입력하세요.';return;}
    const at=(+match[1]*3600 + +match[2]*60 + +match[3])*1000;let i=filtered.findIndex(r=>itemOf(r).start_ms<=at&&at<itemOf(r).end_ms);if(i<0)i=filtered.findIndex(r=>itemOf(r).start_ms>=at);if(i<0){message.textContent='이후 결과가 없습니다.';return;}message.textContent='해당 시각의 결과로 이동했습니다.';locate(i);};
  return {signature:()=>[search.value,page],reset(){page=0;search.value='';message.textContent='';},slice(values){rows=values;filtered=filteredResults(values,search.value,itemOf);page=Math.max(0,Math.min(page,Math.ceil(filtered.length/size)-1));prev.disabled=page===0;next.disabled=(page+1)*size>=filtered.length;count.textContent=`${filtered.length?page+1:0}/${Math.ceil(filtered.length/size)}쪽 · 검색 ${filtered.length}개`;return filtered.slice(page*size,(page+1)*size);},
    locate(id){search.value='';filtered=rows;const i=rows.findIndex(r=>keyOf(itemOf(r))===id);if(i>=0)locate(i);return i>=0;}};
}
