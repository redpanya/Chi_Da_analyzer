export function createEditUndo(onChange=()=>{}){
  let entry=null;
  return {
    record(label,restore){entry={label,restore};onChange(label);},
    clear(){entry=null;onChange('');},
    label:()=>entry?.label||'',
    undo(){if(!entry)return false;const saved=entry;entry=null;onChange('');saved.restore();return true;},
  };
}
export function captureProfileOptions(rows){
  const saved=rows.map(row=>({row,has:Object.hasOwn(row,'options'),options:structuredClone(row.options)}));
  return ()=>{for(const {row,has,options} of saved){if(has)row.options=structuredClone(options);else delete row.options;}};
}
