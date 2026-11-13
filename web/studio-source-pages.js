export function sourcePage(rows,page=0,size=50,revealId=null){
  const pages=Math.max(1,Math.ceil(rows.length/size));
  const index=revealId===null?-1:rows.findIndex(row=>row.id===revealId);
  const selected=Math.max(0,Math.min(pages-1,index<0?page:Math.floor(index/size)));
  return {page:selected,pages,total:rows.length,rows:rows.slice(selected*size,(selected+1)*size)};
}
