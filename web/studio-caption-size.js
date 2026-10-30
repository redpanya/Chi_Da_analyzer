// 저장값은 기존 슬라이더 한 곳에서 읽고, 잘못 입력 중인 숫자는 적용하지 않는다.
export function bindCaptionSize(slider,input,error){
  const message=`글자 크기는 ${slider.min}~${slider.max} 사이의 정수로 입력하세요.`;
  function sync(){slider.value=String(Math.round(Number(slider.value)));input.value=slider.value;input.setCustomValidity('');input.removeAttribute('aria-invalid');error.textContent='';}
  input.addEventListener('input',()=>{
    const value=input.valueAsNumber,valid=Number.isInteger(value)&&value>=Number(slider.min)&&value<=Number(slider.max);
    input.setCustomValidity(valid?'':message);input.setAttribute('aria-invalid',String(!valid));error.textContent=valid?'':message;
    if(valid){slider.value=String(value);slider.dispatchEvent(new Event('input',{bubbles:true}));}
  });
  input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();input.reportValidity();}});
  slider.addEventListener('input',sync);sync();
  return {sync,valid:()=>input.validity.valid};
}
