import assert from 'node:assert/strict';
import {imageGesture,imageRect} from '../web/studio-image-geometry.js';
const start={x:50,y:50,width:30,opacity:80,asset:'fixture'};
for(const frame of [{width:640,height:360},{width:360,height:640},{width:500,height:500}]){
  for(const aspect of [.2,1,3,10]){
    const moved=imageGesture(start,frame,aspect,'',frame.width*.1,frame.height*-.2);
    assert.equal(moved.x,60);assert.equal(moved.y,30);assert.equal(moved.width,30);
    assert.deepEqual(imageGesture(start,{width:frame.width*2,height:frame.height*2},aspect,'',frame.width*.2,frame.height*-.4),moved);
    for(const handle of ['nw','ne','sw','se']){
      const sx=handle.includes('e')?1:-1,sy=handle.includes('s')?1:-1;
      const resized=imageGesture(start,frame,aspect,handle,sx*frame.width*.08,sy*frame.width*.08/aspect);
      assert.ok(resized.width>30);assert.equal(resized.opacity,80);
      const a=imageRect(start,frame,aspect),b=imageRect(resized,frame,aspect);
      assert.ok(Math.abs(b.width/b.height-aspect)<1e-8);
      assert.ok(Math.abs((a.x+(sx<0?a.width:0))-(b.x+(sx<0?b.width:0)))<=frame.width*.003);
      assert.ok(Math.abs((a.y+(sy<0?a.height:0))-(b.y+(sy<0?b.height:0)))<=frame.height*.003);
      for(const delta of [-10000,10000]){
        const bounded=imageGesture({...start,x:0,y:100},frame,aspect,handle,delta,-delta);
        for(const key of ['x','y','width'])assert.ok(Number.isFinite(bounded[key])&&bounded[key]>=0&&bounded[key]<=100);
        assert.ok(bounded.width>=1);
      }
    }
  }
}
assert.deepEqual(start,{x:50,y:50,width:30,opacity:80,asset:'fixture'});
console.log('PNG 이동·네 모서리·비율·화면 배율·경계 제한 검증 통과');
