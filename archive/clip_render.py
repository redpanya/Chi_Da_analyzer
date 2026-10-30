"""구간별 비파괴 렌더링. 자막 이미지는 마지막 합성에서만 적용한다."""
import shutil
import os
from . import clip_contract as contract, clip_captions as captions
from .speech_media import process
from .source import check_cancel
from .video import probe
from .studio_space import available
from .studio_maintenance import identity


def copy_media(source,target,stop):
    """큰 파일도 취소 가능하며 완성본 이름으로 바로 쓰지 않는다."""
    check_cancel(stop)
    if not target.exists():
        try:os.link(source,target);return
        except OSError:pass
    with source.open('rb') as src,target.open('wb') as out:
        while block:=src.read(4*1024**2):
            check_cancel(stop);available(target.parent);out.write(block)


def command(args, folder, name, stop, lock, update, duration):
    check_cancel(stop)
    available(folder)
    progress=folder/(name+'.progress');log=folder/(name+'.log')
    def poll():
        available(folder)
        try:
            lines=progress.read_text(errors='replace').splitlines()
            times=[int(line.split('=',1)[1]) for line in lines if line.startswith('out_time_us=') and line.split('=',1)[1].lstrip('-').isdigit()]
            if times:update(progress=min(.99,max(0,times[-1]/1000000/max(.1,duration))))
        except OSError:pass
    process(['ffmpeg','-hide_banner','-nostdin','-y','-filter_complex_threads','1','-progress',str(progress),*args],log,stop,lock,poll)


def fit(label,out,w,h,mode='cover',x=50,y=50):
    if mode=='contain':return f'[{label}]scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1[{out}]'
    return f'[{label}]scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,crop={w}:{h}:(iw-ow)*{x/100}:(ih-oh)*{y/100},setsar=1[{out}]'


def encode(src,clip,options,target,stop,lock,update):
    start=(clip['start_ms']-src['origin'])/1000;length=(clip['end_ms']-clip['start_ms'])/1000
    args=['-ss',str(start),'-i',str(src['file'])]
    if options['speed']=='fast':
        args+=['-t',str(length),'-map','0:v:0','-map','0:a:0?','-c','copy','-avoid_negative_ts','make_zero','-movflags','+faststart',str(target)]
    else:
        w,h=contract.dimensions(src,options);parts=[]
        if options['layout']=='split':
            split=max(2,min(h-2,round(h*options['split']/100/2)*2));parts.append('[0:v:0]split=2[g][f]')
            for key,label,oh in [('game','g',split),('face','f',h-split)]:
                x,y,rw,rh=options[key]
                parts.append(f'[{label}]crop=trunc(iw*{rw/100}/2)*2:trunc(ih*{rh/100}/2)*2:trunc(iw*{x/100}/2)*2:trunc(ih*{y/100}/2)*2[{label}c]')
                parts.append(fit(label+'c',label+'o',w,oh))
            parts.append('[go][fo]vstack=inputs=2[framed]')
        else:parts.append(fit('0:v:0','framed',w,h,options['fit'],options['x'],options['y']))
        fx=f"fps=30,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS,eq=brightness={options['brightness']}:contrast={options['contrast']}:saturation={options['saturation']}"
        fade=min(options['fade'],length/2)
        if fade:fx+=f',fade=t=in:d={fade},fade=t=out:st={length-fade}:d={fade}'
        parts.append('[framed]'+fx+'[v]')
        if not src['audio']:args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
        a='0:a:0' if src['audio'] else '1:a:0'
        parts.append(f'[{a}]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS,volume={options["volume"]/100},apad[a]')
        args+=['-filter_complex',';'.join(parts),'-map','[v]','-map','[a]','-t',str(length),'-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-b:a','160k','-movflags','+faststart',str(target)]
    command(args,target.parent,target.stem,stop,lock,update,length)
    return verify(target,length,stop,lock,update,fast=options['speed']=='fast')


def verify(file,duration,stop,lock,update,fast=False):
    value=probe(file);actual=float(value['format']['duration'])
    if not fast and abs(actual-duration)>.15:raise ValueError('출력 영상의 길이가 요청 범위와 다릅니다')
    if fast and abs(actual-duration)>10:raise ValueError('키프레임 간격이 너무 큽니다. 정확한 저장으로 다시 진행하세요')
    command(['-v','error','-xerror','-i',str(file),'-map','0:v:0','-map','0:a:0?','-f','null','-'],file.parent,file.stem+'-check',stop,lock,update,actual)
    return {'duration':actual,'bytes':file.stat().st_size,'approximate':fast,'expected_duration':duration}


def join(files,clips,options,target,stop,lock,update):
    starts,overlaps,total=contract.offsets(clips,options['transition'])
    if options['transition']=='cut':
        listing=target.parent/'join.ffconcat';listing.write_text('ffconcat version 1.0\n'+'\n'.join(f"file '{p.name}'\nduration {(c['end_ms']-c['start_ms'])/1000:.3f}" for p,c in zip(files,clips))+'\n')
        args=['-f','concat','-safe','1','-i',str(listing),'-t',str(total),'-c','copy','-movflags','+faststart',str(target)]
    else:
        # 두 영상씩 합성해 긴 목록에서도 파일/디코더를 한꺼번에 열지 않는다.
        current=files[0]
        for i in range(1,len(files)):
            check_cancel(stop);out=target if i==len(files)-1 else target.parent/f'join-{i:03}.mp4'
            d=overlaps[i-1];at=starts[i]
            graph=f'[0:v]settb=AVTB,setpts=PTS-STARTPTS[v0];[1:v]settb=AVTB,setpts=PTS-STARTPTS[v1];[v0][v1]xfade=transition=fade:duration={d}:offset={at}[v];[0:a][1:a]acrossfade=d={d}[a]'
            length=at+(clips[i]['end_ms']-clips[i]['start_ms'])/1000
            command(['-i',str(current),'-i',str(files[i]),'-filter_complex',graph,'-map','[v]','-map','[a]','-t',str(length),'-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-movflags','+faststart',str(out)],out.parent,out.stem,stop,lock,update,length)
            if current.name.startswith('join-'):current.unlink()
            current=out
        if len(files)==1:copy_media(files[0],target,stop)
        return total
    command(args,target.parent,'join',stop,lock,update,total);return total


def burn(file,rows,size,options,target,total,stop,lock,update,overlay=None):
    listing=captions.images(target.parent/(target.stem+'-captions'),rows,size,options,total,stop,overlay=overlay)
    command(['-i',str(file),'-f','concat','-safe','0','-i',str(listing),'-filter_complex','[0:v][1:v]overlay=eof_action=pass:repeatlast=0:format=auto,format=yuv420p[v]',
             '-map','[v]','-map','0:a:0?','-c:v','libx264','-preset','veryfast','-crf','20','-r','30','-c:a','copy','-t',str(total),'-movflags','+faststart',str(target)],target.parent,target.stem,stop,lock,update,total)


def render(folder,src,request,rows,stop,lock,update,completed):
    clips=request['clips'];opts=request['options'];size=contract.dimensions(src,opts);parts=[]
    update(message='선택 구간의 실제 자막 문장 호환성 검사',progress=0)
    captions.preflight(rows,clips,size,opts,stop)
    report=update;overall=0
    def phase(label,base,weight):
        def send(**values):
            nonlocal overall
            if 'progress' in values:
                local=values.pop('progress');overall=max(overall,min(.99,base+weight*local));values.update(progress=overall,phase_progress=local,phase_name=label)
            report(**values)
        return send
    for i,clip in enumerate(clips):
        key=f'clip-{i+1:03}';part=folder/(key+'-source.mp4')
        update=phase(f'구간 {i+1}/{len(clips)} · 영상 처리·검사',.3*i/len(clips),.3/len(clips))
        update(message=f'{i+1}/{len(clips)} 구간 영상 처리',progress=0)
        if not part.exists():
            temp=folder/(key+'-working.mp4');encode(src,clip,opts,temp,stop,lock,update);temp.replace(part)
        parts.append(part)
    groups=[(f'clip-{i+1:03}',[c],p) for i,(c,p) in enumerate(zip(clips,parts))]
    if opts['mode']=='joined':
        update=phase('구간 연결',.3,.1)
        joined=folder/'joined-source.mp4'
        if not joined.exists():
            temp=folder/'joined-working.mp4';join(parts,clips,opts,temp,stop,lock,update);temp.replace(joined)
        groups=[('joined',clips,joined)]
    for j,(key,group,file) in enumerate(groups):
        update=phase(f'출력 {j+1}/{len(groups)} · 자막·최종 검사',.4+.6*j/len(groups),.6/len(groups))
        if key in completed:
            if not all((folder/name).is_file() for name in completed[key]['assets'].values()):raise ValueError('완성 출력이 이동되거나 삭제됐습니다. 다른 결과를 보존하려면 새 영상 생성으로 진행하세요')
            continue
        cue,total=captions.cues(rows,group,opts['transition'] if opts['mode']=='joined' else 'cut')
        update(message=key+' 자막·출력 검사',progress=0)
        temp=folder/(key+'-final-working.mp4');target=folder/(key+'.mp4')
        if (opts['caption'] and cue) or opts.get('image'):
            burn(file,cue if opts['caption'] else [],size,opts,temp,total,stop,lock,update,src.get('overlay'))
        else:copy_media(file,temp,stop)
        check=verify(temp,total,stop,lock,update,opts['speed']=='fast');temp.replace(target)
        assets={'video':target.name}
        if opts['sidecar'] and rows:
            captions.write(folder,key,cue,size,opts);assets.update(srt=key+'.srt',ass=key+'.ass')
        completed[key]={'assets':assets,'verification':check,'file_identity':identity(target),'asset_identities':{k:identity(folder/n) for k,n in assets.items()},'title':group[0]['title'] if len(group)==1 else '합친 영상'}
        update(outputs=completed)
    return completed
