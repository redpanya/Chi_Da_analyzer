"""GGUF와 같은 llama.cpp 토크나이저로 실제 전송 문자열을 계산한다."""
import ast
import shutil
import subprocess
import time
from .source import check_cancel

CONTEXT = 16384
OUTPUT = 3600
TARGET = 4800
MARGIN = 512


class Tokenizer:
    def __init__(self, path, stop):
        self.binary = shutil.which('llama-tokenize')
        if not self.binary:raise ValueError('문맥 토크나이저가 없습니다. 새 앱 패키지를 설치하세요')
        self.path, self.stop = path, stop
        self.cache = {}
        self.seconds = 0.0

    def count(self, text):
        if text in self.cache:return self.cache[text]
        check_cancel(self.stop)
        started = time.monotonic()
        child = subprocess.Popen([self.binary, '-m', str(self.path), '--stdin', '--ids', '--log-disable', '--offline'],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            data = text.encode('utf-8')
            while True:
                try:out, err = child.communicate(input=data, timeout=.25);break
                except subprocess.TimeoutExpired:
                    data = None
                    check_cancel(self.stop)
                    if time.monotonic()-started > 60:raise ValueError('토큰 계산 제한 시간을 넘었습니다')
            if child.returncode:raise ValueError('모델 토크나이저 실행 실패: '+err.decode('utf-8','replace')[-300:])
            ids = ast.literal_eval(out.decode('utf-8'))
            if not isinstance(ids,list) or any(type(x) is not int for x in ids):raise ValueError('토큰 응답 형식이 올바르지 않습니다')
            self.cache[text] = len(ids)
            return len(ids)
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=2)
                except subprocess.TimeoutExpired:child.kill();child.wait()
            self.seconds += time.monotonic()-started


def fit(rows, build, tokenizer, budget=TARGET):
    """실제 프롬프트가 예산에 들어가는 가장 긴 접두 범위. 글자 수를 토큰으로 취급하지 않는다."""
    if not rows:return []
    lo, hi = 1, len(rows)
    if tokenizer.count(build(rows[:1])) > budget:raise ValueError('발언 하나와 열린 문맥이 입력 예산을 넘었습니다')
    while lo < hi:
        mid = (lo+hi+1)//2
        if tokenizer.count(build(rows[:mid])) <= budget:lo = mid
        else:hi = mid-1
    return rows[:lo]
