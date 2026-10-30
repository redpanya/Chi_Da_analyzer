"""루프백 전용 GUI API와 허용된 결과 파일의 Range 전달."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import shutil
from urllib.parse import parse_qs, urlsplit, quote

from .source import safe_error
from .speech_media import local as speech_file
from . import voice_store, explore, runtime, context_job
from .storage import Conflict, asset_path, project_path
from .web_security import content_security_policy

WEB = Path(__file__).resolve().parent.parent / 'web'


class GuiServer(ThreadingHTTPServer):
    # 여러 탭이 ES 모듈을 함께 읽어도 Python 3.11의 기본 대기열(5)을 넘지 않게 한다.
    request_queue_size = 64


def byte_range(value, size):
    if value is None:
        return 0, size - 1
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
    if not match or not any(match.groups()) or size <= 0:
        raise ValueError()
    first, last = match.groups()
    if not first:
        if int(last) <= 0:
            raise ValueError()
        return max(0, size - int(last)), size - 1
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError()
    return start, end


def make_server(manager, port=0, *, annotation_preview=False):
    csp = content_security_policy(annotation_preview)
    prefix = '/' + secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def allowed(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != origin[7:] or self.headers.get('Origin', origin) != origin:
                self.reply(403, {'error': '이 앱 화면에서만 요청할 수 있습니다'})
                return False
            if not urlsplit(self.path).path.startswith(prefix + '/'):
                self.reply(404, {'error': '주소가 없거나 실행기가 다시 시작되었습니다'})
                return False
            return True

        def send_headers(self, status, mime, size):
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(size))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', csp)

        def reply(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_headers(status, 'application/json; charset=utf-8', len(body))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if not self.allowed():
                return
            try:
                length = int(self.headers.get('Content-Length', 0))
                if urlsplit(self.path).path[len(prefix):].startswith('/api/import-'):
                    self.close_connection = True
                    self.reply(410, {'error': '새 로컬 영상 가져오기는 제거되었습니다. 기존 완료 자료는 계속 사용할 수 있습니다'})
                    return
                limit=16*1024**2 if self.path.endswith('/api/studio-image-add') else 22*1024**2 if self.path.endswith(('/api/context-exchange-preview','/api/context-exchange-receive','/api/context-exchange-check-files','/api/context-exchange-import-files')) else 4*1048576 if '/api/studio-' in self.path else 1048576 if self.path.endswith('/api/context-comment-save') else 65536
                if length <= 0 or length > limit or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('요청 형식이 올바르지 않습니다')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('요청 값이 올바르지 않습니다')
                action = urlsplit(self.path).path[len(prefix):]
                if action.startswith('/api/split-'):
                    result = manager.splitter.dispatch(action.removeprefix('/api/split-'), data)
                elif action.startswith('/api/studio-'):
                    result = manager.studio.dispatch(action.removeprefix('/api/studio-'), data)
                elif action.startswith('/api/queue-'):
                    result = manager.automation.dispatch(action[len('/api/queue-'):], data)
                elif action == '/api/report-config':
                    from .report_hardware import collect
                    result = {'hardware': collect()}
                elif action == '/api/reports':
                    result = manager.reports.list(data['root'], data['vod_id'])
                elif action == '/api/report-read':
                    result = manager.reports.snapshot(data['root'], data['vod_id'], data['report_id'])
                elif action == '/api/report-preview':
                    result = {'payload': manager.reports.snapshot(data['root'], data['vod_id'], data['report_id'])['payload']}
                elif action == '/api/report-submit':
                    self.reply(410, {'error': '자동 제출 기능은 제거되었습니다. JSON을 저장해 이메일에 직접 첨부하세요'})
                    return
                elif action == '/api/folders':
                    result = manager.folders()
                elif action == '/api/model-folder':
                    result = manager.model_folder(data['path'])
                elif action == '/api/compute':
                    result = manager.compute_settings(data)
                elif action == '/api/delete-preview':
                    result = manager.deletion_preview(data['root'], data['vod_id'])
                elif action == '/api/delete-project':
                    result = manager.delete_project(data['root'], data['vod_id'], data.get('token'), data.get('confirmation'))
                elif action.startswith('/api/context-exchange-'):
                    result = manager.context_exchange(action.removeprefix('/api/context-exchange-'), data)
                elif action in ('/api/context-comment', '/api/context-comment-save'):
                    from . import context_comments
                    path = project_path(data['root'], data['vod_id'])
                    result = context_comments.save(path, data['run'], data['draft']) if action.endswith('-save') else context_comments.read(path, data['run'])
                elif action in ('/api/context-background', '/api/context-background-save'):
                    from .context_background import validate
                    text=validate(data.get('text')) if action.endswith('-save') else None
                    result = manager.context_background(data['root'], data['vod_id'], text, data.get('mode'), data.get('custom_request'))
                elif action == '/api/context-start':
                    result = manager.context_start(data['root'], data['vod_id'], data['action'], data.get('options'))
                elif action == '/api/context-stop':
                    result = manager.context_stop(data['root'], data['vod_id'])
                elif action == '/api/context-delete':
                    result = manager.context_delete(data['root'], data['vod_id'], data.get('run'))
                elif action == '/api/context-result':
                    result = context_job.result(project_path(data['root'], data['vod_id']), data['vod_id'], data.get('run'))
                elif action == '/api/context-reject-interpretation':
                    result = manager.context_reject_interpretation(data['root'],data['vod_id'],data['run'],data['item'],data['part'],data['interpretation'])
                elif action == '/api/inspect':
                    result = manager.inspect(data['url'],data.get('local') is True)
                elif action == '/api/projects':
                    result = manager.projects(data['root'])
                    root = str(Path(data['root']).expanduser().resolve())
                    # 실행 인자의 보관함을 열기만 해서는 사용자가 저장한 기본 경로를 덮어쓰지 않는다.
                    if root!=manager.default_root:runtime.remember_library(root)
                    manager.default_root = root
                elif action == '/api/state':
                    result = manager.view(data['root'], data['vod_id'])
                elif action == '/api/start':
                    result = manager.start(data['root'], data['vod_id'], data['format_id'], data['kind'])
                elif action == '/api/stop':
                    result = manager.stop(data['root'], data['vod_id'], data['kind'])
                elif action == '/api/analyze':
                    result = manager.analyze(data['root'], data['vod_id'], data.get('settings', {}), data.get('allow_partial', False))
                elif action == '/api/analysis':
                    result = manager.analysis(data['root'], data['vod_id'])
                elif action.startswith('/api/clips-'):
                    self.reply(410, {'error':'구간 저장은 제거된 기능입니다. 화면을 새로고침하세요'});return
                elif action == '/api/explore-info':
                    result = explore.info(data['root'], data['vod_id'], data.get('chat_offset_ms', 0))
                elif action == '/api/explore-search':
                    result = explore.search(data['root'], data['vod_id'], **{k: v for k, v in data.items() if k not in ('root', 'vod_id')})
                elif action == '/api/chats':
                    result = manager.chat_search(data['root'], data['vod_id'], query=data.get('query', ''),
                                                 start_ms=data.get('start_ms', 0), end_ms=data.get('end_ms'), cursor=data.get('cursor', 0))
                elif action == '/api/voices-start':
                    result = manager.voices_start(data['root'], data['vod_id'], data['action'], data.get('options', {}))
                elif action == '/api/voices-stop':
                    result = manager.voices_stop(data['root'], data['vod_id'])
                elif action == '/api/voices-result':
                    result = manager.voices_result(data['root'], data['vod_id'], data.get('query', ''), data.get('cursor', 0),
                                                   data.get('review', False), data.get('failed_query', ''), data.get('failed_cursor', 0), data.get('failed_group',''))
                elif action == '/api/voices-edit':
                    result = manager.voices_edit(data['root'], data['vod_id'], data['action'], data.get('options', {}))
                elif action == '/api/speech-info':
                    result = manager.speech_info(data['root'], data['vod_id'])
                elif action == '/api/speech-start':
                    result = manager.speech_start(data['root'], data['vod_id'], data['action'], data.get('track'), data.get('language', 'ko'), data.get('input_kind', 'original'), data.get('sam_profile'), data.get('asr_options'))
                elif action == '/api/speech-stop':
                    result = manager.speech_stop(data['root'], data['vod_id'])
                elif action == '/api/speech-result':
                    result = manager.speech_result(data['root'], data['vod_id'], data.get('query', ''), data.get('cursor', 0))
                elif action == '/api/speech-edit':
                    result = manager.speech_edit(data['root'], data['vod_id'], data['action'],
                                                 data.get('run'), data.get('segment'), data.get('text'))
                else:
                    self.reply(404, {'error': '요청 경로가 없습니다'})
                    return
                self.reply(200, result)
            except Conflict as error:
                self.reply(409, {'error': str(error)})
            except Exception as error:
                self.reply(400, {'error': safe_error(error)})

        def do_GET(self):
            self.get(True)

        def do_HEAD(self):
            self.get(False)

        def get(self, body):
            if not self.allowed():
                return
            path = urlsplit(self.path).path[len(prefix):]
            if path == '/split-audio':
                try:
                    query = parse_qs(urlsplit(self.path).query)
                    target = manager.splitter.audio_preview.file(query.get('id', [None])[0])
                    self.send_file(target, body, download=False)
                except (ValueError, KeyError, OSError) as error:
                    self.reply(404, {'error': safe_error(error)})
                return
            if path == '/split-file':
                try:
                    query = parse_qs(urlsplit(self.path).query)
                    target = manager.splitter.media_file(source_id=query.get('source', [None])[0],
                                                         run=query.get('run', [None])[0], index=query.get('index', [None])[0])
                    self.send_file(target, body, download='source' not in query)
                except (ValueError, KeyError, OSError) as error:
                    self.reply(404, {'error': safe_error(error)})
                return
            if path == '/api/config':
                self.reply(200, {'root': manager.default_root,
                                 'folders': manager.folders(),
                                 'annotation_preview': bool(annotation_preview),
                                 'media_tools': bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))})
                return
            files = {'/': ('index.html', 'text/html; charset=utf-8'),
                     '/style.css': ('style.css', 'text/css; charset=utf-8'),
                     '/workspace.css': ('workspace.css', 'text/css; charset=utf-8'),
                     '/mini-player.css': ('mini-player.css', 'text/css; charset=utf-8'),
                     '/pattern-background.css': ('pattern-background.css', 'text/css; charset=utf-8'),
                     '/pattern-background.js': ('pattern-background.js', 'text/javascript; charset=utf-8'),
                     '/app.js': ('app.js', 'text/javascript; charset=utf-8')}
            files.update({f'/patterns/pattern-{i:02}.webp': (f'patterns/pattern-{i:02}.webp', 'image/webp')
                          for i in range(1, 9)})
            files.update({f'/clip-studio.{ext}': (f'clip-studio.{ext}', mime)
                          for ext, mime in [('html', 'text/html; charset=utf-8'),
                                            ('css', 'text/css; charset=utf-8'),
                                            ('js', 'text/javascript; charset=utf-8')]})
            files.update({f'/video-split.{ext}': (f'video-split.{ext}', mime)
                          for ext, mime in [('html', 'text/html; charset=utf-8'),
                                            ('css', 'text/css; charset=utf-8'),
                                            ('js', 'text/javascript; charset=utf-8')]})
            files['/video-split-model.js'] = ('video-split-model.js', 'text/javascript; charset=utf-8')
            files['/video-split-delete.js'] = ('video-split-delete.js', 'text/javascript; charset=utf-8')
            files['/video-split-audio.js'] = ('video-split-audio.js', 'text/javascript; charset=utf-8')
            for name in ('clip-studio-tools','clip-studio-preview','studio-decorations','studio-fonts-ui','studio-inspector', 'studio-caption-size','studio-caption-design','studio-caption-templates','studio-image-editor','studio-image-geometry','page-lifecycle','edit-session','studio-captions-ui','studio-export-check','result-browser','reaction-times','studio-history'):
                files[f'/{name}.js'] = (f'{name}.js', 'text/javascript; charset=utf-8')
            files['/clip-studio-model.js'] = ('clip-studio-model.js', 'text/javascript; charset=utf-8')
            files['/analysis-scope-preview.js'] = ('analysis-scope-preview.js', 'text/javascript; charset=utf-8')
            files['/context-clips.js']=('context-clips.js','text/javascript; charset=utf-8')
            files['/context-clip-evidence.js']=('context-clip-evidence.js','text/javascript; charset=utf-8')
            files.update({f'/{name}.js': (f'{name}.js', 'text/javascript; charset=utf-8')
                          for name in ('preview-toast', 'mini-player', 'workspace-layout', 'workspace-status', 'settings-panel', 'version-picker', 'context-clip-controls', 'queue', 'queue-saved', 'queue-options', 'vod-label', 'reports', 'help', 'help-content', 'voice-model-help', 'voice-tool-status', 'voice-tabs', 'context-background', 'context-inputs', 'context-external', 'context-fallback', 'reactions', 'player', 'speech', 'voices', 'voice-review', 'voice-suggestions', 'explore', 'timeline', 'context', 'project-delete', 'folders', 'compute', 'task-timing', 'audio-preview', 'context-reactions', 'context-copy', 'context-comment-model', 'context-comment-time', 'player-sequence', 'context-tree', 'context-interpretations')})
            if path in files:
                filename, mime = files[path]
                content = (WEB / filename).read_bytes()
                self.send_headers(200, mime, len(content))
                self.end_headers()
                if body:
                    self.wfile.write(content)
                return
            if path != '/file':
                self.reply(404, {'error': '파일 경로가 없습니다'})
                return
            try:
                query = parse_qs(urlsplit(self.path).query)
                root, vod, kind, key = (query[name][0] for name in ('root', 'vod_id', 'kind', 'key'))
                data = manager.view(root, vod)
                if kind == 'studio':
                    target = manager.studio.file(project_path(root, vod), query['run'][0], key)
                elif kind == 'voices':
                    from .storage import read_json
                    project = project_path(root, vod)
                    value = voice_store.state(project)
                    if key in ('original', 'vocals', 'background'):
                        stem = read_json(voice_store.local(project, f"stems/{value['stem']}/result.json"))
                        relative = stem['files'][key]
                    else:
                        relative = value['exports'][key]
                    target = voice_store.local(project, relative)
                elif kind == 'speech':
                    relative = data['speech']['separated_audio']['target'] if key == 'sam' else data['speech']['audio']['file'] if key in ('audio', 'audio-save') else data['speech']['exports'][key]
                    target = speech_file(project_path(root, vod), relative)
                else:
                    task = data['tasks'][kind]
                    if kind == 'video' and task['state'] != 'complete':
                        raise ValueError('영상 검사가 완료되지 않았습니다')
                    target = asset_path(project_path(root, vod), task['assets'][key])
                self.send_file(target, body, download=(key not in ('playback', 'audio', 'sam') and not (kind == 'voices' and key in ('original','vocals','background'))))
            except (ValueError, KeyError, OSError) as error:
                self.reply(404, {'error': safe_error(error)})

        def send_file(self, path, body, download):
            with path.open('rb') as file:
                size = path.stat().st_size
                requested = self.headers.get('Range')
                try:
                    start, end = byte_range(requested, size)
                except ValueError:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                mime = {'.mp4': 'video/mp4', '.m4a': 'audio/mp4', '.wav': 'audio/wav'}.get(path.suffix, 'application/octet-stream')
                self.send_headers(206 if requested else 200, mime, end - start + 1)
                self.send_header('Accept-Ranges', 'bytes')
                if requested:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                if download:
                    self.send_header('Content-Disposition', f"attachment; filename=\"download{path.suffix}\"; filename*=UTF-8''{quote(path.name)}")
                self.end_headers()
                if body:
                    file.seek(start)
                    remaining = end - start + 1
                    try:
                        while remaining:
                            chunk = file.read(min(1024 * 1024, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

    server = GuiServer(('127.0.0.1', port), Handler)
    return server, f'http://127.0.0.1:{server.server_port}{prefix}/'
