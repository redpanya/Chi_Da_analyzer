import {frameErrors, showFrameErrors} from './studio-frame-validation.js';
import {studioHistory} from './studio-history.js';
import {pagePolling} from './page-lifecycle.js';
import {createEditSession} from './edit-session.js';
import {studioCaptions} from './studio-captions-ui.js';
import {fastConflicts} from './studio-export-check.js';
import {timecode} from './player.js';
import {createFramePreview} from './clip-studio-preview.js';
import {studioDecorations} from './studio-decorations.js';
import {bindCaptionSize} from './studio-caption-size.js';
import {createCaptionDesign} from './studio-caption-design.js';
import {captionTemplates} from './studio-caption-templates.js';
const $=id=>document.getElementById(id);
const el=(tag,text='')=>{const e=document.createElement(tag);e.textContent=text;return e;};
export function createStudioTools({api,identity,video,selection,getRatio,setRatio,restore,rangeDrafts,restoreRangeDrafts,onCaptionPreview}){
  let revision=0,catalog=[],origin=0,ready=false,running=false,refreshing=false;
  const status=$('render-state'),history=$('render-history');
  const captionSize=bindCaptionSize($('caption-size'),$('caption-size-input'),$('caption-size-error'));
  const captionDesign=createCaptionDesign($('caption-design'),$('caption-style'),$('caption-design-state'),$('caption-design-error'));
  const templates=captionTemplates({api,design:captionDesign});
  function options(){return {ratio:$('frame-layout').value==='split'?'9:16':getRatio(),layout:$('frame-layout').value,split:Number($('frame-split').value),
    game:['x','y','w','h'].map(k=>Number($('game-'+k).value)),face:['x','y','w','h'].map(k=>Number($('face-'+k).value)),
    fit:$('frame-fit').value,x:Number($('frame-x').value),y:Number($('frame-y').value),size:$('export-size').value,mode:document.querySelector('[name=output-mode]:checked').value,
    transition:$('transition').value,volume:Number($('volume').value),brightness:Number($('brightness').value),contrast:Number($('contrast').value),saturation:Number($('saturation').value),fade:Number($('effect-fade').value),
    caption:$('caption-enabled').checked,style:captionDesign.style(),caption_design:captionDesign.read(),font:$('caption-font').value,caption_language:$('caption-language').value,font_size:Number($('caption-size').value),position:$('caption-position').value,caption_x:Number($('caption-x').value),caption_y:Number($('caption-y').value),image:decorations.imageOptions(),sidecar:$('sidecar').checked,speed:$('render-speed').value};}
  const input=()=>$('caption-version').value?{transcript_run:$('caption-version').value,speaker_run:null}:null;
  const request=()=>({clips:selection().map(r=>({id:r.id,title:r.title,start_ms:r.start_ms,end_ms:r.end_ms})),options:options(),selection:input(),caption_edits:captions.edits(),caption_versions:captions.versions(),range_drafts:rangeDrafts()});
  const session=createEditSession({read:request,status:$('studio-save-state'),save:async value=>{if(!captionSize.valid())throw Error($('caption-size-error').textContent);if(!captionDesign.valid())throw Error($('caption-design-error').textContent);const issues=frameErrors(options(),video.videoWidth,video.videoHeight);if(Object.keys(issues).length)throw Error(Object.values(issues)[0]);const saved=await api('studio-draft',{...identity(),revision,request:value});revision=saved.revision;}});
  function buttons(){
    if(!ready)return;
    if(spaceKey&&spaceKey!==JSON.stringify(request())){$('render-space').textContent='설정이 변경됐습니다. 저장 공간을 다시 확인하세요.';spaceKey='';}
    const frameProblems=frameErrors(options(),video.videoWidth,video.videoHeight);
    showFrameErrors(frameProblems);
    const conflicts=fastConflicts(options(),input());
    $('render-conflicts').textContent=conflicts.length?'빠른 저장 전 확인: '+conflicts.join(' · '):'';
    $('render-start').disabled=Object.keys(frameProblems).length>0||!captionDesign.valid()||!captionSize.valid()||!selection().length||running||decorations.blocked()||conflicts.length>0||((options().caption||options().sidecar)&&!!input()&&captions.blocked());
    decorations.busy(running);
    $('draft-save').disabled=Object.keys(frameProblems).length>0||running||!captionSize.valid()||!captionDesign.valid();session.changed();
  }
  const captions=studioCaptions({api,identity,video,selection,onPreview:onCaptionPreview,onChange:()=>{if(ready)session.changed();},onState:buttons});
  const decorations=studioDecorations({api,identity,video,read:options,onChange:buttons});
  document.addEventListener('input',buttons);document.addEventListener('change',buttons);
  document.addEventListener('click',()=>queueMicrotask(buttons));
  function layout(){const split=$('frame-layout').value==='split';$('split-controls').hidden=!split;if(split)setRatio('9:16');for(const b of document.querySelectorAll('[data-ratio]'))b.disabled=split&&b.dataset.ratio!=='9:16';}
  $('frame-layout').onchange=layout;
  createFramePreview(video,options);
  async function refresh(){
    if(!ready||refreshing)return;refreshing=true;
    try{const value=await api('studio-status',identity());historyUI.set(value.runs);
      running=value.runs.some(r=>r.state==='running');buttons();
    }catch(e){error(e);}finally{refreshing=false;}
  }
  function error(e){status.textContent=e.message;}
  const historyUI=studioHistory({host:history,api,identity,refresh,onError:error});
  let spaceKey='';
  async function checkSpace(){
    const value=request(),key=JSON.stringify(value);$('render-space').textContent='저장 공간 계산 중…';
    try{const info=await api('studio-space',{...identity(),request:value});if(key!==JSON.stringify(request()))return;
      spaceKey=key;$('render-space').textContent=`완성 영상 예상 ${(info.output_min/1024**3).toFixed(2)}~${(info.output_max/1024**3).toFixed(2)}GiB · 중간 파일 포함 ${(info.required_min/1024**3).toFixed(2)}~${(info.required_max/1024**3).toFixed(2)}GiB · 남은 공간 ${(info.free/1024**3).toFixed(2)}GiB · ${info.folder}${info.enough?'':' · 공간 확보 필요'} · 가변 용량 추정치`;
    }catch(e){$('render-space').textContent=e.message;}
  }
  $('render-space-check').onclick=checkSpace;

  $('draft-save').onclick=()=>session.save().catch(error);
  $('render-start').onclick=async()=>{try{$('render-start').disabled=true;status.textContent='영상 저장을 시작합니다.';await session.save();await api('studio-start',{...identity(),request:request()});await refresh();}catch(e){error(e);buttons();}};
  pagePolling(refresh,1500);
  return {selectionChanged(){captions.render();buttons();},async init(project){
    origin=Number(project.input?.start_vod_ms)||0;
    const data=await api('studio-info',identity());catalog=data.inputs.transcripts.filter(r=>r.complete);$('caption-version').replaceChildren(new Option('자막 사용 안 함',''),...catalog.map(r=>new Option(r.label,r.id)));
    if(catalog.length)$('caption-version').value=catalog[0].id;
    if(data.draft){
      revision=data.draft.revision;const draft=data.draft.request,o=draft.options;restore(draft.clips);restoreRangeDrafts(draft.range_drafts||{});
      if(draft.selection&&catalog.some(r=>r.id===draft.selection.transcript_run))$('caption-version').value=draft.selection.transcript_run;
      else if(draft.selection){$('caption-version').value='';status.textContent='초안의 전사 버전이 없습니다. 자막 버전을 다시 선택하세요.';}
      else $('caption-version').value='';
      for(const [id,key] of Object.entries({'frame-layout':'layout','frame-split':'split','frame-fit':'fit','frame-x':'x','frame-y':'y','export-size':'size','transition':'transition','volume':'volume','brightness':'brightness','contrast':'contrast','saturation':'saturation','effect-fade':'fade','caption-style':'style','caption-size':'font_size','caption-position':'position','render-speed':'speed'}))$(id).value=o[key];
      for(const axis of ['x','y'])$('caption-'+axis).value=o['caption_'+axis]??0;
      for(const key of ['game','face'])['x','y','w','h'].forEach((k,i)=>$(key+'-'+k).value=o[key][i]);
      $('caption-enabled').checked=o.caption;$('sidecar').checked=o.sidecar;document.querySelector(`[name=output-mode][value=${o.mode}]`).checked=true;setRatio(o.ratio);layout();
    }
    captionDesign.init(data.caption_designs,data.draft?.request?.options);
    captionSize.sync();await decorations.init(data.draft?.request?.options);
    captions.init(origin,data.draft?.request);await captions.load();ready=true;
    const baseline=request(),storedSize=data.draft?.request?.options?.font_size;
    // 이전 초안의 소수 크기는 정수로 표시하되 명시적으로 저장하기 전까지 변경 상태로 둔다.
    if(Number.isFinite(storedSize))baseline.options.font_size=storedSize;
    session.accept(data.draft?.updated_at,baseline);await templates.load();await refresh();$('caption-enabled').dispatchEvent(new Event('input'));
  }};
}
