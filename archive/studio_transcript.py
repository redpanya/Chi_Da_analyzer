"""전사 원문을 변경하지 않고 저장된 발언을 편집 구간으로 옮긴다."""
from .video_replacement import logical_source
from . import analysis_inputs, caption_sync, clip_contract, speech_store


def clip(path, vod, run_id, segment_id):
    analysis_inputs.run_id(run_id)
    run = speech_store.manifest(path)
    if not run or run['id'] != run_id:
        raise ValueError('전사 버전이 변경됐습니다. 목록을 다시 불러온 뒤 담아주세요')
    row = next((r for r in speech_store.segments(path, run) if r['id'] == segment_id), None)
    if row is None:
        raise ValueError('담을 전사 구간을 찾을 수 없습니다. 목록을 다시 불러오세요')
    src = clip_contract.media(path, vod)
    audio = speech_store.audio_for_run(path, run)
    if not audio or audio.get('source') != logical_source(src.get('data', {}), src['identity']):
        raise ValueError('현재 영상과 다른 입력의 전사입니다. 영상과 전사 버전을 확인하세요')
    text = speech_store.corrections(path, run).get(row['id'], row['text'])
    start, end = caption_sync.interval(row, caption_sync.resolve(path, src['data'], audio))
    if end-start < 100:
        raise ValueError('현재 영상 안에 클립으로 담을 발언이 0.1초 이상 남아 있지 않습니다')
    item = dict(id=f"transcript:{run_id}:{row['id']}", title=' '.join(text.split())[:200] or '전사 구간',
                start_ms=src['origin']+start, end_ms=src['origin']+end)
    # 전사는 재생본 상대 시각, 편집 초안은 원본 VOD 시각이다.
    request = clip_contract.validate({'clips': [item]}, src, draft=True)
    return request
