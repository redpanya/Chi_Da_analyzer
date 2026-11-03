"""구간마다 합성을 끝낸 뒤 연결한다. 서로 다른 비율은 첫 구간 캔버스 안에 보존한다."""
from . import clip_contract as contract, clip_captions as captions, clip_render as media
from . import studio_profiles, studio_decorations
from .source import check_cancel

def joined_options(options, size, canvas):
    """별도 ASS의 글자와 위치도 영상의 레터박스 좌표로 변환한다."""
    scale=min(canvas[0]/size[0],canvas[1]/size[1])
    x=(canvas[0]-size[0]*scale)/2+size[0]*(.5+options['caption_x']/100)*scale
    anchor={'bottom':.9,'center':.5,'top':.08}[options['position']]
    y=(canvas[1]-size[1]*scale)/2+size[1]*(anchor+options['caption_y']/100)*scale
    return options|{'font_size':options['font_size']*size[0]*scale/canvas[0],
                    'caption_x':(x/canvas[0]-.5)*100,'caption_y':(y/canvas[1]-anchor)*100}

def sidecars(folder, key, rows, clips, profiles, sizes, canvas, transition):
    starts,_,_=contract.offsets(clips,transition)
    work=folder/(key+'-sidecars');work.mkdir(exist_ok=True)
    all_cues=[];styles=[];events=[];header=''
    for i,(clip,options,size,start) in enumerate(zip(clips,profiles,sizes,starts)):
        cue,_=captions.cues(rows,[clip]);cue=[r|{'start_ms':round(r['start_ms']+start*1000),'end_ms':round(r['end_ms']+start*1000)} for r in cue]
        all_cues.extend(cue)
        captions.write(work,str(i),cue,canvas,joined_options(options,size,canvas))
        text=(work/(str(i)+'.ass')).read_text(encoding='utf-8-sig')
        header=text.split('Style:',1)[0]
        for line in text.splitlines():
            if line.startswith('Style: '):
                name,rest=line[7:].split(',',1);styles.append(f'Style: C{i}_{name},{rest}')
            elif line.startswith('Dialogue: '):
                fields=line.split(',',4);fields[3]=f'C{i}_'+fields[3];events.append(','.join(fields))
    captions.write(folder,key,sorted(all_cues,key=lambda c:(c['start_ms'],c['end_ms'])),canvas,profiles[0])
    (folder/(key+'.ass')).write_text(header+'\n'.join(styles)+'\n\n[Events]\nFormat: Layer, Start, End, Style, Text\n'+'\n'.join(events),encoding='utf-8-sig')

def render(folder,src,request,rows,stop,lock,update,completed):
    clips=request['clips'];profiles=studio_profiles.profiles(request);sizes=[contract.dimensions(src,o) for o in profiles]
    joined=request['options']['mode']=='joined';canvas=sizes[0];parts=[];overall=0
    def phase(index, start=0, weight=1):
        def report(**values):
            nonlocal overall
            if 'progress' in values:
                local=values.pop('progress');overall=max(overall,min(.99,(index+start+weight*local)/(len(clips)+int(joined))))
                values.update(progress=overall,phase_progress=local,phase_name='구간 연결·검사' if index==len(clips) else f'구간 {index+1}/{len(clips)} · 화면·자막·검사')
            update(**values)
        return report
    update(message='구간별 자막 문장 호환성 검사',progress=0)
    for i,(clip,options,size) in enumerate(zip(clips,profiles,sizes)):
        captions.preflight(rows,[clip],size,options,stop)
    def publish(key,file,group,opts,size,report):
        cue,total=captions.cues(rows,group,opts['transition'] if joined else 'cut')
        check=media.verify(file,total,stop,lock,report,opts['speed']=='fast')
        target=folder/(key+'.mp4');temp=folder/(key+'-publish.mp4')
        media.copy_media(file,temp,stop);temp.replace(target);assets={'video':target.name}
        if opts['sidecar'] and rows:
            if joined:sidecars(folder,key,rows,clips,profiles,sizes,canvas,opts['transition'])
            else:captions.write(folder,key,cue,size,opts)
            assets.update(srt=key+'.srt',ass=key+'.ass')
        completed[key]={'assets':assets,'verification':check,'file_identity':media.identity(target),
            'asset_identities':{k:media.identity(folder/n) for k,n in assets.items()},'title':'합친 영상' if joined else group[0]['title']}
        report(outputs=completed,progress=1)
    for key,value in completed.items():
        if not all((folder/n).is_file() for n in value['assets'].values()):raise ValueError('완성 출력이 이동되거나 삭제됐습니다. 새 작업으로 진행하세요')
    if joined and 'joined' in completed:return completed
    for i,(clip,options,size) in enumerate(zip(clips,profiles,sizes)):
        check_cancel(stop);key=f'clip-{i+1:03}';report=phase(i)
        if not joined and key in completed:continue
        report(message=f'{i+1}/{len(clips)} 구간 · 개별 화면·자막 적용',progress=0)
        part=folder/(key+'-profile.mp4');temp=folder/(key+'-working.mp4')
        length=(clip['end_ms']-clip['start_ms'])/1000
        if not part.exists():
            source=folder/(key+'-source.mp4')
            if not source.exists():media.encode(src,clip,options,temp,stop,lock,phase(i,0,.4));temp.replace(source)
            cue,_=captions.cues(rows,[clip])
            if (options['caption'] and cue) or options.get('image'):
                overlay=studio_decorations.prepare(src['project_path'],options,request.get('selection')) if options.get('image') else None
                media.burn(source,cue if options['caption'] else [],size,options,temp,length,stop,lock,phase(i,.4,.3),overlay)
                media.verify(temp,length,stop,lock,phase(i,.4,.3));temp.replace(part)
            else:media.copy_media(source,temp,stop);temp.replace(part)
        if joined and size!=canvas:
            normalized=folder/(key+'-canvas.mp4')
            if not normalized.exists():
                graph=media.fit('0:v:0','v',*canvas,'contain')
                media.command(['-i',str(part),'-filter_complex',graph,'-map','[v]','-map','0:a:0?',
                    '-c:v','libx264','-preset','veryfast','-crf','20','-c:a','copy','-video_track_timescale','15360','-movflags','+faststart',str(temp)],folder,key+'-canvas',stop,lock,phase(i,.7,.3),length)
                media.verify(temp,length,stop,lock,phase(i,.7,.3));temp.replace(normalized)
            part=normalized
        parts.append(part)
        if not joined:publish(key,part,[clip],options,size,phase(i,.7,.3))
        else:report(progress=1)
    if joined:
        result=folder/'joined-profile.mp4'
        if not result.exists():
            temp=folder/'joined-working.mp4';media.join(parts,clips,request['options'],temp,stop,lock,phase(len(clips)))
            media.verify(temp,contract.offsets(clips,request['options']['transition'])[2],stop,lock,phase(len(clips)));temp.replace(result)
        publish('joined',result,clips,request['options'],canvas,phase(len(clips)))
    return completed
