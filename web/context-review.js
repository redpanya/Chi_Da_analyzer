import {contextKey} from './context-comment-model.js';
import {reviewStates,reviewState,reviewCounts,filterReviewed} from './context-review-model.js';

// 댓글 선택과 독립된 검토 기록이다. 다른 창의 revision은 덮어쓰지 않는다.
export function createCandidateReview({api,host,onChange}){
  const node=(tag,text='')=>{const el=document.createElement(tag);el.textContent=text;return el;};
  const bar=node('section');bar.className='candidate-review-bar';bar.setAttribute('aria-label','클립 후보 검토');
  const controls=node('div');controls.className='play-actions';
  const label=node('label','검토 '),filter=node('select');filter.setAttribute('aria-label','후보 검토 상태 필터');
  label.title='검토 상태·메모는 이 결과 버전에만 저장됩니다. 댓글 포함과 클립 담기 선택과는 별개입니다.';
  for(const [value,text] of [['all','전체'],...Object.entries(reviewStates)]){const option=node('option',text);option.value=value;filter.append(option);}
  filter.value='all';label.append(filter);
  const counts=node('span'),reload=node('button','↻');reload.type='button';reload.className='subtle';reload.title='검토 기록 새로고침';reload.setAttribute('aria-label','검토 기록 새로고침');
  const notice=node('p');notice.className='hint';notice.setAttribute('role','status');
  controls.append(label,counts,reload);bar.append(controls,notice);host.before(bar);
  let source=null,items=[],key='',sequence=0,saved={revision:0,items:{}},loading=false,saving=false,ready=false;
  const drafts=new Map(),opened=new Set();
  const noteKey=item=>JSON.stringify([key,contextKey(item)]);
  const storedNote=item=>Object.hasOwn(saved.notes||{},contextKey(item))?saved.notes[contextKey(item)]:'';
  function render(){
    const n=reviewCounts(items,saved.items);
    counts.textContent=`채택 ${n.accepted} · 보류 ${n.held} · 제외 ${n.excluded} · 미검토 ${n.unreviewed}`;
    reload.disabled=!source||loading||saving;filter.disabled=loading||!source;
    bar.hidden=!source;
  }
  async function load(){
    if(!source||saving)return;
    const token=++sequence,identity=source;loading=true;ready=false;notice.textContent='검토 기록을 불러오는 중…';render();onChange();
    try{
      const value=await api('context-review',identity);
      if(token!==sequence)return;
      if(!value||!Number.isInteger(value.revision)||!value.items)throw Error('검토 기록 형식을 확인하세요.');
      saved=value;ready=true;notice.textContent='';
    }catch(error){if(token===sequence)notice.textContent=`검토 기록을 불러오지 못했습니다 · ${error.message}`;}
    finally{if(token===sequence){loading=false;render();onChange();}}
  }
  async function change(item,status,note){
    if(!source||!ready||loading||saving)return;
    const token=sequence,identity=source,draftKey=noteKey(item); saving=true;notice.textContent='검토 기록 저장 중…';render();onChange();
    try{
      const value=await api('context-review-save',{...identity,change:{revision:saved.revision,item:contextKey(item),status,...(note===undefined?{}:{note})}});
      if(token!==sequence)return;
      saved=value;if(note!==undefined&&drafts.get(draftKey)===note)drafts.delete(draftKey);
      notice.textContent='검토 기록 저장됨';
    }catch(error){if(token===sequence){ready=false;notice.textContent=`저장하지 못했습니다 · ${error.message} · 검토 기록 새로고침 후 다시 선택하세요.`;}}
    finally{if(token===sequence){saving=false;render();onChange();}}
  }
  filter.onchange=()=>onChange(true);reload.onclick=load;render();
  return {
    addAction(button){controls.append(button);},
    setSource(project,run,values){
      items=values||[];
      const next=project&&run?JSON.stringify([project.path,run]):'';
      if(next!==key){
        key=next;sequence++;saved={revision:0,items:{}};ready=false;loading=false;saving=false;filter.value='all';
        source=next?{root:project.root,vod_id:project.vod_id,run}:null;
        if(source)void load();else{notice.textContent='';render();}
      }else render();
    },
    filtered(){return filterReviewed(items,saved.items,filter.value);},
    control(item){
      const label=node('label','후보 검토 ');label.className='candidate-review-control';
      const select=node('select');select.setAttribute('aria-label',`${item.title||'클립 후보'} 검토 상태`);
      select.dataset.reviewKey=contextKey(item);
      for(const [value,text] of Object.entries(reviewStates)){const option=node('option',text);option.value=value;select.append(option);}
      select.value=reviewState(saved.items,item);select.disabled=!ready||loading||saving;
      select.onchange=()=>change(item,select.value);label.append(select);return label;
    },
    memo(item){
      const draftKey=noteKey(item),details=node('details');details.className='candidate-review-memo';details.open=opened.has(draftKey);
      const summary=node('summary',storedNote(item)?'검토 메모 · 저장됨':'검토 메모');
      const label=node('label','나만의 검토 메모'),input=node('textarea');input.maxLength=1000;input.rows=3;
      input.value=drafts.has(draftKey)?drafts.get(draftKey):storedNote(item);input.dataset.reviewMemo=contextKey(item);
      input.setAttribute('aria-label',`${item.title||'클립 후보'} 검토 메모`);label.append(input);
      const state=node('p',drafts.has(draftKey)?'저장하지 않은 메모가 있습니다.':'이 메모는 AI 결과·댓글에 포함되지 않습니다.');state.className='hint';state.setAttribute('role','status');
      const save=node('button','메모 저장');save.type='button';save.className='secondary';save.disabled=!ready||loading||saving;
      input.oninput=()=>{drafts.set(draftKey,input.value);state.textContent='저장하지 않은 메모가 있습니다.';};
      save.onclick=()=>change(item,reviewState(saved.items,item),input.value);
      details.ontoggle=()=>{if(details.open)opened.add(draftKey);else opened.delete(draftKey);};
      details.append(summary,label,state,save);return details;
    },
    state:item=>reviewState(saved.items,item),
    reset(){this.setSource(null,null,[]);}
  };
}
