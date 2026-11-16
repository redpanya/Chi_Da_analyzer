"""믹스의 현재 구간 편집과 구간별 프리셋을 하나의 초안으로 저장한다."""
from contextlib import ExitStack
from . import studio_images, analysis_inputs, caption_design, caption_styles, clip_captions, clip_contract, studio_profiles
from .storage import Conflict, ProjectLock, load_project
from . import mix_clips as mix


SNAPSHOT = 'mix-snapshot'


def original(item):
    return item.get('source_clip', item['clip'])


def caption_snapshot(item):
    if 'source_captions' in item:
        return item['source_captions']
    start = original(item)['start_ms']
    return [dict(id=str(i), start_ms=start+row['start_ms'], end_ms=start+row['end_ms'], text=row['text'])
            for i, row in enumerate(item['captions'])]


def edit_request(item, inputs):
    snapshot = caption_snapshot(item)
    stored = item.get('editor', {})
    selection = stored.get('selection', {'transcript_run':SNAPSHOT,'speaker_run':None} if snapshot else None)
    if snapshot and selection and selection['transcript_run'] != SNAPSHOT and not any(
            row['id'] == selection['transcript_run'] and row['complete'] for row in inputs['transcripts']):
        selection = {'transcript_run':SNAPSHOT,'speaker_run':None}
        stored = stored | {'caption_versions':stored.get('caption_versions', {}) | {SNAPSHOT:stored.get('caption_edits', {})}}
    return {**stored,'selection':selection,'clips':[item['clip'] | {'id':item['key']}],'options':item['options']}


def updated_item(path, src, item, raw, preset_source=None):
    snapshot = caption_snapshot(item)
    request = clip_contract.validate(raw, src, draft=True)
    if len(request['clips']) != 1 or request['clips'][0]['id'] != item['key']:
        raise ValueError('현재 믹스 구간 하나를 선택하세요')
    clip = request['clips'][0]
    opts = studio_profiles.effective(request, clip)
    if opts['mode'] != 'joined' or opts['speed'] != 'exact' or opts['sidecar']:
        raise ValueError('믹스는 한 개의 MP4로 저장합니다')
    image = opts.get('image')
    if preset_source and image and not studio_images.location(path,image['asset']).exists():
        studio_images.copy_asset(preset_source,path,image)
    studio_profiles.prepare(path, request)
    opts = studio_profiles.effective(request, clip)
    if preset_source and (not opts['caption'] or item['options']['caption']):
        updated = item | {'options':opts}
        if item['options']['caption'] and not opts['caption']:
            updated.update(source_captions=snapshot, captions=[])
        return updated, opts
    selection = request['selection']
    if selection == {'transcript_run':SNAPSHOT, 'speaker_run':None}:
        if not snapshot:
            raise ValueError('이 구간에 담은 자막이 없습니다')
        rows = [r | {'text':request['caption_edits'].get(r['id'],r['text'])} for r in snapshot]
    else:
        rows = clip_captions.snapshot(path, item['vod_id'], selection, request['caption_edits'])
        if selection:
            snapshot = [r for r in rows if r['start_ms'] < clip['end_ms'] and r['end_ms'] > clip['start_ms']]
    if opts['caption'] and not rows:
        raise ValueError('자막을 입히려면 사용할 전사를 선택하세요')
    cues, _ = clip_captions.cues(rows,[clip])
    settings = {k:request[k] for k in ('selection','caption_edits','caption_versions','range_drafts')}
    updated = item | {'source_clip':original(item), 'source_captions':snapshot, 'editor':settings,
                      'clip':{k:clip[k] for k in ('title','start_ms','end_ms')} | {'id':item['clip']['id']},
                      'options':opts | {'size':item['options']['size'],'transition':'cut'}, 'captions':cues if opts['caption'] else []}
    return updated, opts


def dispatch(folder, value, action, data):
    items = {row['key']:row for row in value['items']}
    key = data.get('key')
    if not isinstance(key,str) or key not in items:
        raise Conflict('믹스 목록에서 편집할 구간을 다시 선택하세요')
    active = items[key]
    path = mix.source_path(folder, active['scope'], active['vod_id'])
    global_size = value.get('size',value['items'][0]['options']['size'])
    if action == 'editor':
        load_project(path,active['vod_id'])
        with ProjectLock(path,read=['media','studio-images','speech','voices']):
            src = clip_contract.media(path, active['vod_id'])
            mix.same_source(active,(src['identity'], src['origin'], src['file']))
            inputs = analysis_inputs.catalog(path)
            snapshot = caption_snapshot(active)
            if snapshot:
                inputs['transcripts'].insert(0, {'id':SNAPSHOT, 'label':'믹스에 담은 자막','complete':True})
            request = edit_request(active,inputs)
            request['options'] = request['options'] | {'size':global_size,'transition':value.get('transition','cut')}
            project = {'root':str(path.parent),'vod_id':active['vod_id'],'metadata':src['data']['metadata'],
                       'input':{'start_vod_ms':src['origin']},'duration_ms':src['duration']}
            defaults = clip_contract.default_options()
            profiles = {k:{p:row['options'].get(p,defaults[p]) for p in studio_profiles.CLIP_KEYS}
                        for k,row in items.items() if k!=key}
            return mix.info(folder, value) | {'project':project,'original':original(active),
                'profiles':profiles,
                'caption_rows':snapshot,'inputs':inputs,'caption_designs':caption_design.catalog(caption_styles.PRESETS),
                'draft':{'revision':value['revision'],'request':request}}

    changes = data.get('profiles', {})
    if not isinstance(changes,dict) or key in changes or changes.keys()-items.keys():
        raise ValueError('프리셋을 적용할 믹스 구간을 다시 선택하세요')
    for settings in changes.values():
        if not isinstance(settings,dict) or settings.keys()-studio_profiles.CLIP_KEYS:
            raise ValueError('프리셋의 구간별 편집 설정을 확인하세요')
    targets = list(changes)
    if data.get('request') is not None:
        targets.append(key)
    dirty = False
    with ExitStack() as locks:
        sources = {}
        image_paths = {mix.source_path(folder,items[k]['scope'],items[k]['vod_id']) for k in changes if changes[k].get('image')}
        if image_paths and path not in image_paths:
            load_project(path,active['vod_id'])
            locks.enter_context(ProjectLock(path,read=['studio-images']))
        for k in targets:
            row = items[k]
            target = mix.source_path(folder,row['scope'],row['vod_id'])
            try:
                if target not in sources:
                    load_project(target,row['vod_id'])
                    locks.enter_context(ProjectLock(target,read=['media','speech','voices','studio-images'],
                                                    write=['studio-images'] if target in image_paths else []))
                    sources[target] = (clip_contract.media(target,row['vod_id']),{})
                src,cache = sources[target]
                mix.same_source(row,(src['identity'],src['origin'],src['file']))
                if k == key:
                    raw = data['request']
                else:
                    options = row['options'] | changes[k]
                    raw = {'clips':[row['clip'] | {'id':k}]}
                    if options['caption'] and not row['options']['caption']:
                        if 'inputs' not in cache:
                            cache['inputs'] = analysis_inputs.catalog(target)
                        raw = edit_request(row,cache['inputs'])
                        if not raw['selection']:
                            run = SNAPSHOT if caption_snapshot(row) else next(
                                (t['id'] for t in cache['inputs']['transcripts'] if t['complete']),None)
                            if run:
                                raw['selection'] = {'transcript_run':run,'speaker_run':None}
                    raw['options'] = options
                updated,opts = updated_item(target,src,row,raw,path if k!=key else None)
                if k == key:
                    if global_size != opts['size']:
                        value['size'] = opts['size']
                        dirty = True
                    if value.get('transition','cut') != opts['transition']:
                        value['transition'] = opts['transition']
                        dirty = True
                if updated != row:
                    row.update(updated)
                    dirty = True
            except (ValueError,OSError) as error:
                if k == key:
                    raise
                kind = Conflict if isinstance(error,Conflict) else ValueError
                raise kind(f"{row['clip']['title']} ({row['broadcast']}) / {error}") from error
        if dirty:
            mix.persist(folder,value)
    return {'revision':value['revision'],'version':mix.render_version(value)}
