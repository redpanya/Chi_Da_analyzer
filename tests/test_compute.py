"""처리 장치 선택은 OS·드라이버 실패·기존 작업 보존을 함께 지켜야 한다."""
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from archive import compute, runtime
from archive.jobs import Manager
from archive.storage import Conflict
from archive.storage import save_json, read_json
from archive import speech_recognition
from archive.source import Cancelled


class ComputeTests(unittest.TestCase):
    def tearDown(self): compute.probe.cache_clear()

    def test_mac_keeps_existing_metal_arguments_and_rejects_setting(self):
        with patch.object(compute, 'windows', return_value=False), patch.object(compute.shutil, 'which', return_value='native'):
            self.assertEqual(compute.status(), {'visible':False})
            self.assertEqual(compute.select('llama-server')['args'], ['-ngl','99'])
            self.assertEqual(compute.select('whisper-cli')['args'], [])
            with self.assertRaises(ValueError): compute.apply('cpu')

    def test_choice_persists_without_replacing_other_settings(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(runtime,'SUPPORT',Path(folder)), patch.object(compute,'windows',return_value=True):
            runtime.save_settings(library='기존 보관함', models='기존 모델')
            self.assertEqual(compute.mode(), 'cpu')
            compute.apply('hybrid'); self.assertEqual(compute.mode(),'hybrid')
            self.assertEqual(runtime.settings()['models'],'기존 모델')
            for invalid in (None, [], 'cuda', True):
                with self.assertRaises(ValueError): compute.apply(invalid)
            self.assertEqual(compute.mode(),'hybrid')

    def test_cpu_gpu_and_unavailable_routes_use_separate_binaries(self):
        with patch.object(compute,'windows',return_value=True), patch.object(compute.shutil,'which',return_value='cpu.exe'), patch.object(compute,'gpu_binary',return_value=Path('gpu.exe')):
            for mode, available, backend in [('cpu',True,'cpu'),('hybrid',True,'vulkan'),('hybrid',False,'cpu')]:
                with self.subTest(mode=mode,available=available), patch.object(compute,'status',return_value={'mode':mode,'available':available,'note':'상태'}):
                    speech=compute.select('whisper-cli'); summary=compute.select('llama-server')
                    self.assertEqual(speech['backend'],backend)
                    self.assertEqual(summary['binary'],'gpu.exe' if backend=='vulkan' else 'cpu.exe')
                    self.assertEqual(summary['args'],['-ngl','auto' if backend=='vulkan' else '0'])
                    self.assertEqual(speech['args'],[] if backend=='vulkan' else ['--no-gpu'])

    def test_probe_uses_device_rows_not_success_exit_or_log_mentions(self):
        with patch.object(compute,'windows',return_value=False):
            for text,code,success in [(b'Available devices:\n  (none)\n',0,False),
                    (b'Available devices:\n  Vulkan0: Example GPU (6144 MiB, 4096 MiB free)\n',0,True),
                    (b'Vulkan driver is missing',0,False),(b'Vulkan0: Example\n',1,False)]:
                compute.probe.cache_clear()
                with patch.object(compute.subprocess,'run',return_value=SimpleNamespace(stdout=text,returncode=code)):
                    self.assertEqual(compute.probe('gpu.exe')['available'],success)
            compute.probe.cache_clear()
            with patch.object(compute.subprocess,'run',side_effect=subprocess.TimeoutExpired('gpu',15)):
                self.assertFalse(compute.probe('gpu.exe')['available'])

    def test_busy_rejects_change_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            manager=Manager(folder); manager.analysis_path=Path(folder)
            with patch.object(compute,'apply') as apply:
                with self.assertRaises(Conflict):manager.compute_settings({'mode':'hybrid'})
                apply.assert_not_called()

    def test_missing_gpu_payload_falls_back_in_status(self):
        with patch.object(compute,'windows',return_value=True), patch.object(compute,'mode',return_value='hybrid'), patch.object(compute,'gpu_binary',return_value=Path('/존재하지-않는-실행기')):
            value=compute.status(); self.assertFalse(value['available']); self.assertIn('CPU',value['note'])

    def test_whisper_receives_selected_flags_and_preserves_cancellation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder); source=path/'원본.wav'; source.write_bytes(b'original')
            plan={'binary':'cpu.exe','backend':'cpu','args':['--no-gpu'],'note':'CPU'}
            def engine(args, *unused):
                self.assertEqual(args[0],'cpu.exe');self.assertIn('--no-gpu',args)
                output=Path(args[args.index('-of')+1]).with_suffix('.json')
                save_json(output,{'transcription':[{'offsets':{'from':0,'to':500},'text':'발언'}]})
            call=lambda:speech_recognition.recognize(plan['binary'],path/'모델',source,path,0,1000,'ko',None,
                threading.Event(),None,{'vad':'off'},plan)
            with patch.object(speech_recognition.media,'chunk_audio',side_effect=lambda src,target,*args:target.touch()), patch.object(speech_recognition.media,'process',side_effect=engine):
                self.assertEqual(call()['transcription'][0]['text'],'발언')
                self.assertEqual(read_json(path/'00000-compute.json')['backend'],'cpu')
            plan.update(binary='gpu.exe',backend='vulkan',args=[])
            with patch.object(speech_recognition.media,'chunk_audio',side_effect=lambda src,target,*args:target.touch()):
                with patch.object(speech_recognition.media,'process',side_effect=ValueError('메모리 부족')):
                    with self.assertRaisesRegex(ValueError,'CPU만 사용'):call()
                with patch.object(speech_recognition.media,'process',side_effect=Cancelled()):
                    with self.assertRaises(Cancelled):call()
                with patch.object(speech_recognition.media,'process',side_effect=OSError(28,'공간 부족')):
                    with self.assertRaises(OSError) as error:call()
                    self.assertEqual(error.exception.errno,28)
            self.assertEqual(source.read_bytes(),b'original')


if __name__ == '__main__': unittest.main()
