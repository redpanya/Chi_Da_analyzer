import {createBackground} from './context-background.js';
import {createContextInputs} from './context-inputs.js';
import {fallbackEvidence,fallbackChats} from './context-fallback.js';
import {timecode} from './player.js';
import {contextReactions} from './context-reactions.js';
import {createContextCopy,canCopyContext} from './context-copy.js';
import {interpretationDetails} from './context-interpretations.js';
import {contextGroups,relationLabel,phaseProgress,contextSummaryFailed,contextReactionRows} from './context-tree.js';
const $=id=>document.getElementById(id);
const node=(tag,text,cls='')=>{const el=document.createElement(tag);el.textContent=text;el.className=cls;return el;};
export function createContext({api,player,onProject}) {
  const copy=createContextCopy({api});
  let project=null,key='',serial=0,currentRun=null,currentResult=null,latestRun=null,listItems=[],viewMode='detail';
  const selectedRuns={detail:null,timestamps:null}, thinking={detail:true,timestamps:false};
  const modeOf=r=>r?.mode||'detail';
  const identity=()=>({root:project.root,vod_id:project.vod_id});
  const message=text=>$('context-notice').textContent=text;
  const background=createBackground({api,message,onChange:controls});
  const inputs=createContextInputs(controls);
  function controls(){
    $('context-resume').disabled=!project||project.locked||currentResult?.scope!=='full'||currentResult.complete||currentResult.stale||currentResult.origin==='external';
    $('context-generate').disabled=!project||project.locked||!inputs.ready()||(viewMode==='detail'&&!background.ready());
  }
  function changeTab(mode){
    if(mode===viewMode)return;
    thinking[viewMode]=$('context-thinking').checked;selectedRuns[viewMode]=currentRun;
    viewMode=mode;serial++;key='';currentRun=null;currentResult=null;listItems=[];
    copy.setItems([],'');renderList(true);$('context-thinking').checked=thinking[mode];
    setTabs();setVersions();controls();
  }
  function setTabs(){
    for(const mode of ['detail','timestamps']){const b=$('context-tab-'+mode);b.setAttribute('aria-selected',String(mode===viewMode));b.tabIndex=mode===viewMode?0:-1;}
    $('context-view-panel').setAttribute('aria-labelledby','context-tab-'+viewMode);
    $('context-list-title').textContent=viewMode==='timestamps'?'주제 변경 타임스탬프':'시간순 문맥 목록';
    $('context-generate').textContent=viewMode==='timestamps'?'빠른 타임스탬프 새로 만들기':'전체 영상 새로 정리';
    $('context-mode-note').textContent=viewMode==='timestamps'?'전사만으로 주제 제목을 만듭니다. 상세 근거 검토·채팅 요약은 생략하며, 사고 끄기로 시작합니다. 🤩는 저장된 채팅 반응 분석을 연결합니다.':'대화 문맥·근거 검토·채팅 반응을 함께 정리합니다. 기존 상세 결과와 외부 상세 결과를 확인할 수 있습니다.';
    $('context-background-form').hidden=viewMode==='timestamps';
    const state=project?.context,taskMode=state?.action?.startsWith('timestamps')?'timestamps':'detail';
    $('context-task-kind').textContent=state?.action?`${state.owned?'진행 중':'최근'} ${state.action==='model'?'모델 준비':taskMode==='timestamps'?'빠른 타임스탬프':'상세 문맥 정리'} 작업${taskMode!==viewMode&&state.action!=='model'?' · 현재 탭과 다른 작업의 상태입니다.':''}`:'';
  }
  function setVersions(){
    const runs=(project?.context?.runs||[]).filter(r=>modeOf(r)===viewMode),select=$('context-version');
    const id=[currentRun,selectedRuns[viewMode],project?.context?.run,...runs.map(r=>r.id).reverse()].find(id=>runs.some(r=>r.id===id));
    select.replaceChildren(...runs.map(r=>new Option(r.label+' · '+r.title,r.id)));select.value=id||'';
    if(id)load(id);else{currentRun=null;currentResult=null;listItems=[];copy.setItems([],'');renderList(true);$('context-overview').replaceChildren(node('p','이 탭에 저장된 결과가 없습니다.','hint'));}
  }
  for(const mode of ['detail','timestamps']){
    const b=$('context-tab-'+mode);b.onclick=()=>changeTab(mode);
    b.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?'detail':e.key==='End'?'timestamps':mode==='detail'?'timestamps':'detail';changeTab(next);$('context-tab-'+next).focus();}};
  }
  function article(item,index){
    const box=node('article','','context-item'),input=item.input,summary=item.summary;
    box.dataset.start=item.start_ms;box.dataset.end=item.end_ms;box.dataset.id=item.id||String(item.start_ms);
    const label=`${timecode(item.start_ms)} ~ ${timecode(item.end_ms)}`;
    const title=node('h3',contextSummaryFailed(item)?'요약 실패':item.gap?'사용 가능한 전사 없음':`${item.kind?'':index+1+'. '}${summary.title}`);
    if(canCopyContext(item))box.append(copy.checkbox(item));
    if(contextSummaryFailed(item)){title.classList.add('context-failed');box.classList.add('context-failed-item');}
    if(item.reaction_index){const badge=node('span','🤩'.repeat(item.reaction_index)+` ${item.reaction_index}/10`,'context-reaction-index');badge.setAttribute('aria-label',`이 VOD 내 채팅 반응 ${item.reaction_index}/10`);badge.title='같은 길이 반응 창의 상대 강도 · 문맥 안의 최고점';title.append(badge);}
    box.append(node('p',label,'hint'),title);
    if(item.parallel)box.append(node('p','동시에 진행된 별개 대화 · 시간 범위가 다른 문맥과 겹칠 수 있습니다.','hint'));
    if(item.adaptive&&(item.interpretations?.length||item.omissions?.length||item.held_claims?.length||item.review_issues?.length))box.append(interpretationDetails(item,player,!project.locked&&currentResult?.complete?rejectInterpretation:null));
    if(item.kind)box.append(node('p',({topic:'상위 주제',story:'하위 이야기',moment:'하위 반응 장면',reaction:'별도 반응'}[item.kind])+(item.relation_status?' · '+relationLabel[item.relation_status]:''),'context-kind'));
    if(item.review||item.parent_review)box.append(node('p',item.kind==='topic'||item.parent_review?'상위 주제 연결 확인 필요':'이야기 경계 확인 필요','hint'));
    if(item.gap){box.classList.add('context-gap');box.append(node('p',currentResult?.version===10?'이 범위에는 사용할 전사가 없거나 자료 형식 확인이 필요합니다. 음성 미검출이 실제 무음의 확정 판정은 아닙니다.':'이 범위는 대화 문맥을 생성하지 않았습니다. 전사가 없거나 반복·경계 검토 대상 발언만 있습니다.'));}
    const play=node('button','이 구간 재생','secondary');play.disabled=project?.tasks.video.state!=='complete';
    play.onclick=()=>{const start=item.play_start_ms??item.start_ms,end=item.play_end_ms??item.end_ms;player.seek(start,true,end);$('context-playing').textContent=`${timecode(start)} ~ ${timecode(end)} · 구간 끝에서 멈춥니다.`;};box.append(play);
    if((item.kind||currentResult?.version>=6)&&!item.provisional&&!item.time_review&&!item.failed&&!item.gap){
      if(Number.isFinite(item.peak_ms)){const peak=node('button','반응 정점 '+timecode(item.peak_ms),'subtle');peak.disabled=play.disabled;peak.onclick=()=>player.seek(item.peak_ms,true);box.append(peak);}
    }
    if(item.failed)box.append(node('p',item.error+' · 다른 완료 문맥은 사용할 수 있습니다. 이어하기로 이 구간을 재검토하세요.','hint'));
    if(item.boundary_error)box.append(node('p','앞 문맥과의 연결 확인 필요 · 두 요약을 각각 보존했습니다.','hint'));
    if(item.reaction_peaks?.length){
      const peaks=node('div','','play-actions');peaks.setAttribute('aria-label','채팅 반응 시각');
      for(const at of item.reaction_peaks){const outside=at<item.start_ms||at>=item.end_ms;const button=node('button',timecode(at)+(outside?' (인접 반응)':''),'subtle');button.title='채팅 반응 시각으로 이동';button.disabled=play.disabled;button.onclick=()=>{player.seek(at,true);$('context-playing').textContent=timecode(at)+' · 채팅 반응 시각으로 이동했습니다.';};peaks.append(button);}
      box.append(node('p','🤩 채팅 반응 시각','hint'),peaks);
    }
    if(item.provisional)box.append(node('p','이어지는 문맥 · 끝과 설명이 바뀔 수 있습니다. 새 주제 또는 영상 끝에서 확정합니다.','hint'));
    if(item.time_review)box.append(node('p','겹친 발언의 경계 시각 확인 필요 · 댓글 복사 선택에서 제외했습니다.','hint'));
    if(item.evidence_review)box.append(node('p','요약 근거 확인 필요 · 전사 내용이 불명확하거나 원문 대조를 확정하지 못했습니다. 원음을 확인하세요.','hint'));
    if(item.grounding_state==='pending')box.append(node('p','요약 초안 · 원문 대조 중입니다. 대조 완료 후 댓글에 선택할 수 있습니다.','hint'));
    if(item.chat_state==='pending')box.append(node('p',canCopyContext(item)?'채팅 설명 대기 · 대화 문맥은 사용할 수 있습니다.':'채팅 설명 대기','hint'));
    if(item.chat_state==='failed')box.append(node('p','채팅 정리 실패 · '+item.chat_error,'hint'));
    const extra=node('details','');extra.append(node('summary',currentResult?.version>=6?'채팅·원문 보기':'채팅 반응·비교·원문 보기'));
    if(item.grounding_state==='review'&&item.draft_summary){
      const draft=node('details','');draft.append(node('summary','검토용 초안 · 미확정'));
      draft.append(node('p','원문 대조를 통과하지 못해 댓글 복사에서 제외했습니다. 원문·원음과 함께 확인하세요.','hint'));
      draft.append(node('p',item.draft_summary.title));
      for(const part of item.draft_summary.context||[])draft.append(node('p',part.text));
      extra.append(draft);
    }
    if(!item.failed&&(!item.gap||item.chat_state==='complete')){
      const refs=new Map(input.evidence.map(r=>[r.id,r]));
      for(const [name,label] of (currentResult?.mode==='timestamps'?[]:[['context','대화 문맥'],['chat','채팅 반응'],['relation','발언과 반응 비교']])){
        if(name==='relation'&&currentResult?.version===6)continue;
        const target=name==='relation'?extra:box;
        target.append(node('h4',label));
        if(!summary[name].length)target.append(node('p',name==='relation'?'함께 설명할 직접적인 근거가 부족합니다.':name==='chat'?(item.chat_state==='pending'?'채팅 반응 정리 대기':item.chat_state==='failed'?'채팅 반응 정리 실패 · 원문을 확인하세요':'이 구간에서 요약할 채팅 반응 근거가 없습니다.'):'사용할 근거가 없습니다.','hint'));
        for(const item of summary[name]){
          target.append(node('p',item.text));const bar=node('div','','play-actions');
          for(const id of item.evidence){const r=refs.get(id);if(!r)continue;const button=node('button',`${id} · ${timecode(r.start_ms)}${r.kind==='speech'?' 발언':' 채팅'}`,'subtle');button.title=r.text;button.onclick=()=>{player.seek(r.start_ms);$('context-playing').textContent='원문 시각으로 이동했습니다.';};bar.append(button);}extra.append(bar);
        }
      }
      for(const text of summary.uncertainties)extra.append(node('p',text,'hint'));
    }
    if(contextSummaryFailed(item)){
      const refs=fallbackEvidence(item),chats=fallbackChats(item),reference=node('section','','context-reference');
      reference.append(node('h4','원문 기반 참고 · 요약 성공 결과가 아닙니다'));
      for(const row of refs){const b=node('button',timecode(row.start_ms),'subtle');b.disabled=play.disabled;b.onclick=()=>player.seek(row.start_ms,true);reference.append(b,node('p',row.text));}
      if(!refs.length)reference.append(node('p','읽을 수 있는 전사 근거가 없습니다. 원음을 확인하세요.','hint'));
      reference.append(node('h4','채팅 원문 참고'));
      for(const row of chats)reference.append(node('p',`${row.text}${row.count?' × '+row.count:''}`));
      if(!chats.length)reference.append(node('p','이 결과에 보존된 채팅 근거 없음 · 반응 미발생을 의미하지 않습니다.','hint'));
      box.append(reference);
    }
    const details=node('details','');details.append(node('summary','입력 범위·제한·원문'));
    details.append(node('p',input.stats.speech_total!=null?`${input.label} 입력 범위 · 발언 ${input.stats.speech_used}/${input.stats.speech_total}개 · 채팅 ${input.stats.chat_used}/${input.stats.chat_total}건 사용`:`${input.label} · 앞뒤 문맥을 연결한 요약과 선별 원문 근거`,'hint'));
    for(const note of input.notes)details.append(node('p',note,'hint'));
    for(const r of input.evidence)details.append(node('p',`${r.id} · ${timecode(r.start_ms)} ~ ${timecode(r.end_ms)} · ${r.speaker||'채팅'}${r.count?' ×'+r.count:''}: ${r.text}`));
    extra.append(details);box.append(extra);return box;
  }
  function tree(value,box,opened){
    for(const group of contextGroups(value)){
      const section=node('section','','context-topic');
      if(group.topic){
        const count=group.children.filter(x=>x.kind==='moment'||x.kind==='reaction').length+group.children.reduce((n,x)=>n+(x.reactions?.length||0),0);
        if(group.topic.summary)section.append(article({...group.topic,event_count:count},0));
        else section.append(node('h3',group.topic.title+' · 상위 요약 미완료'));
        const details=node('details','','context-children');details.dataset.topic=group.topic.id;
        details.open=opened.has(group.topic.id)?opened.get(group.topic.id):true;
        details.append(node('summary',`하위 이야기·장면 ${group.children.filter(x=>x.kind!=='reaction').length}개 · 반응 ${count}개 · 시간순 보기`));
        for(const child of group.children){
          const card=article(child,0);if(child.kind==='reaction')card.classList.add('context-independent');
          for(const event of child.reactions||[]){const attached=node('details','','context-attached');attached.append(node('summary',(event.reaction_index?'🤩'.repeat(event.reaction_index)+' ':'')+relationLabel[event.relation_status]+' · '+event.summary.title),article(event,0));card.append(attached);}
          details.append(card);
        }
        section.append(details);
      }else section.append(...group.children.map(x=>article(x,0)));
      box.append(section);
    }
  }
  function renderList(resetScroll=false){
    const box=$('context-result'),minimum=Number($('context-min-reaction').value),scroll=box.scrollTop;
    const opened=[...box.querySelectorAll('article')].filter(r=>r.querySelector('details')?.open).map(r=>r.dataset.id);
    const expanded=new Map([...box.querySelectorAll('.context-children')].map(r=>[r.dataset.topic,r.open]));
    const rows=contextReactionRows(listItems,minimum),total=contextReactionRows(listItems).length;
    box.replaceChildren();
    if(currentResult?.version===5&&!minimum)tree({...currentResult,items:listItems},box,expanded);
    else box.append(...rows.map(({item,index})=>article(item,index)));
    $('context-filter-count').textContent=`표시 ${rows.length} / 전체 ${total}개`;
    if(!rows.length)box.append(node('p',minimum?`🤩 ${minimum}개 이상인 문맥이 없습니다. ‘전체’를 선택하면 지수가 없는 항목과 실패 내역도 확인할 수 있습니다.`:viewMode==='timestamps'?'이 탭에 표시할 타임스탬프가 없습니다. 새로 만들거나 8번에서 결과를 가져오세요.':'이 탭에 표시할 상세 문맥이 없습니다.','empty'));
    for(const row of box.querySelectorAll('article'))if(opened.includes(row.dataset.id)&&row.querySelector('details'))row.querySelector('details').open=true;
    box.scrollTop=resetScroll?0:scroll;
  }
  async function load(id){
    if(!project)return;const request=++serial,selected=project.path;
    try{
      const [value,analysis]=await Promise.all([api('context-result',{...identity(),run:id}),api('analysis',identity()).catch(()=>({unreadable:true}))]);if(request!==serial||project?.path!==selected)return;
      const changed=currentResult?.id!==value?.id;
      if(changed){$('context-min-reaction').value='0';listItems=[];}
      currentResult=value;controls();const overview=$('context-overview');
      overview.replaceChildren();if(!value){listItems=[];copy.setItems([],'');renderList(true);overview.append(node('p','표시할 문맥 처리 내역이 없습니다.','hint'));return;}currentRun=value.id;selectedRuns[viewMode]=value.id;$('context-version').value=value.id;
      if(value.stale)overview.append(node('p','이전 입력의 결과 · 전사·화자·채팅이 변경됐습니다. 새 정리를 시작하세요.','hint'));
      let items;
      if(value.version===11){
        overview.append(node('h3',`${value.mode==='timestamps'?'타임스탬프':'외부 상세 문맥'} · ${value.complete?'전체 처리 완료':'일부 처리'} · 발언 ${value.done}/${value.total}`));
        overview.append(node('p','입력: '+value.input_label,'hint'));
        overview.append(node('p',value.origin==='external'?'외부 AI 결과 · 형식 확인됨 · 원문 검토 필요':`Gemma 4 E4B · 사고 ${value.inference?.thinking?'켜기':'끄기'} · 상세 검토·채팅 요약 생략`,'hint'));
        for(const note of value.notes||[])overview.append(node('p',note,'hint'));
        if(value.input_rejections?.length)overview.append(node('p',`입력 형식 확인 필요 ${value.input_rejections.length}개 · 원본은 보존됩니다.`,'hint'));
        items=value.items;
      }else if(value.scope==='full'){
        overview.append(node('h3',`전체 영상 00:00:00 ~ ${timecode(value.duration_ms)} · ${value.phase==='done'?'전체 범위 처리 종료':value.complete?'처리 완료':[7,8,9,10].includes(value.version)&&value.phase==='chat'?'채팅 설명 정리':value.phase==='grounding'?'요약 원문 대조':value.version>=6&&value.done===value.total?'처리 종료 · 확인 필요':'일부 처리'} · ${value.version>=6?'입력 처리':'요약'} ${value.done}/${value.total}`));
        if(value.broadcast_background)overview.append(node('p','분석에 사용한 방송 배경: '+value.broadcast_background,'hint'));
        overview.append(node('p',value.input_label?'분석에 사용한 데이터: '+value.input_label:'이전 결과 · 실행 당시 선택된 전사·화자 정보 사용','hint'));
        overview.append(node('p',(value.version===5?`상위 주제 ${value.topics.length}개 · 완료 이야기·장면 ${value.items.filter(r=>r.kind!=='topic').length}개`:`완료 문맥 ${value.items.filter(r=>!r.gap&&!r.failed&&r.grounding_state!=='pending'&&r.grounding_state!=='review').length}개`)+` · 채팅 보정 ${value.chat_offset_ms/1000}초 · ${value.model}${value.inference?' · 사고 '+(value.inference.thinking?'켜기':'끄기')+(value.version===10?' · 원본 보존 · 문맥 보완·발언 선별':' · 전사 자동 보정 없음'):''}`,'hint'));
        if(value.stats.speech_total!=null)overview.append(node('p',`발언 ${value.stats.speech_used}/${value.stats.speech_total}개 · `+(value.version===5?`제공 채팅 ${value.stats.chat_total}건`:`채팅 ${value.stats.chat_used}/${value.stats.chat_total}건 사용`),'hint'));
        if(value.version<6)overview.append(node('p',value.version===5?'이전 상위·하위 방식의 결과':'이전 문맥 처리 방식의 결과','hint'));
        if(value.pending_topic&&![7,8,9,10].includes(value.version)){const p=value.pending_topic;overview.append(node('p',`${timecode(p.start_ms)} ~ ${timecode(p.end_ms)} · 이어지는 주제: ${p.topic} · 주제 전환 또는 영상 끝에서 요약합니다.`,'hint'));}
        overview.append(node('p',`요약 사용 가능 ${value.items.filter(canCopyContext).length}개 · 요약 실패 ${value.items.filter(contextSummaryFailed).length}개 · 전사 없음 ${value.items.filter(r=>r.gap).length}구간`,'hint'));
        if(value.evidence_reviews)overview.append(node('p',`요약 근거 확인 필요 ${value.evidence_reviews}개 · 자동 재시도 없이 원문 검토가 필요합니다.`,'hint'));
        if(value.input_rejections?.length)overview.append(node('p',`자료 형식 확인 필요 ${value.input_rejections.length}개`,'hint'));
        if(value.version===10&&value.input_rejections?.length){
          const ledger=node('details','');ledger.append(node('summary','입력에서 제외한 자료·이유'));
          for(const row of value.input_rejections)ledger.append(node('p',`${row.id} · 원본 ${row.source_id} · ${Number.isFinite(row.start_ms)?timecode(row.start_ms):'시각 오류'} · ${row.reason}`));
          overview.append(ledger);
        }
        for(const note of value.notes)overview.append(node('p',note,'hint'));
        if(value.version>=6&&(value.item_failures||value.boundary_failures))overview.append(node('p',`요약 실패 ${value.item_failures}개 · 연결 확인 필요 ${value.boundary_failures}개. 이어하기로 실패 부분을 재검토할 수 있습니다.`,'hint'));
        if(!value.complete&&value.version<6)overview.append(node('p',`완료된 하위 요약부터 체크하여 댓글용으로 복사할 수 있습니다. ${value.reaction_failures?'반응 '+value.reaction_failures+'개는 분석 실패로 남아 있습니다. 이어하기로 재검토하세요.':'요약 완료 수와 반응 관계 분석 진행률은 별개입니다.'}`,'hint'));
        if(value.version===5&&value.pipeline_revision===4&&!value.complete)overview.append(node('p','이 정리 이어하기를 누르면 기존 결과를 보존하고 별도 복구 버전에서 계속합니다. 이야기 구조·완료 요약은 재사용하고 반응 관계는 새 방식으로 확인합니다.','hint'));
        if([7,8,9,10].includes(value.version))overview.append(node('p',`대사 중심 분석 · ${value.phase==='dialogue'?'대화 읽기':value.phase==='chat'?'채팅 설명 정리':value.phase==='grounding'?'요약 원문 대조':'처리 종료'} · 채팅 설명 확인 필요 ${value.chat_failures||0}개`,'hint'));
        items=[7,8,9,10].includes(value.version)&&value.pending_topic?[...value.items,value.pending_topic]:value.items;
      }else{
        overview.append(node('h3','이전에 보존한 선택 구간 요약'));
        items=[{start_ms:value.input.range.start_ms,end_ms:value.input.range.end_ms,input:value.input,summary:value.summary}];
      }
      const reactions=contextReactions(items,value.version>=6?(value.reaction_analysis?.reaction_index?value.reaction_analysis:analysis?.reaction_index&&!analysis.stale&&JSON.stringify(analysis.settings)===JSON.stringify(value.reaction_settings)?analysis:value.reaction_analysis||analysis):(analysis||value.reaction_analysis),value.chat_offset_ms??value.input?.range.chat_offset_ms??0,value.stale,value.duration_ms);
      await copy.setItems(reactions.items.flatMap(item=>[item,...(item.reactions||[])]),JSON.stringify([selected,value.id]),project.input?.start_vod_ms||0,{...identity(),run:value.id});
      if(request!==serial||project?.path!==selected)return;
      if(reactions.note)overview.append(node('p',reactions.note,'hint'));
      listItems=reactions.items;renderList(changed);
    }catch(error){if(request===serial)message(error.message);}
  }
  async function start(action,options){
    if(!project)return;const selected=project.path;message('');
    try{const value=await api('context-start',{...identity(),action,options});if(project?.path===selected){if(action!=='model')currentRun=null;onProject(value);}}
    catch(error){if(project?.path===selected)message(error.message);}
  }
  async function rejectInterpretation(change){
    if(!project||project.locked||!currentResult?.complete)return;
    const selected=project.path;
    try{
      const value=await api('context-reject-interpretation',{...identity(),run:currentResult.id,item:change.owner_id,part:change.part_id,interpretation:change.id});
      if(project?.path===selected){currentRun=null;onProject(value);}
    }catch(error){if(project?.path===selected)message(error.message);}
  }
  $('context-prepare').onclick=()=>start('model',{});
  $('context-generate').onclick=async()=>{const offset=$('context-offset').valueAsNumber;if(!Number.isFinite(offset)||Math.abs(offset)>600)return message('채팅 보정은 -600~600초로 입력하세요.');const options={chat_offset_ms:Math.round(offset*1000),thinking:$('context-thinking').checked,selection:inputs.selection()};if(viewMode==='timestamps'){if(inputs.ready())start('timestamps',options);return;}if(!inputs.ready()||!await background.save())return;start('whole',options);};
  $('context-resume').onclick=()=>start(currentResult?.mode==='timestamps'?'timestamps-resume':'resume',{run:currentRun});
  $('context-stop').onclick=async()=>{if(!project)return;const selected=project.path;try{const value=await api('context-stop',identity());if(project?.path===selected)onProject(value);}catch(error){message(error.message);}};
  $('context-open').onclick=()=>load($('context-version').value);
  $('context-min-reaction').onchange=()=>renderList(true);
  $('context-log').ontoggle=()=>{$('context-log-toggle').textContent=$('context-log').open?'처리 로그 닫기':'처리 로그 열기';};
  return {
    refresh(){if(project&&currentRun)load(currentRun);},
    openRun(id,mode){changeTab(mode);currentRun=id;selectedRuns[mode]=id;setVersions();},
    setProject(value){
      const changed=project?.path!==value?.path;project=value;inputs.setProject(value);background.setProject(value);
      if(changed){viewMode=modeOf(value?.context?.runs?.find(r=>r.id===value.context.run));selectedRuns.detail=null;selectedRuns.timestamps=null;thinking.detail=true;thinking.timestamps=false;serial++;key='';currentRun=null;currentResult=null;latestRun=null;listItems=[];copy.setItems([],'');$('context-min-reaction').value='0';renderList(true);$('context-log').open=false;$('context-overview').replaceChildren(node('p','문맥 결과를 열면 처리 내역이 표시됩니다.','hint'));$('context-offset').value='0';$('context-playing').textContent='목록의 ‘이 구간 재생’을 눌러 영상을 확인하세요.';message('');}
      const state=value?.context,p=state?.progress||{},model=state?.model;
      if(changed)$('context-thinking').checked=thinking[viewMode];setTabs();
      $('context-thinking').disabled=!value||value.locked;
      $('context-title').textContent=value?.metadata.title||'';
      $('context-prepare').disabled=!value||value.locked;$('context-stop').disabled=!state?.owned||state.state==='stopping';$('context-generate').disabled=!value||value.locked||!value.speech?.transcript?.complete||value.speech.stale;controls();
      $('context-model').textContent=model?`Gemma 4 E4B · ${model.ready?'모델 준비됨':'모델 준비 필요'} · ${model.engine?'엔진 포함/설치됨':'엔진 없음'}`:'';
      const finished=['complete','review'].includes(state?.state);
      const status=state?.state==='review'&&currentResult?.id===state.run&&currentResult.complete
        ?`문맥 처리 완료 · 근거 확인 필요 ${currentResult.evidence_reviews||0}개. 해당 항목의 초안·원문·원음을 확인하세요.`:state?.message||'';
      $('context-status').textContent=status+(!finished&&p.total!=null?` · ${p.done}/${p.total} 처리 단위`:'')+(state?.owned&&p.seconds!=null?` · 현재 단위 ${p.seconds}초 경과`:'')+(state?.action!=='model'&&state?.compute?.note?' · '+state.compute.note:'');
      const progress=$('context-progress');
      const percent=p.stage==='timestamps'&&p.total?Math.min(100,100*p.done/p.total):phaseProgress(p,finished,currentResult?.pipeline_revision,currentResult?.version);
      if(p.total_bytes)progress.value=Math.min(99,p.bytes/p.total_bytes*100);else if(percent!=null)progress.value=percent;else if(p.duration_ms)progress.value=p.processed_ms/p.duration_ms*100;else if(state?.owned)progress.removeAttribute('value');else progress.value=0;
      const next=JSON.stringify([value?.path,state?.run,state?.runs,p.stage,p.done,state?.state,value?.speech?.updated_at,value?.voices?.revision,value?.tasks.chat.state]);if(next===key)return;key=next;
      if(state?.run!==latestRun&&modeOf(state?.runs?.find(r=>r.id===state.run))===viewMode){currentRun=state?.run||null;}
      latestRun=state?.run;setVersions();
    }
  };
}
