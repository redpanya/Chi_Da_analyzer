"""원문은 남기고 반복 후보와 내용 근거가 부족한 전사를 구별한다."""
from collections import Counter
from difflib import SequenceMatcher
import re

REVISION = 1


def repetitive(text):
    words = re.findall(r'[\w]+', text.casefold())
    if len(words) < 12: return False
    # 실제 문장 두 번, 짧은 인사·감탄은 제외하지 않는다.
    for size in range(1, min(8, len(words)//6)+1):
        grams = [tuple(words[i:i+size]) for i in range(0, len(words)-size+1, size)]
        if len(grams) >= 6 and Counter(grams).most_common(1)[0][1]*size >= len(words)*.85:
            return True
    return False


def annotate(rows):
    result = []
    for row in rows:
        notes = []
        if repetitive(row['text']): notes.append('문장 내부의 과도한 반복 · 내용 근거 확인 필요')
        value = row | {'quality_revision': REVISION, 'quality_review': bool(notes),
                       'quality_notes': notes, 'repeat_candidate': False, 'repeat_review': False}
        if result:
            previous = result[-1]
            if (len(row['text']) >= 4 and 0 <= row['start_ms']-previous['end_ms'] <= 15000
                    and SequenceMatcher(None, previous['text'], row['text']).ratio() >= .9):
                previous['repeat_candidate'] = value['repeat_candidate'] = True
        result.append(value)
    return result
