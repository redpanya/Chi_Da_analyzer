import assert from 'node:assert/strict';
import {bindCaptionSize} from '../web/studio-caption-size.js';
class Input extends EventTarget{
  constructor(value){super();this.value=value;this.min='14';this.max='40';this.message='';this.attrs={};}
  get valueAsNumber(){return this.value.trim()===''?NaN:Number(this.value);}
  get validity(){return {valid:!this.message};}
  setCustomValidity(s){this.message=s;}setAttribute(k,v){this.attrs[k]=v;}removeAttribute(k){delete this.attrs[k];}
}
const slider=new Input('22'),number=new Input(''),error={textContent:''};let changes=0;
slider.addEventListener('input',()=>changes++);const size=bindCaptionSize(slider,number,error);
assert.equal(number.value,'22');assert.equal(changes,0);
const input=value=>{number.value=value;number.dispatchEvent(new Event('input'));};
for(const value of ['14','40','26']){input(value);assert.equal(slider.value,value);assert.equal(size.valid(),true);}
for(const value of ['','abc','13','41','Infinity','26.5','34.682']){input(value);assert.equal(slider.value,'26');assert.equal(size.valid(),false);assert.match(error.textContent,/14~40.*정수/);}
slider.value='30';slider.dispatchEvent(new Event('input'));assert.equal(number.value,'30');assert.equal(size.valid(),true);assert.equal(error.textContent,'');
for(const [saved,expected] of [['37.25','37'],['34.682','35'],['26.5','27']]){slider.value=saved;size.sync();assert.equal(number.value,expected);assert.equal(slider.value,expected);assert.equal(size.valid(),true);}
console.log('글자 크기: 정수·슬라이더 동기화·상하한·소수 거절·빈 값·오류 복구·기존 소수 반올림 검사 통과');
