"""원본 페이지 기반 재개와 메모리 사용을 제한한 채팅 내보내기·경계 검사."""

from contextlib import closing
import csv
from datetime import datetime, timezone
import json
import heapq
from pathlib import Path
import sqlite3
import uuid

from .source import Cancelled, check_cancel, request_json
from .storage import save_json, read_json
from . import chat_boundary


def validate(payload, cursor):
    if not isinstance(payload, dict) or payload.get('code') != 200 or not isinstance(payload.get('content'), dict):
        raise ValueError('정상 채팅 응답이 아닙니다')
    content = payload['content']
    if 'nextPlayerMessageTime' not in content or not isinstance(content.get('videoChats'), list) or not isinstance(content.get('previousVideoChats'), list):
        raise ValueError('채팅 응답 형식이 바뀌었습니다')
    messages, following = content['videoChats'], content['nextPlayerMessageTime']
    times = [m.get('playerMessageTime') if isinstance(m, dict) else None for m in messages]
    if any(type(t) is not int or t < 0 for t in times) or times != sorted(times):
        raise ValueError('채팅 시각이 올바르지 않거나 역행합니다')
    if following is not None and (type(following) is not int or following <= cursor or (times and following < times[-1])):
        raise ValueError('다음 채팅 커서가 반복되거나 역행합니다')
    return messages, following


def fetch(vod, cursor, stop):
    return request_json(f'https://api.chzzk.naver.com/service/v1/videos/{vod}/chats?playerMessageTime={cursor}', stop)


def fingerprint(message):
    return chat_boundary.fingerprint(message)


def row(message, vod, sequence, status):
    failed = False
    try:
        profile = json.loads(message.get('profile') or '{}')
        if not isinstance(profile, dict):
            raise ValueError()
    except (ValueError, TypeError):
        profile, failed = {}, True
    offset = message['playerMessageTime']
    seconds, ms = divmod(offset, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    epoch, sent = message.get('messageTime'), None
    if type(epoch) is int:
        try:
            sent = datetime.fromtimestamp(epoch / 1000, timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            pass
    return {'vod_id': vod, 'collection_status': status, 'offset_ms': offset,
            'timecode': f'{hours:02}:{minutes:02}:{seconds:02}.{ms:03}',
            'sent_at_epoch_ms': epoch, 'sent_at_iso': sent, 'nickname': profile.get('nickname'),
            'user_id_hash': message.get('userIdHash'), 'text': message.get('content'),
            'message_type': message.get('messageTypeCode'), 'message_status': message.get('messageStatusType'),
            'page_sequence': sequence, 'profile_parse_failed': failed}


def safe_csv(value):
    return "'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r')) else value


def export(project, paths, label, stop, extras=None):
    generation = project.path / 'exports' / uuid.uuid4().hex
    generation.mkdir(parents=True)
    db = sqlite3.connect(generation / 'counts.sqlite')
    db.execute('CREATE TABLE counts (fingerprint TEXT PRIMARY KEY, amount INTEGER NOT NULL)')
    vod = project.data['vod_id']
    count, failed = 0, 0
    extra_iterator = chat_boundary.extra_messages(extras) if extras else None
    try:
        with (generation / 'chat.json').open('w', encoding='utf-8') as js, (generation / 'chat.jsonl').open('w', encoding='utf-8') as jl, (generation / 'chat.csv').open('w', encoding='utf-8-sig', newline='') as cs, (generation / 'chat.txt').open('w', encoding='utf-8') as tx:
            js.write(json.dumps({'vod_id': vod, 'collection_status': label, 'time_basis': 'VOD 경과 밀리초'}, ensure_ascii=False)[:-1] + ',"messages":[\n')
            tx.write(f'VOD {vod} / {label} / 영상 경과시간 기준\n')
            writer = csv.DictWriter(cs, fieldnames=list(row({'playerMessageTime': 0}, vod, 0, label)))
            writer.writeheader()
            def original_messages():
                for sequence, path in enumerate(paths):
                    check_cancel(stop)
                    wrapper = read_json(path)
                    for message in wrapper['response']['content']['videoChats']:
                        yield message, sequence
            messages = original_messages()
            if extras:
                messages = heapq.merge(messages, extra_iterator, key=lambda item: item[0]['playerMessageTime'])
            for message, sequence in messages:
                check_cancel(stop)
                item = row(message, vod, sequence, label)
                encoded = json.dumps(item, ensure_ascii=False)
                js.write((',' if count else '') + encoded + '\n')
                jl.write(encoded + '\n')
                writer.writerow({key: safe_csv(value) for key, value in item.items()})
                tx.write(f"[{item['timecode']}] {json.dumps(item['nickname'], ensure_ascii=False)}: {json.dumps(item['text'], ensure_ascii=False)}\n")
                db.execute('INSERT INTO counts VALUES (?, 1) ON CONFLICT(fingerprint) DO UPDATE SET amount=amount+1', (fingerprint(message),))
                count += 1
                failed += item['profile_parse_failed']
            js.write(']}\n')
        db.commit()
    finally:
        if extra_iterator is not None: extra_iterator.close()
        db.close()
    save_json(generation / 'summary.json', {'status': label, 'messages': count, 'profile_parse_failed': failed})
    return generation, count


def collect(project, stop):
    vod = project.data['vod_id']
    pages = project.path / 'chat-pages'
    pages.mkdir(exist_ok=True)
    if project.data['metadata'].get('chat_enabled') is False:
        generation, _ = export(project, [], '채팅 미제공', stop)
        project.update('chat', state='unavailable', message='서비스에서 채팅을 제공하지 않는 VOD입니다',
                       progress={'messages': 0, 'pages': 0}, assets=export_assets(project, generation))
        return
    cursor, count, previous, overlap = 0, 0, None, False
    paths, cursors, boundaries = [], {0}, {}
    cached = sorted(p for p in pages.glob('*.json') if not p.name.startswith('._'))
    paused = False
    try:
        for sequence in range(100000):
            check_cancel(stop)
            path = pages / f'{sequence:06}.json'
            if sequence < len(cached):
                if path != cached[sequence]:
                    raise ValueError('보존한 채팅 페이지 번호에 빈 구간이 있습니다')
                wrapper = read_json(path)
                if wrapper.get('vod_id') != vod or wrapper.get('cursor') != cursor:
                    raise ValueError('보존한 채팅의 VOD·커서 식별 정보가 다릅니다')
                payload = wrapper['response']
            else:
                payload = fetch(vod, cursor, stop)
                try:
                    validate(payload, cursor)
                except ValueError:
                    save_json(project.path / 'diagnostics' / f'chat-error-{uuid.uuid4().hex}.json', payload)
                    raise
                save_json(path, {'vod_id': vod, 'cursor': cursor, 'response': payload})
            messages, following = validate(payload, cursor)
            if messages:
                overlap |= previous is not None and messages[0]['playerMessageTime'] <= previous
                previous = messages[-1]['playerMessageTime']
            paths.append(path)
            count += len(messages)
            cursor = following
            progress = {'pages': len(paths), 'messages': count, 'last_ms': previous, 'next_cursor': cursor}
            save_json(project.path / 'chat-checkpoint.json', progress)
            project.update('chat', state='running', message='제공되는 채팅 범위를 순서대로 받고 있습니다', progress=progress)
            if cursor is None:
                if sequence + 1 < len(cached):
                    raise ValueError('종료 커서 뒤에 추가 보존 페이지가 있습니다')
                break
            cursors.add(cursor - 1)
            if messages and cursor == messages[-1]['playerMessageTime']:
                boundaries[cursor-1] = sequence
            if sequence >= len(cached) and stop.wait(.2):
                raise Cancelled()
        else:
            raise ValueError('수집 페이지 한도를 넘었습니다. 검증이 필요합니다')
    except Cancelled:
        paused = True
    if paused:
        # 원본 페이지는 이미 안전하게 저장됐다. 사용자가 중단한 결과만 별도 묶음으로 내보낸다.
        import threading
        generation, count = export(project, paths, '일부 수집 · 중단됨', threading.Event())
        project.update('chat', state='paused', message='중단했습니다. 저장된 페이지에서 이어받을 수 있습니다',
                       assets=export_assets(project, generation))
        return
    project.update('chat', state='exporting', message='채팅 결과를 정리하고 경계를 검사하고 있습니다')
    generation, count = export(project, paths, '제공 범위 순회 완료 · 경계 검증 전', stop)
    checks, fetched, reused = [], 0, 0
    database = generation/'counts.sqlite'
    with closing(sqlite3.connect(database)) as db:
        chat_boundary.prepare(db)
        for cursor in sorted(cursors):
            check_cancel(stop)
            saved = project.path/'diagnostics/chat-audit'/f'{cursor}.json'
            if saved.is_symlink() or saved.parent.is_symlink():
                raise ValueError('채팅 경계 검사 경로의 연결 파일은 사용할 수 없습니다')
            if saved.exists():
                payload = read_json(saved)
                reused += 1
            else:
                payload = fetch(vod, cursor, stop)
                validate(payload, cursor)
                save_json(saved, payload)
                fetched += 1
            messages, _ = validate(payload, cursor)
            checks.append(chat_boundary.reconcile(db, messages, cursor, boundaries.get(cursor)))
            if stop.wait(.15): raise Cancelled()
    valid = not overlap and all(not c['missing'] and not c['single_timestamp_full_page'] for c in checks)
    audit = {'checks': checks, 'overlap': overlap, 'match': valid, 'revision': 2,
             'cached_requests': reused, 'network_requests': fetched,
             'recovered': sum(c['recovered'] for c in checks)}
    save_json(generation/'boundary-recovery.json', audit)
    if not (project.path/'diagnostics/chat-audit.json').exists():
        save_json(project.path/'diagnostics/chat-audit.json', audit)
    recovered = audit['recovered']
    label = ('제공 범위 순회·경계 대조 완료' if count or recovered else '현재 제공된 채팅 없음') if valid else '제공 범위 순회 · 경계 검증 필요'
    # 원본 페이지와 이전 내보내기는 유지하고, 보완분을 시간순으로 합친 새 묶음만 연결한다.
    final, count = export(project, paths, label, stop, extras=database)
    save_json(final/'boundary-recovery.json', audit | {'source_generation': str(generation.relative_to(project.path))})
    progress = project.snapshot()['tasks']['chat'].get('progress', {}) | {'messages': count}
    message = label+(f' · 경계 누락 {recovered}건 보완' if recovered else '')
    missing = sum(c['missing'] for c in checks)
    if not valid: message += f' · 미확인 {missing}건'+(' · 페이지 겹침' if overlap else '')+(' · 같은 시각의 응답 한도 도달' if any(c['single_timestamp_full_page'] for c in checks) else '')
    project.update('chat', state=('complete' if count else 'empty') if valid else 'review',
                   message=message, assets=export_assets(project, final), progress=progress,
                   verification={'boundary_requests': len(checks), 'missing': missing, 'recovered': recovered,
                                 'cached_requests': reused, 'network_requests': fetched,
                                 'audit': str((final/'boundary-recovery.json').relative_to(project.path)),
                                 'scope': '저장된 제공 응답의 경계 대조이며 삭제 전 역사적 전체 건수 대조가 아님'})


def export_assets(project, generation):
    return {ext: str((generation / f'chat.{ext}').relative_to(project.path)) for ext in ('json', 'jsonl', 'csv', 'txt')}
