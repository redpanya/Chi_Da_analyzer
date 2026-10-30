"""다운로드 구간의 채팅 경계와 원본/구간 시각을 함께 보존한다."""
from .download_scope import bounds


def select(messages, scope):
    if scope is None:
        return messages
    return [m for m in messages if scope['start_ms'] <= m['playerMessageTime'] < scope['end_ms']]


def timing(item, scope):
    if scope is None:
        return item
    ms = item['offset_ms']-scope['start_ms']; seconds, fraction = divmod(ms,1000)
    return item | {'vod_offset_ms':item['offset_ms'], 'clip_offset_ms':ms,
                   'clip_timecode':f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}.{fraction:03}'}
