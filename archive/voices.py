"""M4 작업은 새 폴더에 완성한 뒤 현재 결과만 전환한다."""
from . import error_log
from pathlib import Path
import threading
import uuid
import sys

from . import speech_media as media, speech_model, speech_store as speech, voice_models as models, voice_store as store
from . import audio_limits
from . import diarization_backends as backends, diarization_run, speaker_tools
from .source import Cancelled, check_cancel, safe_error
from .storage import read_json, save_json, stamp

WORKER = Path(__file__).resolve().parent.parent / 'workers/voices.py'


def input_audio(path, data, stop=None):
    value = speech.state(path); audio = value.get('audio'); run = speech.manifest(path, value)
    if not audio or not run or not run['complete'] or run.get('source_audio_sha256', run['audio_sha256']) != audio['sha256']:
        raise ValueError('현재 음성의 전체 전사를 먼저 완료하세요')
    if audio['source'] != media.identity(media.source(path, data), path):
        raise ValueError('영상 입력이 변경됐습니다. 음성 추출부터 다시 확인하세요')
    file = media.local(path, audio['file'])
    media.validate_wav(file, audio['duration_ms'],stop)
    if speech_model.digest(file,stop) != audio['sha256']:
        raise ValueError('추출 음성 검사 실패. 원음 파일을 다시 확인하세요')
    return file, audio, run


def validate_range(start, end, duration):
    if any(type(v) is not int for v in (start, end)) or not 0 <= start < end <= duration or not 1000 <= end-start <= 300000:
        raise ValueError('원음 검토는 영상 안의 1초~5분 구간을 지정하세요')


def validate_turns(turns, duration):
    if not isinstance(turns, list):
        raise ValueError('화자 엔진 결과 형식이 올바르지 않습니다')
    for turn in turns:
        a, b, speaker = (turn.get(key) for key in ('start_ms', 'end_ms', 'speaker'))
        if any(type(v) is not int for v in (a,b)) or not 0 <= a < b <= duration+100 or (speaker is not None and (type(speaker) is not int or speaker < 0)):
            raise ValueError('화자 엔진 결과 시각/ID를 확인할 수 없습니다')
        turn['end_ms'] = min(b, duration)
        if a >= duration:
            raise ValueError('화자 결과가 음성 범위를 벗어났습니다')


class VoiceJob:
    def __init__(self, path, data, lock, action, options):
        self.path, self.data, self.lock, self.action, self.options = path, data, lock, action, options
        self.stop = threading.Event(); self.closed = False
        self.thread = threading.Thread(target=self.run, daemon=True)

    def update(self, **values):
        store.update(self.path, **values)

    def cancel(self):
        self.stop.set()

    def worker(self, folder, action, audio, **options):
        backend=self.options.get('backend','sherpa')
        if backend!='sherpa':
            return diarization_run.run(backend,folder,audio,options['speakers'],self.stop,self.lock,self.update)
        args = speaker_tools.command('sherpa', folder/'request.json')
        models.verify()
        request = folder/'request.json'
        save_json(request, {'action': action, 'cache': str(models.home()), 'audio': str(audio),
                            'output': str(folder/'engine.json')} | options)
        previous=None
        def progress():
            nonlocal previous
            file=folder/'progress.json'
            if file.exists():
                value=read_json(file)
                if value!=previous:self.update(progress=value,message='화자 구분 · 완료 조각 보존 중');previous=value
        media.process(args, folder/'engine.log', self.stop, self.lock,on_poll=progress)
        return read_json(folder/'engine.json')

    def diarize(self):
        path = self.path; file, audio, transcript = input_audio(path, self.data,self.stop)
        audio_limits.duration(audio['duration_ms'])
        backend=self.options.get('backend','sherpa')
        backends.validate(backend,self.options.get('speakers',-1))
        signature={'audio_sha256':audio['sha256'],'transcript_run':transcript['id'],'speakers':self.options.get('speakers',-1),
                   **backends.signature(backend)}
        pending=store.state(path).get('pending_diarization')
        run=pending['id'] if pending and pending['signature']==signature else uuid.uuid4().hex
        folder=store.local(path,f'runs/{run}');folder.mkdir(parents=True,exist_ok=True)
        if any(p.is_symlink() for p in folder.rglob('*')):raise ValueError('화자 실행 폴더의 연결 파일은 사용할 수 없습니다')
        self.update(pending_diarization={'id':run,'signature':signature},message=backends.BACKENDS[backend]['label']+' · '+backends.BACKENDS[backend]['hint'],progress={})
        raw=self.worker(folder,'diarize',file,speakers=signature['speakers'],signature=signature)
        validate_turns(raw['turns'], audio['duration_ms'])
        speakers, assignments = store.assign(speech.segments(path, transcript), raw['turns'], run)
        result = raw | {'backend':backend,'backend_label':backends.BACKENDS[backend]['label'],'model_signature':backends.signature(backend),
                        'model_hashes':{name:value[1] for name,value in models.FILES.items()} if backend=='sherpa' else {f['name']:f['sha256'] or f['git_sha1'] for f in backends.catalog(backend)['files']},
                        'id': run, 'created_at': stamp(), 'transcript_run': transcript['id'], 'audio_sha256': audio['sha256'],
                        'duration_ms': audio['duration_ms'], 'speakers': speakers, 'assignments': assignments}
        check_cancel(self.stop)
        if audio != speech.state(path)['audio'] or speech_model.digest(file,self.stop) != audio['sha256']:
            raise ValueError('분석 중 원음이 변경됐습니다')
        save_json(folder/'result.json', result)
        self.update(run=run, runs=list(dict.fromkeys(store.state(path)['runs']+[run])),pending_diarization=None,exports={})

    def run(self):
        try:
            if self.action == 'install-engine':
                from .speaker_tools_install import install
                install(self.options['backend'],self.stop,self.lock,self.update)
            elif self.action == 'check-engine':
                backend=self.options['backend']
                folder=store.local(self.path,'preparations/'+uuid.uuid4().hex)
                self.update(message='선택 실행 도구 검사 중 · 모델·음성 로드 없음')
                speaker_tools.check(speaker_tools.command(backend,check=True),folder/'tool-check.log',self.stop,self.lock,backend)
            elif self.action == 'prepare':
                folder=store.local(self.path,'preparations/'+uuid.uuid4().hex)
                diarization_run.prepare(self.options.get('backend','sherpa'),folder,self.stop,self.lock,self.update)
            elif self.action == 'diarize': self.diarize()
            elif self.action == 'suggest':
                from . import voice_suggestions
                voice_suggestions.run(self)
            elif self.action == 'retranscribe-original':
                from . import voice_retranscription
                voice_retranscription.run(self)
            else: raise ValueError('지원하지 않는 화자 작업입니다. 기존 분리 결과는 보존됩니다')
            message='후보 검토 완료 · 배정 보류 항목은 그대로 남기며, 제안은 듣고 확인한 뒤 적용하세요' if self.action=='suggest' else '원음 재전사 비교본 저장 완료 · 기존 전사는 유지됩니다' if self.action=='retranscribe-original' else 'M4 작업 완료 · 자동 결과는 듣고 확인하세요'
            if self.action in ('install-engine','check-engine'):
                message='실행 도구 '+('설치' if self.action=='install-engine' else '검사')+' 완료 · 모델이 준비되어 있으면 바로 분석할 수 있습니다'
            self.update(state='complete', message=message, progress={})
        except Exception as error:
            paused = isinstance(error, Cancelled) or self.stop.is_set()
            if not paused: error_log.record('voices-'+self.action,error,path=self.path)
            try:
                self.update(state='paused' if paused else 'error', message='중단했습니다. 기존 완료 결과는 유지됩니다' if paused else safe_error(error))
            except OSError: pass
        finally:
            self.lock.close(); self.closed = True
