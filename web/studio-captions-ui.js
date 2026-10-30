import {timecode} from './player.js';
import {latestResponse} from './page-lifecycle.js';
const $=id=>document.getElementById(id);
export function studioCaptions({api,identity,video,selection,onChange,onState,onPreview}){
  let rows=[],versions={},loaded='',page=0,origin=0,loading=false,failed=false;
  const latest=latestResponse(),select=$('caption-version'),list=$('caption-rows');
  const edits=()=>versions[select.value]||(versions[select.value]={});
  const active=()=>!loading&&!failed&&loaded===select.value;
  function at(){const now=origin+video.currentTime*1000;$('caption-text').textContent=active()?rows.filter(r=>r.start_ms<=now&&now<r.end_ms).map(r=>edits()[r.id]??r.text).join('\n'):'';}
  function visible(){const query=$('caption-search').value.trim().toLowerCase();return rows.filter(r=>selection().some(c=>r.start_ms<c.end_ms&&r.end_ms>c.start_ms)&&(!query||`${timecode(r.start_ms)} ${edits()[r.id]??r.text}`.toLowerCase().includes(query)));}
  function count(total){$('caption-count').textContent=`${total}개 · ${total?page+1:0}/${Math.ceil(total/50)}쪽 · 교정 ${Object.keys(edits()).length}개 · 이 편집에만 적용`;}
  function render(){
    list.replaceChildren();const all=active()?visible():[];page=Math.max(0,Math.min(page,Math.ceil(all.length/50)-1));
    count(all.length);
    $('caption-prev').disabled=page===0;$('caption-next').disabled=(page+1)*50>=all.length;
    for(const r of all.slice(page*50,(page+1)*50)){
      const row=document.createElement('div');row.className='caption-edit-row';
      const jump=document.createElement('button');jump.type='button';jump.className='caption-time';jump.textContent='▶ '+timecode(r.start_ms);jump.setAttribute('aria-label',timecode(r.start_ms)+' 자막 시각 재생');
      const text=document.createElement('textarea');text.rows=2;text.value=edits()[r.id]??r.text;text.maxLength=5000;text.setAttribute('aria-label',timecode(r.start_ms)+' 자막 내용');const version=select.value;
      jump.onclick=()=>{if(!active()||version!==select.value)return;onPreview?.(r);};
      text.oninput=()=>{if(!active()||version!==select.value)return;edits()[r.id]=text.value;count(all.length);at();onChange();};row.append(jump,text);list.append(row);
    }
  }
  async function load(){
    const current=latest.begin(),version=select.value;loading=true;failed=false;rows=[];page=0;render();at();onState();
    $('caption-load-state').textContent=version?'선택한 전사 자막을 불러오는 중…':'자막 사용 안 함';
    try{const value=version?await api('studio-captions',{...identity(),selection:{transcript_run:version,speaker_run:null}}):{rows:[]};
      if(!current()||version!==select.value)return;rows=value.rows;loaded=version;$('caption-load-state').textContent=version?`자막 준비됨 · ${select.selectedOptions[0].textContent} · ${rows.length}개`: '자막 사용 안 함';
    }catch(e){if(!current())return;failed=true;$('caption-load-state').textContent='자막 불러오기 실패 · '+e.message;}
    finally{if(current()){loading=false;render();at();onState();}}
  }
  select.onchange=()=>{onChange();void load();};$('caption-retry').onclick=load;
  const top=()=>{document.querySelector('.inspector-body').scrollTop=0;};
  $('caption-search').oninput=()=>{page=0;render();top();};$('caption-prev').onclick=()=>{page--;render();top();};$('caption-next').onclick=()=>{page++;render();top();};
  $('caption-current').onclick=()=>{const all=visible(),now=origin+video.currentTime*1000,index=all.findIndex(r=>r.end_ms>now);page=Math.floor(Math.max(0,index)/50);render();top();};
  video.addEventListener('timeupdate',at);video.addEventListener('seeked',at);
  return {render,load,blocked:()=>!active(),edits,versions:()=>versions,init(value,draft){origin=value;versions=draft?.caption_versions||{};if(draft?.selection&&!versions[draft.selection.transcript_run])versions[draft.selection.transcript_run]=draft.caption_edits||{};}};
}
