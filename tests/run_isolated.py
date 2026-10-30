"""검사에서 발생한 진단 로그를 사용자의 앱 기록과 분리한다."""
from pathlib import Path
import tempfile
import unittest
from archive import runtime

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='chida-tests-') as temp:
        runtime.SUPPORT=Path(temp)
        unittest.main(module=None)
