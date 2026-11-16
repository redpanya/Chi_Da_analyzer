from .storage import ResourceBusy
"""화면 수명과 분리된 작업, 개별 중단, 재시작 복구."""
from . import error_log

import threading
import time

from . import analysis_store, chat, source, video, speech, speech_store, speech_media, speech_model
from . import task_timing, local_import, speech_options, compute, download_scope
from .video_replacement import ReplacementProject, transfer_tasks, cleanup
from . import voices, voice_store, voice_models, deletion, context_job, context_input, model_paths, context_model
from .storage import (Project, ProjectLock, Conflict, FINISHED, ACTIVE, create_or_load,
                      library, load_project, project_path, recover)


class Job:
    def __init__(self, project, guard):
        self.project = project
        self.work = ReplacementProject(project) if project.data.get('video_replacement') else project
        self.guard = guard
        self.stops, self.workers = {}, {}
        self.closed = False
        self.thread = threading.Thread(target=self.run, name=f"vod-{project.data['vod_id']}", daemon=True)

    def add(self, kinds, concurrent_fragments=None):
        for kind in kinds:
            if kind in self.workers and self.workers[kind].is_alive():
                raise Conflict('해당 작업의 중단 정리가 진행 중입니다. 잠시 후 이어받으세요')
        started = []
        try:
            for kind in kinds:
                if kind == 'video' and concurrent_fragments is not None:
                    self.work.update(kind, concurrent_fragments=concurrent_fragments)
                self.work.update(kind, state='queued', message='작업을 준비하고 있습니다',
                                 timing=task_timing.start(self.work.snapshot()['tasks'][kind], resume=True))
                self.stops[kind] = threading.Event()
                self.workers[kind] = threading.Thread(target=self.run_one, args=(kind,), daemon=True)
            for kind in kinds:
                self.workers[kind].start()
                started.append(kind)
        except Exception:
            for kind in started:
                self.stops[kind].set()
            for kind in started:
                self.workers[kind].join()
            raise

    def run_one(self, kind):
        try:
            if kind == 'video' and isinstance(self.work, ReplacementProject):
                self.work.download(video.download,self.stops[kind])
            else:
                (video.download if kind == 'video' else chat.collect)(self.project,self.stops[kind])
        except Exception as error:
            paused = isinstance(error, source.Cancelled) or self.stops[kind].is_set()
            if not paused: error_log.record('download-'+kind,error,path=self.project.path)
            try:
                self.work.update(kind, state='paused' if paused else 'error',
                                    message='중단했습니다. 저장된 자료에서 이어받을 수 있습니다' if paused else source.safe_error(error))
            except OSError:
                # 디스크까지 기록 불가하면 이전 진행 상태가 남으며 다음 열기에서 복구한다.
                pass

    def run(self):
        try:
            while True:
                with self.guard:
                    if not any(worker.is_alive() for worker in self.workers.values()):
                        if self.project.data.get('video_cleanup'):
                            from .storage import save_json
                            data = self.project.snapshot()
                            if cleanup(self.project.path, data):
                                save_json(self.project.path/'project.json', data)
                                self.project.data = data
                        self.project.lock.close()
                        self.closed = True
                        break
                threading.Event().wait(.1)
        finally:
            self.project.lock.close()
            self.closed = True

    def cancel(self, kind):
        for target, stop in self.stops.items():
            if kind in ('all', target) and self.work.snapshot()['tasks'][target]['state'] in ACTIVE:
                stop.set()
                self.work.update(target, state='stopping', message='중단 요청을 받았습니다. 현재 자료를 보존하고 있습니다')


class Manager:
    def __init__(self, default_root):
        self.default_root = str(library(str(default_root)))
        from .media_readers import MediaReaders
        self.media_readers = MediaReaders()
        self.guard = threading.RLock()
        self.job = None
        self.metadata = {}
        self.analysis_paths = set()
        self.speech_job = None
        self.voice_job = None
        self.import_job = None
        self.context_job = None
        from .automation import Automation
        from .reports import Reports
        self.automation = Automation(self)
        self.reports = Reports(self)
        from .studio_jobs import Studio
        self.studio = Studio(self)
        from .mix_clips import MixClips
        self.mix = MixClips()
        from .split_jobs import Splitter
        self.splitter = Splitter(self)
        from .work_queue import WorkQueue
        self.tasks = WorkQueue(self)

    def folders(self):
        with self.guard:
            try:
                self.speech_idle()
                busy = False
            except Conflict:
                busy = True
            try:
                model_paths.available()
                problem = ''
            except (OSError, ValueError) as error:
                problem = source.safe_error(error)
            return {'models': str(model_paths.root()), 'busy': busy, 'problem': problem, 'compute': compute.status(),
                    'ready': {name: not problem and module.status()['ready'] for name, module in
                              [('speech', speech_model), ('voices', voice_models), ('context', context_model)]}}

    def compute_settings(self, data):
        with self.guard:
            self.speech_idle()
            if set(data) == {'mode'}:
                compute.apply(data['mode'])
            elif set(data) != {'refresh'} or data['refresh'] is not True:
                raise ValueError('처리 장치 설정 형식이 올바르지 않습니다')
            if data.get('refresh'): compute.status(refresh=True)
            return self.folders()

    def import_start(self, root, vod, value):
        value=local_import.options(value);path=project_path(root,vod)
        with self.guard:
            if self.import_job and not self.import_job.closed and self.import_job.path==path and not self.import_job.thread:
                self.import_job.cancel()
            self.speech_idle();lock=ProjectLock(path)
            try:
                meta=self.metadata.get(vod)
                if (path/'project.json').exists():meta=load_project(path,vod)['metadata']
                if meta is None:raise ValueError('먼저 VOD 정보를 확인하세요')
                data=create_or_load(path,meta,None,value)
                project=Project(path,data,lock)
                self.import_job=local_import.Upload(project)
            except Exception:lock.close();raise
            return self.import_job.status()|{'project':self.view(root,vod)}

    def import_action(self, id, action, **values):
        with self.guard:
            job=self.import_job
            if not job or job.closed or job.id!=id:raise Conflict('가져오기 세션이 끝났습니다. 같은 파일을 다시 선택하세요')
            if action=='chunk':return job.chunk(**values)
            if action=='finish':job.finish()
            elif action=='cancel':job.cancel()
            else:raise ValueError('알 수 없는 가져오기 요청입니다')
            return {'ok':True}

    def model_folder(self, path):
        with self.guard:
            self.speech_idle()
            model_paths.apply(path)
            return self.folders()

    def inspect(self, url, local=False):
        if local:
            vod=source.resolve_url(url)
            try:meta=source.metadata(vod)
            except (OSError,ValueError):meta={'id':vod,'url':f'https://chzzk.naver.com/video/{vod}','title':f'VOD {vod}','channel':'','duration':None,'metadata_warning':'VOD 정보 조회 실패 · 채팅은 별도로 재시도합니다'}
            meta['formats']=[]
        else:meta = source.inspect(url)
        with self.guard:
            self.metadata[meta['id']] = meta
        return meta

    def view(self, root, vod):
        path = project_path(root, vod)
        with self.guard:
            download = self.tasks.find("download", path)
            speech_worker = self.tasks.find("speech", path)
            voice_worker = self.tasks.find("voices", path)
            context_worker = self.tasks.find("context", path)
            own = download and not download.closed and download.project.path == path
            if own:
                data, locked = download.project.snapshot(), True
            else:
                data = load_project(path, vod)
                try:
                    with ProjectLock(path):
                        data = recover(path, load_project(path, vod))
                    locked = False
                except Conflict:
                    locked = True
            speech_own = bool(speech_worker and not speech_worker.closed and speech_worker.path == path)
            try:
                voice = speech_store.view(path, data, locked, speech_own)
            except (ValueError, KeyError, OSError, TypeError):
                voice = {'state': 'error', 'message': '음성 상태 파일을 읽지 못했습니다. 기존 영상·채팅은 사용할 수 있습니다', 'owned': speech_own}
            if speech_own and speech_worker.stop.is_set():
                voice = voice | {'state': 'stopping', 'message': '현재 조각을 중단하고 있습니다. 완료 조각은 유지됩니다'}
            m4_own = bool(voice_worker and not voice_worker.closed and voice_worker.path == path)
            try:
                m4 = voice_store.view(path, locked, m4_own)
            except (ValueError, KeyError, OSError, TypeError):
                m4 = {'state': 'error', 'message': '화자 상태를 읽지 못했습니다. 기존 영상·채팅·전사는 사용할 수 있습니다', 'owned': m4_own}
            if m4_own and voice_worker.stop.is_set():
                m4 = m4 | {'state': 'stopping', 'message': 'M4 작업 중단을 정리하고 있습니다'}
            context_own = bool(context_worker and not context_worker.closed and context_worker.path == path)
            try: context = context_job.view(path, locked, context_own)
            except (ValueError, KeyError, OSError, TypeError): context = {'state':'error','message':'문맥 상태를 읽지 못했습니다','owned':context_own}
            if context_own and context_worker.stop.is_set(): context = context | {'state':'stopping'}
            return data | {'model_root': str(model_paths.root()), 'context': context, 'root': str(path.parent), 'library_root': str(download_scope.base_root(path.parent)), 'path': str(path), 'locked': locked, 'owned': bool(own or (self.import_job and not self.import_job.closed and self.import_job.path==path)),
                           'analysis_running': path in self.analysis_paths, 'speech': voice, 'voices': m4}

    def projects(self, root):
        root = library(root)
        if not root.exists():
            return []
        if not root.is_dir():
            raise ValueError('저장 경로가 폴더가 아닙니다')
        results = []
        for path in download_scope.project_paths(root):
            if path.is_symlink() or not (path / 'project.json').is_file():
                continue
            try:
                results.append(self.view(str(path.parent), path.name[4:]) | {'library_root':str(root)})
            except (ValueError, OSError):
                continue
        return sorted(results, key=lambda x: x['updated_at'], reverse=True)

    def start(self, root, vod, format_id, kind, concurrent_fragments=None):
        if concurrent_fragments is not None:
            source.fragment_concurrency(concurrent_fragments)
        if kind not in ('all', 'video', 'chat'):
            raise ValueError('작업 종류가 올바르지 않습니다')
        path = project_path(root, vod)
        with self.guard:
            if self.job and not self.job.closed:
                if self.job.project.path != path:
                    raise ResourceBusy('다른 VOD 다운로드가 끝나면 시작합니다')
                current = self.job.project.snapshot()
                if format_id != current['format_id']:
                    raise Conflict('진행 중인 VOD의 화질은 바꿀 수 없습니다')
                kinds = [target for target in ('video', 'chat') if kind in ('all', target)
                         and transfer_tasks(current)[target]['state'] not in ACTIVE | FINISHED]
                if not kinds:
                    raise Conflict('이미 진행 중이거나 완료된 작업입니다')
                raise ResourceBusy('현재 다운로드가 끝나면 나머지 자료를 받습니다')
            if (path/'project.json').exists():
                saved = load_project(path,vod)
                if saved.get('input') and not download_scope.remote(saved) and kind!='chat' and saved['tasks']['video']['state']!='complete':
                    raise ValueError('가져오기에서 같은 비디오를 다시 첨부하세요. 채팅만 이어받기는 따로 사용할 수 있습니다')
            replacing = (path/'project.json').exists() and bool(load_project(path, vod).get('video_replacement'))
            lock = ProjectLock(path, lanes=('download',), **({} if replacing else {'write': ['metadata'] + (['media'] if kind in ('all', 'video') else []) + (['chat'] if kind in ('all', 'chat') else [])}))
            job = None
            try:
                if (path / 'project.json').exists():
                    current = load_project(path, vod)
                    meta = current['metadata']
                else:
                    meta = self.metadata.get(vod)
                    if meta is None:
                        raise ValueError('먼저 VOD 정보를 확인하세요')
                data = recover(path, create_or_load(path, meta, format_id))
                kinds = [target for target in ('video', 'chat') if kind in ('all', target) and transfer_tasks(data)[target]['state'] not in FINISHED]
                if not kinds:
                    lock.close()
                    return self.view(root, vod)
                project = Project(path, data, lock)
                job = Job(project, self.guard)
                self.job = job
                job.report_started = time.monotonic()
                job.add(kinds, concurrent_fragments=concurrent_fragments)
                self.tasks.track('download', job)
                job.thread.start()
                self.reports.watch(job, 'download')
            except Exception:
                if job is not None:
                    for stop in job.stops.values():
                        stop.set()
                    for worker in job.workers.values():
                        if worker.ident is not None:
                            worker.join()
                    self.job = None
                lock.close()
                raise
        return self.view(root, vod)

    def stop(self, root, vod, kind):
        if kind not in ('all', 'video', 'chat'):
            raise ValueError('작업 종류가 올바르지 않습니다')
        with self.guard:
            if kind in ('video', 'all') and self.import_job and not self.import_job.closed and self.import_job.path==project_path(root,vod):
                self.import_job.cancel()
                if kind == 'video' or not self.job or self.job.closed or self.job.project.path != project_path(root, vod):
                    return self.view(root,vod)
            if not self.job or not self.job.thread.is_alive() or self.job.project.path != project_path(root, vod):
                raise Conflict('이 실행기가 진행하는 작업이 아닙니다')
            self.job.cancel(kind)
        return self.view(root, vod)

    def close(self):
        self.tasks.close()
        self.automation.close()
        self.tasks.close_workers()
        self.splitter.close()
        self.studio.close()
        self.mix.close()
        if self.import_job:
            self.import_job.cancel()
            if self.import_job.thread:self.import_job.thread.join()
        with self.guard:
            job = self.job
            if job and job.thread.is_alive():
                job.cancel('all')
            voice = self.speech_job
            if voice and not voice.closed:
                voice.cancel()
        if job:
            job.thread.join()
        if voice:
            voice.thread.join()
        if self.voice_job:
            self.voice_job.cancel()
            self.voice_job.thread.join()
        if self.context_job:
            self.context_job.cancel()
            self.context_job.thread.join()
        for worker in (self.job, self.speech_job, self.voice_job, self.context_job):
            observer = getattr(worker, 'report_thread', None)
            if observer: observer.join()

    def analyze(self, root, vod, options, allow_partial=False, *, stop=None):
        path = project_path(root, vod)
        with self.guard:
            lock = ProjectLock(path, read=['chat'], write=['analysis'])
            self.analysis_paths.add(path)
        try:
            data = load_project(path, vod)
            token = None
            try:
                token = self.reports.begin(path, 'reactions')
            except (OSError, ValueError):
                self.reports.warning = '반응 분석 성능 기록을 시작하지 못했습니다'
            try:
                result = analysis_store.run(path, data, options, allow_partial, stop=stop)
            except Exception as error:
                if token:
                    self.reports.safe_finish(path, token, 'reactions', 'paused' if isinstance(error, source.Cancelled) else 'error', source.safe_error(error))
                raise
            if token:
                self.reports.safe_finish(path, token, 'reactions', 'complete')
            return result
        finally:
            with self.guard:
                lock.close()
                self.analysis_paths.discard(path)

    def analysis(self, root, vod):
        path = project_path(root, vod)
        return analysis_store.load(path, load_project(path, vod))

    def chat_search(self, root, vod, **query):
        path = project_path(root, vod)
        return analysis_store.search(path, load_project(path, vod), **query)

    def speech_info(self, root, vod):
        path = project_path(root, vod)
        data = load_project(path, vod)
        return speech_media.info(path, data) | {'model': speech_model.status()}

    def work_lock(self, path, kind, action=None):
        inputs = {'speech':['media'], 'voices':['media', 'speech'],
                  'context':['media', 'speech', 'voices', 'analysis', 'chat']}[kind]
        if action in ('model', 'prepare', 'install-engine', 'check-engine'):
            inputs = []  # 도구 준비는 해당 작업 상태만 기록하고 방송 자료는 읽지 않는다.
        lanes = ()
        if kind == 'context' or action == 'suggest':
            lanes = ('context',)
        elif action in ('transcribe', 'retranscribe-original'):
            lanes = ('transcribe',)
        lock = ProjectLock(path, read=inputs, write=[kind], lanes=lanes)
        try:
            if action in ('transcribe', 'retranscribe-original'):
                lock.children.append(ProjectLock(model_paths.root(), read=['speech-models']))
            elif kind == 'voices':
                if action in ('prepare', 'install-engine'):
                    lock.children.append(ProjectLock(model_paths.root(), write=['voices-models']))
                else:
                    lock.children.append(ProjectLock(model_paths.root(), read=['voices-models']))
            return lock
        except BaseException:
            lock.close()
            raise

    def speech_start(self, root, vod, action, track=None, language='ko', input_kind='original', sam_profile=None, asr_options=None):
        if input_kind != 'original' or sam_profile is not None or action not in ('audio', 'model', 'transcribe'):
            raise ValueError('말소리 분리 기능은 제거되었습니다. 기존 파일을 보존하고 원본 오디오 전사를 사용하세요')
        options = speech_options.validate(asr_options)
        if language not in ('ko', 'auto', 'en', 'ja'):
            raise ValueError('음성 작업 또는 언어가 올바르지 않습니다')
        if action == 'audio' and type(track) is not int:
            raise ValueError('오디오 트랙을 선택하세요')
        path = project_path(root, vod)
        with self.guard:
            lock = self.work_lock(path, 'speech', action)
            try:
                data = load_project(path, vod)
                from .storage import upgrade_project
                if data.get('schema') == 1:
                    with ProjectLock(path, write=['metadata']):
                        data = upgrade_project(path, load_project(path, vod))
                previous = speech_store.state(path)
                raw = previous.get('raw_audio') or previous.get('audio') or {}
                key = [action]
                if action == 'transcribe':
                    from .speech_quality import REVISION as quality_revision
                    key += [raw.get('sha256'), raw.get('source'), language, options, quality_revision, speech_options.REVISION]
                settings = {'input_kind':'original', 'asr_options':options}
                request_options = {'track': track, 'language': language, 'input_kind': 'original', 'asr_options': options}
                speech_store.update(path, state='running', action=action, message='음성 작업을 준비합니다', progress={},
                                    compute=None, options=settings, resume_request={'action': action, 'options': request_options},
                                    timing_key=key, timing=task_timing.start(previous, resume=action != 'audio' and previous.get('action') == action and previous.get('timing_key', key) == key))
                self.speech_job = speech.SpeechJob(path, data, lock, action, {'track': track, 'language': language, 'input_kind': 'original', 'asr_options':options})
                self.speech_job.report_started = time.monotonic()
                self.tasks.track('speech', self.speech_job)
                self.speech_job.thread.start()
                if action != 'model':
                    self.reports.watch(self.speech_job, action, {'language': language, 'vad': options['vad'], 'hint_characters': len(options['prompt'])})
            except Exception:
                lock.close()
                self.speech_job = None
                raise
        return self.view(root, vod)

    def speech_idle(self):
        self.tasks.idle()
        if self.tasks.busy(): raise Conflict('실행 중인 작업을 완료하거나 중단한 뒤 설정을 변경하세요')
        self.automation.idle()
        self.studio.idle()
        self.splitter.idle()
        if self.import_job and not self.import_job.closed:raise Conflict('파일 가져오기 중입니다. 완료 또는 중단 후 진행하세요')
        if bool(self.analysis_paths) or (self.job and not self.job.closed) or (self.speech_job and not self.speech_job.closed) or (self.voice_job and not self.voice_job.closed) or (self.context_job and not self.context_job.closed):
            raise Conflict('다른 작업이 진행 중입니다. 완료 또는 중단 후 진행하세요')

    def project_idle(self, path, *, include_queued=False):
        self.tasks.project_idle(path, include_queued=include_queued)
        if path in self.analysis_paths:
            raise Conflict('이 VOD의 채팅 분석이 진행 중입니다. 완료 후 변경하세요')
        if self.automation.running and not self.automation.owns_thread() and self.automation.is_processing(path):
            raise Conflict('이 VOD의 자동화 작업이 진행 중입니다. 일시정지한 뒤 변경하세요')

    def speech_stop(self, root, vod):
        with self.guard:
            worker = self.tasks.find('speech', project_path(root, vod))
            if not worker or worker.closed or worker.path != project_path(root, vod):
                raise Conflict('이 실행기가 처리하는 음성 작업이 아닙니다')
            worker.cancel()
        return self.view(root, vod)

    def speech_result(self, root, vod, query='', cursor=0):
        path = project_path(root, vod)
        data = load_project(path, vod)
        result = speech_store.result(path, query, cursor)
        if data.get('analysis_video') and result['run']:
            from . import caption_sync
            run = speech_store.manifest(path, {'run': result['run']})
            if run:
                sync = caption_sync.resolve(path, data, speech_store.audio_for_run(path, run))
                for row in result['items']:
                    row['video_start_ms'], row['video_end_ms'] = caption_sync.interval(row, sync)
                result['sync_message'] = sync['message']
        return result

    def speech_edit(self, root, vod, action, run=None, segment=None, text=None):
        path = project_path(root, vod)
        with self.guard:
            with ProjectLock(path, read=['voices', 'context'] if action == 'delete' else [], write=['speech']):
                load_project(path, vod)
                if action == 'correct':
                    speech_store.correct(path, run, segment, text)
                    speech_store.update(path, exports={})
                elif action == 'select':
                    speech_store.select(path, run)
                elif action == 'export':
                    speech_store.export(path)
                elif action == 'delete':
                    from .result_deletion import speech as delete
                    delete(path, run)
                else:
                    raise ValueError('전사 편집 요청이 올바르지 않습니다')
        return self.view(root, vod)

    def voices_start(self, root, vod, action, options):
        if action not in ('prepare', 'diarize', 'install-engine', 'check-engine', 'suggest', 'retranscribe-original') or not isinstance(options, dict):
            raise ValueError('M4 작업이 올바르지 않습니다')
        speakers = options.get('speakers', -1)
        if type(speakers) is not int or speakers not in [-1, *range(1,21)]:
            raise ValueError('화자 수는 자동 또는 1~20명을 선택하세요')
        path = project_path(root, vod)
        if action in ('prepare','diarize','install-engine','check-engine'):
            from . import diarization_backends
            backend=options.get('backend',voice_store.state(path).get('backend','sherpa'))
            diarization_backends.validate(backend,speakers)
            backend_status=diarization_backends.status(backend)
            if not backend_status['supported']:
                raise ValueError(backend_status['install_hint'])
            if action in ('prepare','diarize','check-engine') and not backend_status['engine']:
                raise ValueError('선택 실행 도구를 먼저 다운로드·설치하세요. 기존 모델과 결과는 유지됩니다')
            options=options|{'backend':backend}
        with self.guard:
            lock = self.work_lock(path, 'voices', action)
            try:
                data = load_project(path, vod)
                if action=='suggest':
                    from .voice_suggestions import prepare
                    prepare(path,options)
                settings = {}
                if action in ('prepare','diarize','install-engine','check-engine'): settings['backend']=backend
                voice_store.update(path, **settings, state='running', action=action, message='M4 작업을 준비합니다', progress={},
                                   resume_request={'action': action, 'options': options},
                                   timing=task_timing.start(voice_store.state(path)))
                self.voice_job = voices.VoiceJob(path, data, lock, action, options)
                self.voice_job.report_started = time.monotonic()
                self.tasks.track('voices', self.voice_job)
                self.voice_job.thread.start()
                if action == 'diarize':
                    self.reports.watch(self.voice_job, 'diarize', {'speaker_backend': backend})
            except Exception:
                lock.close(); self.voice_job = None
                raise
        return self.view(root, vod)

    def voices_stop(self, root, vod):
        with self.guard:
            worker = self.tasks.find('voices', project_path(root, vod))
            if not worker or worker.closed or worker.path != project_path(root,vod):
                raise Conflict('이 실행기가 처리하는 M4 작업이 아닙니다')
            worker.cancel()
        return self.view(root,vod)

    def voices_result(self, root, vod, query='', cursor=0, review=False, failed_query='', failed_cursor=0, failed_group=''):
        from .storage import read_json
        path = project_path(root,vod); load_project(path,vod)
        value = voice_store.browse(path, query, cursor, review, failed_query, failed_cursor, failed_group)
        s = voice_store.state(path)
        from . import diarization_backends, voice_suggestions, voice_retranscription
        return value | {'model':voice_models.status(), 'diarization_models':{k:diarization_backends.status(k) for k in diarization_backends.BACKENDS},
            'suggestion':voice_suggestions.latest(path),
            'retranscription':voice_retranscription.latest(path),
            'stem': read_json(voice_store.local(path, f"stems/{s['stem']}/result.json")) if s.get('stem') else None}

    def voices_edit(self, root, vod, action, options):
        path = project_path(root,vod)
        with self.guard:
            with ProjectLock(path, read=['context'] if action == 'delete' else ['speech'], write=['voices']):
                load_project(path,vod)
                if action == 'export': voice_store.export(path)
                elif action == 'delete':
                    from .result_deletion import voices as delete
                    delete(path, options.get('run'))
                elif action == 'accept-suggestion':
                    from .voice_suggestions import accept
                    accept(path,options)
                elif action in ('select-suggestion','select-retranscription'):
                    key='suggestion' if action=='select-suggestion' else 'retranscription'
                    if options.get('id') not in [r['id'] for r in voice_store.state(path).get(key+'s',[])]:raise ValueError('보존된 검토 버전을 선택하세요')
                    voice_store.update(path,**{key:options['id']})
                elif action == 'select':
                    s = voice_store.state(path)
                    run, stem = options.get('run'), options.get('stem')
                    if run is not None:
                        if run not in s['runs']: raise ValueError('분석 버전을 선택하세요')
                        voice_store.update(path, run=run, exports={})
                    if stem is not None:
                        if stem not in [v['id'] for v in s['stems']]: raise ValueError('분리본을 선택하세요')
                        voice_store.update(path, stem=stem)
                else:
                    voice_store.edit(path, options.get('run'), options.get('revision'), action,
                                     **{k:v for k,v in options.items() if k not in ('run','revision','action')})
        return self.view(root,vod)


    def deletion_preview(self, root, vod):
        path = project_path(root, vod)
        with self.guard:
            self.project_idle(path, include_queued=True)
            load_project(path, vod)
            with ProjectLock(path): return deletion.preview(path, vod)

    def delete_project(self, root, vod, token, confirmation):
        path = project_path(root, vod)
        with self.guard, self.automation.guard:
            self.project_idle(path, include_queued=True)
            load_project(path, vod)
            with ProjectLock(path) as lock, lock.moving():
                result = deletion.trash(path, vod, token, confirmation, readers=self.media_readers)
            self.tasks.items = [item for item in self.tasks.items if item['action'] == 'queue-start' or str(path) not in item['paths']]
            with self.reports.guard:
                self.reports.sessions.pop(str(path), None)
            try:
                self.automation.status(str(download_scope.base_root(root)))
            except (ValueError, OSError):
                pass  # 삭제는 끝났다. 보관함의 다음 상태 조회에서 목록 정리를 재시도한다.
            return result

    def context_background(self, root, vod, text=None, mode=None, custom_request=None):
        from . import context_background
        path = project_path(root, vod)
        with self.guard:
            load_project(path, vod)
            if text is None:
                return context_background.settings(path)
            with ProjectLock(path, write=['context']):
                context_background.save(path, text, mode, custom_request)
                return context_background.settings(path)

    def context_start(self, root, vod, action, options=None):
        if action not in ('model','summarize','whole','resume','timestamps','timestamps-resume','clips','clips-resume'): raise ValueError('알 수 없는 문맥 작업입니다')
        if options is not None and not isinstance(options,dict):raise ValueError('문맥 작업 설정 형식이 올바르지 않습니다')
        if action=='model' and options and set(options)-{'model'}:raise ValueError('모델 설정을 확인하세요')
        if action in ('model','whole'):
            if (options or {}).get('model',context_model.DEFAULT_NAME)!=context_model.DEFAULT_NAME or (options or {}).get('method','dialogue')!='dialogue':
                raise ValueError('새 문맥 정리는 Gemma 4 E4B · 대사 중심을 사용합니다')
        if action=='summarize':raise ValueError('새 문맥 정리는 전체 영상 메뉴에서 시작하세요')
        path=project_path(root,vod)
        with self.guard:
            load_project(path,vod);lock=self.work_lock(path, 'context', action)
            try:
                if action in ('clips','clips-resume'):
                    from . import context_clips_local
                    value=context_clips_local.prepare(path,vod,action,options or {})
                elif action in ('timestamps','timestamps-resume'):
                    from . import context_timestamps
                    value=context_timestamps.prepare(path,vod,action,options or {})
                elif action in ('whole','resume'):
                    from . import context_full
                    value=context_full.prepare(path,vod,action,options or {})
                else:
                    value=context_input.build(path,vod,options or {}) if action=='summarize' else {'model_name':(options or {}).get('model')}
                self.context_job=context_job.ContextJob(path,vod,lock,action,value)
                self.context_job.report_started = time.monotonic()
                self.tasks.track('context', self.context_job)
                self.context_job.thread.start()
                if action in ('whole', 'resume', 'timestamps', 'timestamps-resume', 'clips', 'clips-resume'):
                    self.reports.watch(self.context_job, 'summary', {'summary_mode':'clips' if action.startswith('clips') else 'timestamps' if action.startswith('timestamps') else 'detail', 'thinking': (value.get('inference') or {}).get('thinking', True), 'summary_model': context_model.DEFAULT_NAME if self.context_job.model_info['name'] == context_model.DEFAULT_NAME else 'unknown'})
            except Exception:
                lock.close();self.context_job=None;raise
        return self.view(root,vod)

    def context_exchange(self, action, values):
        from . import context_exchange as exchange, context_exchange_zip as zipper, context_exchange_batch as batch
        path=project_path(values['root'],values['vod_id']);vod=values['vod_id']
        with self.guard:
            load_project(path,vod)
            if action=='prompt':
                mode=values.get('mode','timestamps');custom=exchange.custom_request(values.get('custom_request',''))
                return {'prompt':zipper.work_order({'mode':mode,'request_prompt':exchange.prompt(mode,custom,values.get('background',''))})}
            if action=='list':return exchange.listing(path)
            if action=='bundle':return exchange.bundle(path,values.get('export_id'))
            if action=='archive':return zipper.pack(path,values.get('export_id'))
            if action=='repair-archive':return zipper.repair(path,vod,values.get('export_id'))
            if action=='repair-files':return batch.repair(path,vod,values)
            if action=='preview':return exchange.preview(path,vod,values.get('text'))
            if action=='check-files':return batch.preview(path,vod,values)
            with ProjectLock(path, read=['media', 'speech', 'voices', 'chat', 'analysis'], write=['context']):
                if action=='create':return exchange.create(path,vod,values.get('options'))
                if action=='receive':return exchange.receive(path,vod,values.get('text'),values.get('token'))
                if action=='import-files':return batch.receive(path,vod,values)
                if action=='cancel':return exchange.cancel(path,values.get('export_id'))
                if action=='resume':return exchange.resume(path,vod,values.get('export_id'))
                raise ValueError('알 수 없는 외부 파일 작업입니다')

    def context_delete(self, root, vod, run):
        from .result_deletion import context as delete
        path = project_path(root, vod)
        with self.guard:
            load_project(path, vod)
            with ProjectLock(path, write=['context']):delete(path, run)
        return self.view(root, vod)

    def context_stop(self, root, vod):
        with self.guard:
            worker = self.tasks.find('context', project_path(root, vod))
            if not worker or worker.closed or worker.path!=project_path(root,vod): raise Conflict('현재 처리 중인 문맥 작업이 아닙니다')
            worker.cancel()
        return self.view(root,vod)

    def context_reject_interpretation(self,root,vod,run,item,part,interpretation):
        from .context_interpretation_edit import reject
        if not all(isinstance(v,str) for v in (run,item,part,interpretation)):raise ValueError('보완 선택 정보가 올바르지 않습니다')
        path=project_path(root,vod)
        with self.guard:
            load_project(path,vod)
            with ProjectLock(path, write=['context']):reject(path,vod,run,item,part,interpretation)
        return self.view(root,vod)
