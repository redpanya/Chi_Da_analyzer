import {timecode} from './player.js';
import {createTimeline,viewport} from './timeline.js';
const $=id=>document.getElementById(id);
export function createExplorer({api,player}){
  let project=null,info=null,key='',active=false,generation=0,position=0,center=0,offset=0,view=null;
  const video=$('player');
  const timeline=createTimeline({canvas:$('unified-graph'),onSeek:jump,onPan:pan,onZoom:zoom});
  function draw(){
    if(!info)return;
    view=viewport(info.duration_ms,center,Number($('timeline-span').value));
    timeline.set(info,position,view);
    $('explore-position').max=info.duration_ms||1;$('explore-position').value=(view.start+view.end)/2;
    $('explore-window').textContent=`표시 범위 ${timecode(view.start)} ~ ${timecode(view.end)} · 초록 채팅량 / 금색 반응 / 색상별 발언·화자 / 주황 인식 실패`;
    $('explore-clock').textContent=`${timecode(position)} / ${timecode(info.video_ms||info.duration_ms)}`;
    const selected=(info.reactions||[]).filter(r=>r.start_ms<=position&&position<=r.end_ms);
    $('timeline-detail').textContent=selected.length?selected.map(r=>r.text).join(' · '):'선택 시각에 겹치는 반응 후보 없음';
  }
  function pan(ms){$('explore-follow').checked=false;center=Math.max(0,Math.min(info?.duration_ms||0,ms));draw();}
  function resize(){if(view)center=(view.start+view.end)/2;draw();}
  function zoom(direction){const spans=[0,1800000,600000,120000],i=spans.indexOf(Number($('timeline-span').value));$('timeline-span').value=spans[Math.max(0,Math.min(3,i+direction))];resize();}
  function jump(ms){
    position=Math.max(0,Math.min(info?.video_ms||info?.duration_ms||ms,ms));
    if(project?.tasks.video.state==='complete')player.seek(position,!video.paused);
    else $('explore-message').textContent='영상 준비 전입니다. 시간축 자료만 확인할 수 있습니다.';
    draw();
  }
  async function refresh(){
    if(!active||!project)return;
    const request=++generation,selected=project.path;
    try{const data=await api('explore-info',{root:project.root,vod_id:project.vod_id,chat_offset_ms:Math.round(offset*1000)});
      if(request!==generation||project?.path!==selected||!active)return;
      info=data;$('explore-notes').textContent=data.notes.join(' · ');draw();
    }catch(error){if(request===generation)$('explore-message').textContent=error.message;}
  }
  $('timeline-in').onclick=()=>zoom(1);$('timeline-out').onclick=()=>zoom(-1);
  $('timeline-span').onchange=resize;$('timeline-fit').onclick=()=>{$('timeline-span').value='0';resize();};
  $('timeline-current').onclick=()=>{center=position;draw();};
  for(const [id,direction] of [['timeline-prev',-1],['timeline-next',1]])$(id).onclick=()=>{const v=viewport(info?.duration_ms||1,center,Number($('timeline-span').value));pan((v.start+v.end)/2+direction*(v.end-v.start)*.8);};
  $('explore-position').oninput=()=>pan(Number($('explore-position').value));
  $('explore-follow').onchange=()=>{if($('explore-follow').checked){center=position;draw();}};
  $('explore-offset-form').onsubmit=e=>{e.preventDefault();const value=$('explore-offset').valueAsNumber;if(!project||!Number.isFinite(value)||Math.abs(value)>600)return;offset=value;try{const name='explore:'+project.path;sessionStorage.setItem(name,JSON.stringify({...JSON.parse(sessionStorage.getItem(name)||'{}'),offset}));}catch{}refresh();};
  for(const event of ['timeupdate','seeked'])video.addEventListener(event,()=>{if(!active)return;position=Math.round(video.currentTime*1000);if($('explore-follow').checked)center=position;draw();});
  return {refresh,setProject(value){const changed=value?.path!==project?.path;project=value;if(changed){info=null;center=position=offset=0;$('explore-offset').value='0';$('explore-message').textContent='';$('timeline-span').value='600000';$('explore-follow').checked=false;}
    if(changed){view=null;try{const saved=JSON.parse(sessionStorage.getItem('explore:'+value?.path)||'{}');if(Number.isFinite(saved.offset)&&Math.abs(saved.offset)<=600)offset=saved.offset;}catch{}$('explore-offset').value=offset;$('explore-title').textContent=value?.metadata.title||'';$('explore-notes').textContent='';$('explore-window').textContent='시간축 자료를 불러옵니다.';timeline.set(null,0);}
    const next=JSON.stringify([value?.path,value?.tasks,value?.speech?.updated_at,value?.voices?.revision,value?.analysis_running]);if(next===key)return;key=next;generation++;if(active)refresh();},
    open(enabled){active=enabled;generation++;if(enabled){position=video.getAttribute('src')?Math.round(video.currentTime*1000):0;refresh();}},
    focus(row){const ms=row.peak_ms??row.at_ms??row.start_ms;center=ms;position=ms;if(project?.tasks.video.state==='complete')player.seek(ms,false);draw();}};
}
