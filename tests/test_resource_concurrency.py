"""독립 실행과 충돌 대기 경계를 실제 파일 잠금으로 검증한다."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from archive.storage import ProjectLock, ResourceBusy


class ResourceConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.a = Path(self.tmp.name) / 'a'
        self.b = Path(self.tmp.name) / 'b'

    def test_download_and_ai_have_separate_single_lanes(self):
        with ProjectLock(self.a, write=['media'], lanes=['download']):
            with ProjectLock(self.b, write=['context'], lanes=['context']):
                with ProjectLock(self.b, read=['media'], write=['speech']):
                    with self.assertRaises(ResourceBusy):
                        ProjectLock(self.b, write=['media'], lanes=['download'])
                    with self.assertRaises(ResourceBusy):
                        ProjectLock(self.a, write=['context'], lanes=['context'])
        with ProjectLock(self.a, write=['media'], lanes=['download']):
            pass

    def test_readers_and_independent_outputs_share_project(self):
        with ProjectLock(self.a, read=['media'], write=['speech']):
            with ProjectLock(self.a, read=['media'], write=['studio-run-one']):
                with ProjectLock(self.a, read=['media'], write=['studio-run-two']):
                    with self.assertRaises(ResourceBusy):
                        ProjectLock(self.a, read=['speech'], write=['voices'])
                    with self.assertRaises(ResourceBusy):
                        ProjectLock(self.a, write=['media'])
                    with self.assertRaises(ResourceBusy):
                        ProjectLock(self.a)
        with ProjectLock(self.a):
            with self.assertRaises(ResourceBusy):
                ProjectLock(self.a, read=['media'])

    def test_partial_acquisition_releases_lanes_and_file_locks(self):
        with ProjectLock(self.a, write=['speech']):
            with self.assertRaises(ResourceBusy):
                ProjectLock(self.a, read=['media', 'speech'], lanes=['context'])
            with ProjectLock(self.a, write=['media'], lanes=['context']):
                pass
        with self.assertRaises(RuntimeError):
            with ProjectLock(self.a, write=['speech'], lanes=['context']):
                raise RuntimeError('실패')
        with ProjectLock(self.a, write=['speech'], lanes=['context']):
            pass

    def test_three_transcriptions_leave_clip_and_independent_work_available(self):
        with ExitStack() as jobs:
            for i in range(3):
                jobs.enter_context(ProjectLock(self.a / str(i), read=['media'], write=['speech'], lanes=['transcribe']))
            with self.assertRaises(ResourceBusy):
                ProjectLock(self.b, write=['speech'], lanes=['transcribe'])
            with ProjectLock(self.a / '0', read=['media'], write=['studio-run']):
                pass
        with ProjectLock(self.b, write=['speech'], lanes=['transcribe']):
            pass
