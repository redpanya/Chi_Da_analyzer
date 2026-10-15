"""저장된 경계 응답의 발생 횟수로 같은 밀리초에서 잘린 메시지만 보완한다."""
from collections import Counter
import json
import sqlite3


def fingerprint(message):
    return json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def event_key(message):
    return fingerprint({key: message.get(key) for key in
                        ('playerMessageTime', 'messageTime', 'userIdHash', 'messageTypeCode', 'content')})


def prepare(db):
    db.execute('CREATE TABLE events (event TEXT PRIMARY KEY, amount INTEGER NOT NULL)')
    db.execute('CREATE TABLE extras (fingerprint TEXT PRIMARY KEY, amount INTEGER NOT NULL, offset INTEGER, sequence INTEGER, cursor INTEGER)')
    for raw, amount in db.execute('SELECT fingerprint, amount FROM counts'):
        db.execute('INSERT INTO events VALUES (?, ?) ON CONFLICT(event) DO UPDATE SET amount=amount+excluded.amount',
                   (event_key(json.loads(raw)), amount))


def amount(db, table, column, key):
    row = db.execute(f'SELECT amount FROM {table} WHERE {column}=?', (key,)).fetchone()
    return row[0] if row else 0


def reconcile(db, messages, cursor, boundary_sequence):
    dense = len(messages) >= 200 and len({m['playerMessageTime'] for m in messages}) == 1
    observed = Counter(event_key(m) for m in messages)
    missing = recovered = changed = 0
    for raw, count in Counter(fingerprint(m) for m in messages).items():
        delta = max(0, count-amount(db, 'counts', 'fingerprint', raw))
        if not delta: continue
        message = json.loads(raw); event = event_key(message)
        event_delta = max(0, observed[event]-amount(db, 'events', 'event', event))
        stable = type(message.get('messageTime')) is int and isinstance(message.get('userIdHash'), str)
        boundary = boundary_sequence is not None and message['playerMessageTime'] == cursor+1
        if dense or not stable or not boundary or event_delta < delta:
            missing += delta
            if event_delta < delta: changed += delta
            continue
        db.execute('INSERT INTO counts VALUES (?, ?) ON CONFLICT(fingerprint) DO UPDATE SET amount=amount+excluded.amount', (raw, delta))
        db.execute('INSERT INTO events VALUES (?, ?) ON CONFLICT(event) DO UPDATE SET amount=amount+excluded.amount', (event, delta))
        db.execute('INSERT INTO extras VALUES (?, ?, ?, ?, ?) ON CONFLICT(fingerprint) DO UPDATE SET amount=amount+excluded.amount',
                   (raw, delta, message['playerMessageTime'], boundary_sequence, cursor))
        recovered += delta
    db.commit()
    return {'cursor': cursor, 'missing': missing, 'recovered': recovered,
            'response_changed': changed, 'single_timestamp_full_page': dense}


def extra_messages(file):
    db = sqlite3.connect(file)
    try:
        for raw, count, sequence in db.execute('SELECT fingerprint, amount, sequence FROM extras ORDER BY offset, rowid'):
            for _ in range(count):
                yield json.loads(raw), sequence
    finally:
        db.close()
