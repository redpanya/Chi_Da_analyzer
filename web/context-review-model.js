import {contextKey} from './context-comment-model.js';

export const reviewStates=Object.freeze({unreviewed:'미검토',accepted:'채택',held:'보류',excluded:'제외'});
export function reviewState(records,item){
  const key=contextKey(item),value=Object.hasOwn(records||{},key)?records[key]:null;
  return Object.hasOwn(reviewStates,value)?value:'unreviewed';
}
export function reviewCounts(items,records){
  const counts={unreviewed:0,accepted:0,held:0,excluded:0};
  for(const item of items)counts[reviewState(records,item)]++;
  return counts;
}
export function filterReviewed(items,records,filter){
  return Object.hasOwn(reviewStates,filter)?items.filter(item=>reviewState(records,item)===filter):items;
}
