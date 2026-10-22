"""한 전사·화자 실행 폴더만 휴지통으로 이동한다. 참조 결과는 함께 삭제하지 않는다."""
from . import speech_store, voice_store, deletion
from .analysis_inputs import run_id, transcripts
from .storage import Conflict, read_json, save_json, stamp


def _trash(path, store, id, changes):
    folder = store.local(path, f'runs/{id}')
    if not folder.is_dir() or any(p.is_symlink() for p in folder.rglob('*')):
        raise ValueError('삭제할 데이터 폴더 또는 연결 파일을 확인하세요')
    before = store.state(path)
    # 중단·디스크 오류가 있어도 사라진 실행을 다시 선택하거나 이어받지 않는다.
    after = before | changes | {'updated_at': stamp(),
        'deleted_runs': list(dict.fromkeys(before.get('deleted_runs', []) + [id]))}
    save_json(store.local(path, 'state.json'), after)
    try:
        deletion.trash_path(folder)
    except Exception:
        if folder.exists():
            save_json(store.local(path, 'state.json'), before)
        raise


def speech(path, id):
    run_id(id)
    from .context_exchange import protect_input
    protect_input(path,id,'transcript_run')
    if id not in {r['id'] for r in transcripts(path)}:
        raise ValueError('삭제할 전사 데이터를 목록에서 선택하세요')
    state = voice_store.state(path)
    pending = state.get('pending_diarization') or {}
    if pending.get('signature', {}).get('transcript_run') == id:
        raise Conflict('중단된 화자 분석이 사용하는 전사입니다. 해당 화자 작업을 완료한 뒤 분석 데이터를 삭제하세요')
    for file in voice_store.local(path, 'runs').glob('*/result.json'):
        if file.parent.name in state.get('deleted_runs', []):
            continue
        try:
            voice_store.local(path, str(file.relative_to(path/'voices')))
            result = read_json(file)
            if result['transcript_run'] == id:
                raise Conflict('이 전사를 사용하는 화자 분석이 있습니다. 연결된 화자 분석 데이터를 먼저 삭제하세요')
        except (OSError, ValueError, KeyError, TypeError) as error:
            if isinstance(error, Conflict):
                raise
            raise Conflict('화자 데이터의 연결 관계를 확인하지 못해 전사를 삭제하지 않았습니다') from None
    value = speech_store.state(path)
    changes = {}
    if value.get('run') == id:
        changes.update(run=None, exports={}, state='idle', progress={}, timing=None, compute=None,
                       message='전사 데이터를 휴지통으로 이동했습니다. 사용할 전사를 선택하거나 새로 전사하세요')
    if value.get('pending_run') == id:
        changes['pending_run'] = None
    _trash(path, speech_store, id, changes)


def voices(path, id):
    run_id(id)
    from .context_exchange import protect_input
    protect_input(path,id,'speaker_run')
    value = voice_store.state(path)
    if id not in value.get('runs', []):
        raise ValueError('삭제할 화자 분석 데이터를 목록에서 선택하세요')
    changes = {'runs': [r for r in value['runs'] if r != id]}
    if value.get('run') == id:
        changes.update(run=None, exports={}, state='idle', progress={}, timing=None,
                       message='화자 데이터를 휴지통으로 이동했습니다. 사용할 분석을 선택하세요')
    if (value.get('pending_diarization') or {}).get('id') == id:
        changes['pending_diarization'] = None
    _trash(path, voice_store, id, changes)
