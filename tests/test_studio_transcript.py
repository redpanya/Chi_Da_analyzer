"""전사 담기: 원문 보존, 초안 병합, 중복, 시각 변환, 충돌 방어."""
import copy
import unittest
from archive import speech_media, studio_jobs
from archive.storage import Conflict, ProjectLock, read_json, save_json
from test_studio_jobs import StudioJobs


class TranscriptClips(unittest.TestCase):
    setUp = StudioJobs.setUp
    tearDown = StudioJobs.tearDown

    def transcript(self):
        run = 'a'*32
        folder = self.path/'speech'/'runs'/run
        source = speech_media.identity(self.file, self.path)
        save_json(self.path/'speech/state.json', {'state':'complete','run':run})
        save_json(folder/'manifest.json', {'id':run,'duration_ms':4000,'processed_ms':4000,'complete':True,
            'source_audio':{'source':source}, 'chunks':[{'start_ms':0,'end_ms':4000,'file':'00000.json'}]})
        save_json(folder/'00000.json', {'start_ms':0,'end_ms':4000,'segments':[
            {'id':'first','start_ms':1000,'end_ms':2000,'text':'원문'},
            {'id':'second','start_ms':2500,'end_ms':3500,'text':'다음 발언'}]})
        save_json(folder/'corrections.json', {'first':'저장된 교정\n제목'})
        return run

    def add(self, run, segment='first'):
        return self.manager.studio.dispatch('transcript-add', self.args|{'run':run,'segment':segment})

    def test_append_preserves_options_edits_and_old_results(self):
        run = self.transcript()
        request={'clips':[{'id':'manual-1','title':'기존','start_ms':3000,'end_ms':4000}],
            'options':{'font_size':30,'caption_y':3.5},'caption_edits':{'first':'편집 전용 교정'},
            'range_drafts':{'manual-1':{'title':'입력 중','start':'00:00:03','end':'00:00:04'}}}
        old = self.manager.studio.dispatch('draft', self.args|{'request':request,'revision':0})
        files={str(p):p.read_bytes() for p in self.path.rglob('*') if p.is_file() and 'studio' not in p.parts}
        result=self.add(run);saved=read_json(self.path/'studio/draft.json')
        self.assertTrue(result['added']);self.assertEqual(result['count'],2)
        for key in old['request'].keys()-{'clips'}:self.assertEqual(saved['request'][key],old['request'][key])
        self.assertEqual(saved['request']['clips'][0]['title'],'저장된 교정 제목')
        self.assertEqual(saved['request']['clips'][1],old['request']['clips'][0])
        self.assertEqual(read_json(next((self.path/'studio/drafts').glob('*.json'))),old)
        self.assertEqual(files,{str(p):p.read_bytes() for p in self.path.rglob('*') if p.is_file() and 'studio' not in p.parts})
        before=(self.path/'studio/draft.json').read_bytes()
        self.assertFalse(self.add(run)['added']);self.assertEqual(before,(self.path/'studio/draft.json').read_bytes())
        with self.assertRaises(Conflict):self.manager.studio.dispatch('draft',self.args|{'request':request,'revision':old['revision']})

    def test_partial_video_origin_and_fresh_draft(self):
        run=self.transcript();data=read_json(self.path/'project.json')
        data['input']={'kind':'range','start_vod_ms':900000};save_json(self.path/'project.json',data)
        self.add(run)
        request=read_json(self.path/'studio/draft.json')['request']
        self.assertEqual((request['clips'][0]['start_ms'],request['clips'][0]['end_ms']),(901000,902000))
        self.assertFalse(request['options']['caption']);self.assertIsNone(request['selection'])

    def test_no_rewrite_for_duplicate_even_after_manual_clip_edit(self):
        run=self.transcript();self.add(run)
        old=read_json(self.path/'studio/draft.json');request=copy.deepcopy(old['request'])
        request['clips'][0].update(title='사용자 편집 제목',start_ms=500)
        self.manager.studio.dispatch('draft',self.args|{'request':request,'revision':old['revision']})
        self.assertFalse(self.add(run)['added'])
        self.assertEqual(read_json(self.path/'studio/draft.json')['request']['clips'][0]['title'],'사용자 편집 제목')

    def test_stale_missing_locked_and_limit(self):
        run=self.transcript()
        for value,segment in [('b'*32,'first'),('../../x','first'),(run,'missing')]:
            with self.assertRaises(ValueError):self.add(value,segment)
        with ProjectLock(self.path):
            with self.assertRaises(Conflict):self.add(run)
        request={'clips':[{'id':str(i),'title':'기존','start_ms':0,'end_ms':1000} for i in range(100)]}
        self.manager.studio.dispatch('draft',self.args|{'request':request,'revision':0})
        before=(self.path/'studio/draft.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'100개'):self.add(run)
        self.assertEqual(before,(self.path/'studio/draft.json').read_bytes())
        self.file.write_bytes(b'changed')
        with self.assertRaises((ValueError,RuntimeError)):self.add(run)


if __name__=='__main__':unittest.main()
