"""단계 선택은 미선택 작업을 실행하지 않고 구버전 큐·원본을 유지한다."""
import itertools
import unittest
from unittest.mock import patch

from archive.automation import options
from archive.automation_plan import STEPS, selected, sequence
from archive.automation_steps import check_inputs, MissingInput, execute
from archive.storage import project_path, load_project
from archive import speech_media
import test_automation_reports as fixtures


class SelectionTests(unittest.TestCase):
    setUp = fixtures.AutomationTests.setUp
    tearDown = fixtures.AutomationTests.tearDown
    add = fixtures.AutomationTests.add
    finish = fixtures.AutomationTests.finish

    def test_all_combinations_and_unselected_modes(self):
        for count in range(1, 6):
            for chosen in itertools.combinations(STEPS, count):
                settings = options({'steps':list(reversed(chosen)), 'summary_modes':['clips','timestamps']})
                expected = [s for s in chosen if s != 'context']
                if 'context' in chosen: expected += ['reactions','timestamps','clips']
                self.assertEqual(sequence(settings), expected)
                self.assertEqual(settings['speakers_enabled'], 'diarize' in chosen)
        for bad in ([], None, 'audio', ['unknown'], ['audio','audio'], [{}]):
            with self.assertRaises(ValueError): options({'steps':bad})
        with self.assertRaises(ValueError): options({'steps':['context'],'summary_modes':[]})
        self.assertEqual(sequence(options({'steps':['audio'],'summary_modes':[]})), ['audio'])
        self.assertEqual(selected({}), ['download'])
        self.assertEqual(sequence({'mode':'analysis','speakers_enabled':True}), ['download','audio','transcribe','diarize','reactions','summary'])

    def test_selected_only_and_legacy_resume(self):
        self.add('1', {'steps':['context'],'summary_modes':['clips','timestamps']})
        self.add('2', {'steps':['audio']})
        self.add('3', {'mode':'analysis','speakers_enabled':True})
        self.manager.automation.change(self.root, lambda d:d['items'][2]['options'].pop('steps'))
        calls=[]
        with patch('archive.automation.steps.execute',side_effect=lambda q,e,s:calls.append((e['vod'],s)) or 'reused'):
            self.manager.automation.start(self.root); result=self.finish()
        self.assertEqual(calls, [('1',s) for s in ['reactions','timestamps','clips']]+[('2','audio')]+[('3',s) for s in ['download','audio','transcribe','diarize','reactions','summary']])
        self.assertTrue(all(i['state']=='complete' for i in result['items']))
        self.assertNotIn('steps', result['items'][2]['options'])

    def test_apply_selection_then_retry_keeps_plan_and_sources(self):
        item=self.add('1',{'background':'일반 방송'})
        queue=self.manager.automation
        path=project_path(self.root,'1')/'project.json';before=path.read_bytes()
        changed=queue.update_settings(self.root,[item['id']],{'steps':['transcribe','context'],'summary_modes':['clips']})['items'][0]
        self.assertEqual(changed['options']['steps'],['transcribe','context'])
        self.assertEqual(changed['options']['background'],'일반 방송')
        queue.change(self.root,lambda d:d['items'][0].update(state='paused',stage='transcribe',stages={'transcribe':'partial'}))
        retried=queue.remove_or_retry(self.root,item['id'],retry=True)['items'][0]
        self.assertEqual(retried['options'],changed['options'])
        self.assertEqual(path.read_bytes(),before)

    def test_missing_input_stops_only_that_vod_without_starting_hidden_jobs(self):
        self.add('1',{'steps':['diarize']})
        self.add('2',{'steps':['audio']})
        self.add('3',{'steps':['transcribe']})
        self.add('4',{'steps':['context']})
        queue=self.manager.automation
        originals={project_path(self.root,str(i))/'project.json':(project_path(self.root,str(i))/'project.json').read_bytes() for i in range(1,5)}
        with patch.object(self.manager,'start') as download, patch.object(self.manager,'speech_start') as speech, patch.object(self.manager,'voices_start') as voice, patch.object(self.manager,'context_start') as context:
            queue.start(self.root); result=self.finish()
        self.assertEqual([i['state'] for i in result['items']], ['error']*4)
        for name in ['완료된 전사','완료된 영상','원음 오디오','완료된 전사']:
            self.assertIn(name,result['items'].pop(0)['message'])
        for mock in [download,speech,voice,context]:mock.assert_not_called()
        for file,content in originals.items():self.assertEqual(file.read_bytes(), content)

    def test_existing_audio_and_transcript_checks_are_read_only(self):
        self.add();path=project_path(self.root,'1');data=load_project(path,'1')
        (path/'media').mkdir();video=path/'media/original.mp4';video.write_bytes(b'original')
        data['tasks']['video'].update(state='complete',assets={'playback':'media/original.mp4'})
        audio=path/'speech/source.wav';audio.parent.mkdir();audio.write_bytes(b'audio')
        raw={'source':speech_media.identity(video,path),'file':'source.wav'}
        with patch('archive.speech_store.state',return_value={'raw_audio':raw}):
            check_inputs(path,data,options({'steps':['transcribe']}),'transcribe')
            with patch('archive.speech_store.manifest',return_value={'complete':True}), patch('archive.speech_store.view',return_value={'stale':False}):
                check_inputs(path,data,options({'steps':['context']}),'summary')
            with patch('archive.speech_store.manifest',return_value={'complete':False}):
                with self.assertRaises(MissingInput):check_inputs(path,data,options({'steps':['diarize']}),'diarize')
            raw['separation_run']='old-stem'
            with self.assertRaises(MissingInput):check_inputs(path,data,options({'steps':['transcribe']}),'transcribe')
            raw.pop('separation_run');video.write_bytes(b'changed-video')
            with self.assertRaises(MissingInput):check_inputs(path,data,options({'steps':['transcribe']}),'transcribe')
        self.assertEqual(audio.read_bytes(),b'audio')

    def test_chat_absent_does_not_download_or_block_ai(self):
        item=self.add('1',{'steps':['context'],'summary_modes':['timestamps']})
        self.manager.automation.root=self.root
        with patch('archive.automation_steps.check_inputs'), patch.object(self.manager,'start') as download, patch.object(self.manager.reports,'skipped') as skipped:
            self.assertEqual(execute(self.manager.automation,item,'reactions'),'skipped')
            skipped.assert_called_once();download.assert_not_called()
