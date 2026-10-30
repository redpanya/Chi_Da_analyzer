"""추출·모델 준비·전사를 실행하고 완료 조각을 체크포인트로 유지한다."""
from . import error_log

import shutil
import threading
import time
import uuid

from . import speech_media as media, speech_model as model, speech_store as store, speech_options
from . import audio_limits, compute
from . import speech_vad, speech_quality, speech_recognition
from .source import Cancelled, check_cancel, safe_error
from .storage import save_json, stamp


def transcribe(path, data, language, stop, lock, update, input_audio=None, raw_audio=None, options=None):
    options = speech_options.validate(options)
    if language not in ('ko', 'auto', 'en', 'ja'):
        raise ValueError('지원하는 전사 언어를 선택하세요')
    audio = input_audio or store.state(path).get('audio')
    raw_audio = raw_audio or audio
    if not audio:
        raise ValueError('음성을 먼저 추출하세요')
    if audio['source'] != media.identity(media.source(path, data), path):
        raise ValueError('영상 입력이 변경됐습니다. 음성을 다시 추출하세요')
    audio_limits.duration(audio['duration_ms'])
    wav = media.local(path, audio['file'])
    media.validate_wav(wav, audio['duration_ms'],stop)
    if model.digest(wav,stop) != audio['sha256']:
        raise ValueError('추출 음성이 변경됐습니다. 다시 추출하세요')
    wav_identity = media.identity(wav, path)
    binary, version = model.engine_version()
    execution = compute.select('whisper-cli')
    if compute.windows():
        binary = execution['binary']
    update(compute=execution)
    model_file = model.verify()
    vad_model = speech_vad.prepare(stop, update) if options['vad'] != 'off' else None
    signature = {'audio_sha256': audio['sha256'], 'language': language, 'engine': version,
                 'source_audio_sha256': raw_audio['sha256'], 'input_kind': audio.get('input_kind', 'original'),
                 'separation_run': audio.get('separation_run'), 'model_sha256': model.SHA256, 'chunk_ms': store.CHUNK_MS, 'duration_ms': audio['duration_ms'],
                 'quality_revision': speech_quality.REVISION, 'vad_revision':speech_vad.REVISION, 'vad_sha256':speech_vad.SHA256,
                 'coverage_revision':speech_vad.COVERAGE_REVISION,
                 'asr_options': options, 'options_revision': speech_options.REVISION}
    active = store.manifest(path)
    run = store.matching_run(path, signature)
    if not run:
        run = signature | {'id': uuid.uuid4().hex, 'created_at': stamp(), 'chunks': [], 'processed_ms': 0,
                           'complete': False, 'segment_count': 0, 'model': model.NAME,
                           'input_audio': audio, 'source_audio': raw_audio}
        save_json(media.local(path, f"runs/{run['id']}/manifest.json"), run)
    update(pending_run=run['id'])
    if not active or not active['complete']:
        update(run=run['id'], audio=raw_audio, exports={})
    store.segments(path, run)
    folder = media.local(path, f"runs/{run['id']}")
    if any(item.is_symlink() for item in folder.iterdir()):
        raise ValueError('전사 실행 폴더의 연결 파일은 덮어쓰지 않습니다')
    for start in range(run['processed_ms'], run['duration_ms'], store.CHUNK_MS):
        check_cancel(stop)
        if shutil.disk_usage(path).free < 64 * 1024**2:
            raise OSError(28, '전사 체크포인트 저장 공간 부족')
        end = min(start + store.CHUNK_MS, run['duration_ms'])
        index = len(run['chunks'])
        update(message=f'전체 음성 전사 중 · {index + 1}번째 조각',
               progress={'processed_ms': start, 'duration_ms': run['duration_ms'], 'current_end_ms': end})
        chunk = folder / 'working.wav'
        metrics = media.chunk_audio(wav, chunk, start, end)
        raw_prefix = folder / f'{index:05d}-raw'
        started = time.monotonic()
        if metrics['digital_silence']:
            raw = {'transcription': [], 'reason': 'digital_silence'}
            save_json(raw_prefix.with_suffix('.json'), raw)
        else:
            raw = speech_recognition.recognize(binary,model_file,chunk,folder,index,end-start,language,vad_model,stop,lock,options,execution)
        rows = speech_quality.annotate(store.normalize(raw, start, end, index))
        if audio['source'] != media.identity(media.source(path, data), path) or wav_identity != media.identity(wav, path):
            raise ValueError('전사 중 영상 또는 추출 음성이 변경됐습니다. 입력을 다시 확인하세요')
        if metrics['digital_silence']:
            status = 'silence'
        else:
            status = 'recognized' if rows else 'no_speech' if raw.get('reason')=='vad_no_speech' else 'unrecognized'
        coverage=speech_vad.coverage(raw.get('windows',[]),end-start,start,metrics['digital_silence'])
        saved = {'start_ms': start, 'end_ms': end, 'status': status, 'segments': rows, 'coverage':coverage,
                 'metrics': metrics, 'seconds': round(time.monotonic() - started, 3)}
        name = f'{index:05d}.json'
        save_json(folder / name, saved)
        run['chunks'].append({'file': name, 'start_ms': start, 'end_ms': end, 'status': status,
                              'encoding_review_count': sum(row['encoding_review'] for row in rows),
                              'quality_review_count':sum(row['quality_review'] for row in rows),
                              'not_transcribed_ms':sum(b-a for a,b in coverage['not_transcribed'])})
        run.update(processed_ms=end, segment_count=run['segment_count'] + len(rows), complete=end == run['duration_ms'])
        save_json(folder / 'manifest.json', run)
        update(progress={'processed_ms': end, 'duration_ms': run['duration_ms']})
        chunk.unlink(missing_ok=True)
    check_cancel(stop)
    previous_audio = store.state(path).get('audio')
    if previous_audio:
        save_json(media.local(path, 'audio-history/'+previous_audio['sha256']+'.json'), previous_audio)
    update(run=run['id'], audio=raw_audio, pending_run=None, exports={})
    store.export(path)


class SpeechJob:
    def __init__(self, path, data, lock, action, options):
        self.path, self.data, self.lock = path, data, lock
        self.action, self.options = action, options
        self.stop = threading.Event()
        self.closed = False
        self.thread = threading.Thread(target=self.run, name='음성-작업', daemon=True)

    def update(self, **values):
        return store.update(self.path, **values)

    def cancel(self):
        self.stop.set()

    def run(self):
        try:
            if self.action == 'model':
                model.prepare(self.stop, self.update)
            elif self.action == 'audio':
                audio = media.extract(self.path, self.data, self.options['track'], self.stop, self.lock, self.update)
                values = {'raw_audio': audio}
                if not store.manifest(self.path): values['audio'] = audio
                self.update(**values)
            elif self.action == 'transcribe':
                if self.options.get('input_kind', 'original') != 'original':
                    raise ValueError('말소리 분리 작업은 제거되었습니다. 기존 결과를 보존하고 원본 오디오로 새 전사를 시작하세요')
                state = store.state(self.path)
                raw = state.get('raw_audio') or state.get('audio')
                if not raw: raise ValueError('원음을 먼저 추출하세요')
                audio = raw | {'input_kind': 'original'}
                transcribe(self.path, self.data, self.options['language'], self.stop, self.lock, self.update,
                           audio, raw, options=self.options.get('asr_options'))
            else:
                raise ValueError('지원하지 않는 음성 작업입니다. 기존 분리 결과는 그대로 보존됩니다')
            self.update(state='complete', message={'model': '모델 준비 완료', 'audio': '음성 추출 완료',
                        'transcribe': '전체 범위 전사 처리 완료 · 자동 인식 내용은 원음으로 확인하세요'}[self.action])
        except Exception as error:
            if not self.stop.is_set() and not isinstance(error,Cancelled): error_log.record('speech-'+self.action,error,path=self.path)
            try:
                paused = isinstance(error, Cancelled) or self.stop.is_set()
                self.update(state='paused' if paused else 'error',
                            message='중단했습니다. 완료 조각은 유지되며 현재 조각은 다시 처리합니다' if paused else safe_error(error))
            except OSError:
                pass
        finally:
            self.lock.close()
            self.closed = True
