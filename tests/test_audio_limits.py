"""20시간 경계·대용량 컨테이너·긴 화자 결과 연결을 검사한다."""
import random
import unittest
from archive import audio_limits, voice_store, voices

class AudioLimitsTests(unittest.TestCase):
    def test_twenty_hours_and_container_boundary(self):
        audio_limits.duration(72_000_000)
        for v in (72_000_001,0,-1,True,float('nan')):
            with self.assertRaises(ValueError):audio_limits.duration(v)
        for rate,channels in ((48000,1),(44100,2)):
            self.assertEqual(audio_limits.wav_format(72000*rate,rate,channels),'RF64')
            self.assertEqual(audio_limits.wav_format(300*rate,rate,channels),'WAV')
            with self.assertRaises(ValueError):audio_limits.wav_format(72000*rate+1,rate,channels)
        self.assertEqual(audio_limits.wav_format(72000*16000,16000,1,2),'WAV')

    def test_unknown_voice_stays_failed_at_twenty_hour_offset(self):
        end=audio_limits.MAX_MS
        turns=[{'start_ms':end-3000,'end_ms':end,'speaker':None}]
        voices.validate_turns(turns,end)
        speakers,assigned=voice_store.assign([{'id':'last','start_ms':end-3000,'end_ms':end}],turns,'long')
        self.assertEqual(speakers,{})
        self.assertEqual(assigned['last']['reason'],'ambiguous')
        self.assertIsNone(assigned['last']['speaker'])

    def test_sweep_matches_overlap_for_unsorted_and_nested_rows(self):
        random.seed(14)
        turns=[{'start_ms':s,'end_ms':s+random.randint(100,1500),'speaker':i%3} for i,s in enumerate(range(0,40000,250))]
        rows=[{'id':str(i),'start_ms':i*113,'end_ms':i*113+random.randint(100,8000)} for i in range(160)]
        random.shuffle(rows);random.shuffle(turns)
        _,actual=voice_store.assign(rows,turns,'x')
        labels=sorted({t['speaker'] for t in turns},key=lambda k:min(t['start_ms'] for t in turns if t['speaker']==k))
        for row in rows:
            ids,one=voice_store.assign([row],turns,'x')
            self.assertEqual(actual[row['id']],one[row['id']])
        self.assertEqual(list(ids),['x-0','x-1','x-2'])


class ResumeSpaceTests(unittest.TestCase):
    def test_cancelled_hash_keeps_input(self):
        import tempfile,threading,hashlib
        from pathlib import Path
        from archive.speech_model import digest
        from archive.source import Cancelled
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'audio.wav';value=b'original audio'
            path.write_bytes(value);stop=threading.Event();stop.set()
            with self.assertRaises(Cancelled):digest(path,stop)
            self.assertEqual(path.read_bytes(),value)
            stop.clear();self.assertEqual(digest(path,stop),hashlib.sha256(value).hexdigest())

    def test_resume_does_not_require_completed_chunks_twice(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'000000.npz').write_bytes(b'x'*100)
            (folder/'target.part.wav').write_bytes(b'x'*100)
            self.assertEqual(audio_limits.remaining_space(folder,1000,1,50),950)


class LongTranscriptTests(unittest.TestCase):
    import test_speech as fixture
    setUp=fixture.SpeechTests.setUp
    tearDown=fixture.SpeechTests.tearDown
    audio=fixture.SpeechTests.audio

    def test_twenty_hour_transcript_schedule_and_resume(self):
        import threading
        from unittest.mock import patch
        from archive import speech, speech_store as store, speech_model, speech_media as media
        from archive.storage import ProjectLock
        self.audio();raw=store.state(self.path)['audio']|{'duration_ms':audio_limits.MAX_MS}
        store.update(self.path,audio=raw);spans=[]
        def chunk(_source,_target,start,end):
            spans.append((start,end));return {'digital_silence':True,'peak':0,'rms':0}
        with patch.object(media,'validate_wav'),patch.object(media,'chunk_audio',side_effect=chunk),patch.object(speech_model,'verify'),patch.object(speech_model,'engine_version',return_value=('test','test')):
            for _ in range(2):
                with ProjectLock(self.path) as lock:
                    speech.transcribe(self.path,self.data,'ko',threading.Event(),lock,lambda **v:store.update(self.path,**v))
        self.assertEqual(len(spans),audio_limits.MAX_MS//store.CHUNK_MS)
        self.assertEqual(spans[0][0],0);self.assertEqual(spans[-1][1],audio_limits.MAX_MS)
        self.assertTrue(all(spans[i-1][1]==spans[i][0] for i in range(1,len(spans))))
        self.assertTrue(store.manifest(self.path)['complete'])

if __name__=='__main__':unittest.main()

