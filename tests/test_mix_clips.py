"""여러 VOD의 독립 초안, 원본 확인, 편집 순서 출력 검증."""
from array import array
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import base64
import hashlib
import io
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from archive import mix_clips, studio_images, studio_jobs
from archive.jobs import Manager
from archive.storage import Conflict, ProjectLock, create_or_load, read_json, save_json


class MixClipsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.mix = mix_clips.MixClips()
        self.addCleanup(self.mix.close)
        self.folder = mix_clips.workspace(str(self.root))

    def call(self, action, **data):
        return self.mix.dispatch(action, {'library_root':str(self.root), **data})

    def source(self, root, vod, color, origin=0, frequency=None):
        path = root/f'vod-{vod}'
        with ProjectLock(path):
            data = create_or_load(path, {'id':vod,'title':color,'formats':[{'id':'test'}]}, 'test')
        file = path/'original.mp4'
        size = '160x90' if color=='red' else '90x160'
        audio = ['-f','lavfi','-i',f'sine=frequency={frequency}:sample_rate=48000:duration=2'] if frequency else []
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color={color}:s={size}:r=30:d=2',*audio,
                        '-c:v','libx264',str(file)],check=True)
        data['input'] = {'start_vod_ms':origin}
        data['tasks']['video'].update(state='complete',assets={'playback':file.name})
        save_json(path/'project.json',data)
        clip = {'id':'장면','title':color,'start_ms':origin+300,'end_ms':origin+1100}
        basket = path/'studio'/'draft.json'
        save_json(basket, {'revision':1,'request':{'clips':[clip]}})
        return file, basket

    def test_two_sources_and_range_in_same_library(self):
        vod = '101'
        scope = self.root/'.download-ranges'/('e'*32)
        first = self.source(self.root,vod,'red')
        second = self.source(scope,vod,'blue',90000)
        before = [hashlib.sha256(f.read_bytes()).digest() for f in (*first,*second)]
        self.assertEqual(mix_clips.workspace(str(scope)), self.folder)
        for root in (self.root,scope):
            self.assertEqual(self.call('send',root=str(root),vod_id=vod,revision=1)['added'],1)
        self.assertEqual(self.call('send',root=str(self.root),vod_id=vod,revision=1),{'added':0,'duplicates':1})
        value = self.call('info')
        self.assertEqual([i['origin'] for i in value['items']], [0,90000])
        self.assertEqual([i['preview_key'] for i in value['items']], [i['key'] for i in value['items']])
        blue = value['items'][1]['key']
        reordered = self.call('move',revision=value['revision'],key=blue,direction=-1)
        with self.assertRaises(Conflict):
            self.call('remove',revision=value['revision'],key=blue)
        self.assertEqual(reordered['items'][0]['title'],'blue')
        self.call('render',revision=reordered['revision'])
        self.mix.jobs[self.folder]['thread'].join(30)
        job = self.call('status',version=reordered['version'])
        self.assertEqual(job['state'],'complete',job)
        file = job['file']
        for t, channel in (('0.4',2),('1.2',0)):
            pixel = subprocess.check_output(['ffmpeg','-v','error','-ss',t,'-i',file,'-vf',
                                             'crop=2:2:iw/2:ih/2,scale=1:1','-frames:v','1',
                                             '-f','rawvideo','-pix_fmt','rgb24','-'])
            self.assertGreater(pixel[channel],240)
        self.assertEqual(before,[hashlib.sha256(f.read_bytes()).digest() for f in (*first,*second)])
        second[0].rename(second[0].with_suffix('.bak'))
        self.assertTrue(self.call('info')['items'][0]['problem'])
        with self.assertRaises(Conflict):
            self.call('render',revision=reordered['revision'])
        trimmed = self.call('remove',revision=reordered['revision'],key=blue)
        self.assertEqual([i['title'] for i in trimmed['items']],['red'])
        self.assertTrue(Path(file).is_file())
        self.assertTrue(second[1].is_file())
        with self.assertRaises(Conflict):
            self.call('clear', revision=reordered['revision'])
        self.assertEqual(self.call('clear',revision=trimmed['revision'])['items'],[])
        self.assertEqual(before[1],hashlib.sha256(first[1].read_bytes()).digest())
        self.assertEqual(before[3],hashlib.sha256(second[1].read_bytes()).digest())
        with patch('archive.processes.open_folder') as opener:
            self.call('open-folder', version=reordered['version'])
            opener.assert_called_once_with(Path(file).parent)
            with self.assertRaises(FileNotFoundError):
                self.call('open-folder', version=trimmed['version'])

    def test_preview_uses_one_verified_key_for_clips_from_one_file(self):
        _, basket = self.source(self.root, '101', 'red')
        request = read_json(basket)
        clips = request['request']['clips']
        clips.append(clips[0] | {'id':'다음', 'start_ms':1200, 'end_ms':1500})
        save_json(basket, request)
        self.call('send', root=str(self.root), vod_id='101', revision=1)
        first, second = self.call('info')['items']
        self.assertNotEqual(first['key'], second['key'])
        self.assertEqual(first['preview_key'], second['preview_key'])
        value = mix_clips.draft(self.folder)
        value['items'][0]['source']['bytes'] = 0
        first, second = mix_clips.info(self.folder, value)['items']
        self.assertTrue(first['problem'])
        self.assertEqual(second['preview_key'], second['key'])

    def test_move_to_nonadjacent_position(self):
        for vod in ('101','102','103'):
            self.source(self.root,vod,'red')
            self.call('send',root=str(self.root),vod_id=vod,revision=1)
        value=self.call('info')
        args={'revision':value['revision'],'key':value['items'][2]['key']}
        for invalid in (-1,3,False):
            with self.assertRaises(ValueError):
                self.call('move',**args,to_index=invalid)
        self.call('move',**args,to_index=0)
        self.assertEqual([r['vod_id'] for r in self.call('info')['items']],['103','101','102'])

    def test_editor_saves_one_copy_and_retimes_captions(self):
        first = self.source(self.root, '101', 'red')
        second = self.source(self.root, '102', 'blue')
        originals = [p.read_bytes() for p in (*first, *second)]
        for vod in ('101', '102'):
            self.call('send', root=str(self.root), vod_id=vod, revision=1)
        value = mix_clips.draft(self.folder)
        red, blue = value['items']
        red['captions'] = [dict(start_ms=150, end_ms=650, text='Original')]
        red['options']['caption'] = True
        mix_clips.persist(self.folder, value)
        view = self.call('editor', key=red['key'])
        req = view['draft']['request']
        self.assertEqual(view['original']['start_ms'], 300)
        self.assertEqual(view['caption_rows'][0]['start_ms'], 450)
        self.assertEqual(req['selection']['transcript_run'], 'mix-snapshot')
        req['clips'][0].update(title='편집본', start_ms=550, end_ms=1500, options={'ratio':'1:1'})
        req['options'].update(transition='fade', size='720')
        req['caption_edits'] = {'0':'Edited'}
        saved = self.call('edit', revision=view['revision'], key=red['key'], request=req)
        changed = mix_clips.draft(self.folder)
        self.assertEqual(changed['items'][1], blue)
        edited = changed['items'][0]
        self.assertEqual(edited['options']['ratio'], '1:1')
        self.assertEqual(edited['captions'], [dict(start_ms=0, end_ms=400, text='Edited')])
        self.assertEqual(self.call('send', root=str(self.root), vod_id='101', revision=1)['duplicates'], 1)
        self.assertEqual(self.call('editor', key=red['key'])['original'], red['clip'])
        self.assertEqual(self.call('editor', key=blue['key'])['draft']['request']['options']['size'], '720')
        self.assertEqual(self.call('edit', revision=saved['revision'], key=red['key'], request=req), saved)
        with self.assertRaises(Conflict):
            self.call('edit', revision=view['revision'], key=red['key'], request=req)
        with self.assertRaises(ValueError):
            self.call('edit', revision=saved['revision'], key=blue['key'], request=req)
        self.call('render',revision=saved['revision'])
        self.mix.jobs[self.folder]['thread'].join(45)
        job = self.call('status',version=saved['version'])
        self.assertEqual(job['state'], 'complete', job)
        meta = subprocess.check_output(['ffprobe', '-v','error','-select_streams','v:0',
            '-show_entries','stream=width,height','-of','csv=p=0',job['file']],text=True).strip()
        self.assertEqual(meta, '720,720')
        self.assertEqual(originals, [p.read_bytes() for p in (*first, *second)])

    def test_vod_and_mix_can_save_independent_edits_at_the_same_time(self):
        _, basket = self.source(self.root, '101', 'red')
        project = {'root':str(self.root), 'vod_id':'101'}
        self.call('send', **project, revision=1)
        key = self.call('info')['items'][0]['key']
        mix = self.call('editor', key=key)
        vod_request = read_json(basket)['request']
        vod_request['clips'][0]['title'] = '보관함 편집본'
        mix_request = mix['draft']['request']
        mix_request['clips'][0]['title'] = '믹스 편집본'
        manager = Manager(self.root)
        self.addCleanup(manager.close)
        entered, release = Event(), Event()
        save = studio_jobs.save_draft
        def hold_save(*args):
            entered.set()
            self.assertTrue(release.wait(10))
            return save(*args)
        with patch.object(studio_jobs, 'save_draft', side_effect=hold_save), ThreadPoolExecutor(1) as pool:
            worker = pool.submit(manager.studio.dispatch, 'draft', project | {'revision':1,'request':vod_request})
            try:
                self.assertTrue(entered.wait(10))
                self.call('edit', revision=mix['revision'], key=key, request=mix_request)
                with self.assertRaises(Conflict):
                    self.call('send', **project, revision=1)
            finally:
                release.set()
            worker.result(10)
        self.assertEqual(read_json(basket)['request']['clips'][0]['title'], '보관함 편집본')
        self.assertEqual(self.call('info')['items'][0]['title'], '믹스 편집본')

    def test_batch_profiles_use_each_mix_item_and_save_together(self):
        originals = {}
        for vod,color in [('101','red'),('102','blue'),('103','green')]:
            for file in self.source(self.root,vod,color):
                originals[file] = file.read_bytes()
            self.call('send',root=str(self.root),vod_id=vod,revision=1)
        draft = mix_clips.draft(self.folder)
        red,blue,green = draft['items']
        # 원본 클립 식별자가 같은 세 방송에서도 믹스 구간별로 적용한다.
        self.assertEqual(len({r['clip']['id'] for r in draft['items']}),1)
        draft_file = self.folder/'초안.json'
        before = draft_file.read_bytes()
        with self.assertRaisesRegex(ValueError,'green'):
            self.call('edit',revision=draft['revision'],key=red['key'],
                      profiles={blue['key']:{'volume':25},green['key']:{'caption':True}})
        self.assertEqual(draft_file.read_bytes(),before)
        for row in (blue,green):
            row['source_captions'] = [dict(id='1',start_ms=400,end_ms=600,text=row['broadcast'])]
            row['editor'] = {'selection':None}
        mix_clips.persist(self.folder,draft)
        view = self.call('editor',key=red['key'])
        self.assertEqual(set(view['profiles']),{blue['key'],green['key']})
        save = dict(revision=view['revision'],key=red['key'],request=None)
        before = draft_file.read_bytes()
        for invalid in ({green['key']:{'ratio':'invalid'}}, {green['key']:{'size':'720'}}, {'없는 구간':{}}):
            with self.assertRaises(ValueError):
                self.call('edit',**save,profiles={blue['key']:{'volume':25}} | invalid)
            self.assertEqual(draft_file.read_bytes(),before)
        png = io.BytesIO()
        Image.new('RGBA',(8,8),'white').save(png,format='PNG')
        asset = studio_images.add(self.root/'vod-101',base64.b64encode(png.getvalue()).decode(),'장식.png')
        image = dict(asset=asset['asset'],name=asset['name'],x=50,y=50,width=25,opacity=100)
        preset = {'ratio':'1:1','volume':55,'caption':True,'image':image}
        selected = {r['key']:preset for r in (blue,green)}
        saved = self.call('edit',**save,profiles=selected)
        with self.assertRaises(Conflict):
            self.call('edit',**save,profiles=selected)
        first,*others = mix_clips.draft(self.folder)['items']
        self.assertEqual(first,red)
        for row in others:
            self.assertEqual({k:row['options'][k] for k in preset},preset)
            self.assertEqual(row['captions'],[dict(start_ms=100,end_ms=300,text=row['broadcast'])])
            self.assertEqual(studio_images.load(self.root/('vod-'+row['vod_id']),image).size,(8,8))
        current = view['draft']['request']
        current['clips'][0]['options'] = {'ratio':'4:5'}
        self.call('edit',key=red['key'],revision=saved['revision'],request=current)
        rows = mix_clips.draft(self.folder)['items']
        self.assertEqual([r['options']['ratio'] for r in rows],['4:5','1:1','1:1'])
        self.assertEqual(rows[1:],others)
        self.assertTrue(all(file.read_bytes()==content for file,content in originals.items()))

    def test_deleted_transcript_uses_saved_mix_captions(self):
        self.source(self.root, '101', 'red')
        self.call('send', root=str(self.root), vod_id='101', revision=1)
        key = self.call('info')['items'][0]['key']
        view = self.call('editor', key=key)
        req = view['draft']['request']
        req['selection'] = {'transcript_run':'a'*32, 'speaker_run':None}
        req['options']['caption'] = True
        rows = [dict(id='a', start_ms=0, end_ms=500, text='saved'),
                dict(id='b', start_ms=1700, end_ms=1800, text='later')]
        with patch('archive.clip_captions.snapshot', return_value=rows):
            self.call('edit', revision=view['revision'], key=key, request=req)
        reopened = self.call('editor', key=key)
        self.assertEqual(reopened['caption_rows'], rows[:1])
        self.assertEqual(reopened['draft']['request']['selection']['transcript_run'], 'mix-snapshot')
        self.call('edit', revision=reopened['revision'], key=key, request=reopened['draft']['request'])
        self.assertEqual(mix_clips.draft(self.folder)['items'][0]['captions'][0]['text'], 'saved')

    def test_dissolve_keeps_pcm_through_joins_and_preserves_older_output(self):
        for vod,color,tone in [('101','red',440),('102','blue',None),('103','red',880)]:
            source,_ = self.source(self.root,vod,color,frequency=tone)
            self.call('send',root=str(self.root),vod_id=vod,revision=1)
        value = mix_clips.draft(self.folder)
        self.assertEqual(mix_clips.render_version(value), value['version'])
        value['transition'] = 'fade'
        value['items'][-1]['options']['volume'] = 50
        mix_clips.persist(self.folder, value)
        old = mix_clips.output(self.folder, value['version'])
        old.write_bytes(source.read_bytes())
        saved = self.call('info')
        self.assertNotEqual(saved['version'], value['version'])
        self.assertEqual(saved['job']['state'], 'idle')
        command = mix_clips.clip_render.command
        codecs = []
        def record(args, *rest):
            if '-c:a' in args:
                codecs.append((Path(args[-1]).name,args[args.index('-c:a')+1]))
            return command(args,*rest)
        with patch.object(mix_clips.clip_render,'command',side_effect=record):
            self.call('render', revision=saved['revision'])
            self.mix.jobs[self.folder]['thread'].join(45)
        result = self.call('status', version=saved['version'])
        self.assertEqual(result['state'], 'complete', result)
        self.assertEqual([p for p,c in codecs if c=='aac'], ['mix.mp4'])
        self.assertEqual([c for _,c in codecs], ['pcm_f32le','pcm_f32le','copy','pcm_f32le','pcm_f32le','aac'])
        stream = subprocess.check_output(['ffprobe','-v','error','-select_streams','a:0',
            '-show_entries','stream=codec_name,sample_rate,channels','-of','csv=p=0',result['file']],text=True)
        self.assertEqual(stream.strip(),'aac,48000,2')
        samples = array('f')
        samples.frombytes(subprocess.check_output(['ffmpeg','-v','error','-i',result['file'],
            '-map','0:a:0','-ac','1','-ar','48000','-f','f32le','-']))
        def rms(start):
            window = samples[round(start*48000):round(start*48000)+2400]
            return math.sqrt(sum(x*x for x in window)/len(window))
        first, quiet, last = rms(0.2), rms(0.9), rms(1.6)
        self.assertGreater(first, 0.02)
        self.assertLess(quiet, 0.001)
        self.assertAlmostEqual(last/first, 0.5, delta=0.05)
        self.assertEqual(old.read_bytes(), source.read_bytes())
        self.assertEqual(self.call('render', revision=saved['revision']), result)
