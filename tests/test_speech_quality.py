import copy
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from archive import speech_quality as quality, speech_vad as vad, speech_recognition as recognition
from archive import context_evidence, speech_store
from archive.storage import ProjectLock, save_json, read_json


def row(text,start=0):
    return {'id':str(start),'start_ms':start,'end_ms':start+1000,'text':text}


class QualityTests(unittest.TestCase):
    def test_repeated_real_speech_is_preserved_in_summary_input(self):
        original=[row('생일 축하해요',n*3000) for n in range(4)];before=copy.deepcopy(original)
        result=quality.annotate(original)
        self.assertEqual(original,before)
        self.assertTrue(all(x['repeat_candidate'] for x in result))
        self.assertFalse(any(x['quality_review'] or x['repeat_review'] for x in result))
        self.assertEqual(len(context_evidence.speech({'speech':result})),4)

    def test_internal_loop_is_review_and_user_correction_overrides(self):
        result=quality.annotate([row('피 '*219)])
        self.assertTrue(result[0]['quality_review']);self.assertEqual(result[0]['text'],'피 '*219)
        self.assertFalse(context_evidence.speech({'speech':result}))
        result[0].update(text='원음 확인한 반복 발화',corrected=True)
        self.assertEqual(len(context_evidence.speech({'speech':result})),1)
        self.assertFalse(quality.repetitive('정말 감사합니다 정말 감사합니다'))

    def test_vad_window_preserves_long_gaps_and_rejects_invalid_ranges(self):
        self.assertEqual(vad.windows([[66000,68000],[71000,73000]],90000),[[65750,74000]])
        self.assertEqual(vad.windows([[1000,2000],[66000,68000]],90000),[[750,3000],[65750,69000]])
        for value in [[[2000,1000]],[[0,90001]],[[1000,2000],[1500,3000]]]:
            with self.assertRaises(ValueError):vad.windows(value,90000)

    def test_coverage_distinguishes_unprocessed_audio_from_confirmed_digital_silence(self):
        value=vad.coverage([[1000,2000],[6000,7000]],8000,300000)
        self.assertEqual(value['asr_windows'],[[301000,302000],[306000,307000]])
        self.assertEqual(value['not_transcribed'],[[300000,301000],[302000,306000],[307000,308000]])
        self.assertFalse(value['speech_absence_confirmed'])
        silent=vad.coverage([],8000,digital_silence=True)
        self.assertTrue(silent['digital_silence_candidate']);self.assertFalse(silent['speech_absence_confirmed'])
        with self.assertRaises(ValueError):vad.coverage([[0,9000]],8000)

    def test_multiple_asr_windows_restore_original_time_and_preserve_raw(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);wav=p/'input.wav'
            with wave.open(str(wav),'wb') as w:
                w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(b'\0\0'*16000*8)
            def engine(args,*a):
                self.assertIn('-oj',args);self.assertNotIn('-ojf',args)
                inputs=[args[i+1] for i,x in enumerate(args) if x=='-of']
                for file in inputs:save_json(Path(file).with_suffix('.json'),{'transcription':[{'offsets':{'from':0,'to':500},'text':'같은 인사'}]})
            with ProjectLock(p) as lock,patch.object(vad,'detect',return_value=[[1000,2000],[6000,7000]]),patch.object(recognition.media,'process',side_effect=engine):
                result=recognition.recognize('whisper',p/'model',wav,p,0,8000,'ko',p/'vad',threading.Event(),lock)
            normalized=speech_store.normalize(result,300000,308000,1)
            self.assertEqual([r['start_ms'] for r in normalized],[301000,306000])
            self.assertEqual([r['text'] for r in normalized],['같은 인사']*2)
            self.assertEqual(read_json(p/'00000-speech-0000.json')['transcription'][0]['offsets']['from'],0)


if __name__=='__main__':unittest.main()
