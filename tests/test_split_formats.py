"""컨테이너·코덱을 바꾼 합성 자료의 분할과 원본 패킷 보존 검사."""
import hashlib
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from archive.jobs import Manager
from archive.split_jobs import Splitter
from archive import split_media, split_formats
from test_video_split import packets


class SplitFormats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = subprocess.check_output(['ffmpeg', '-hide_banner', '-encoders'], stderr=subprocess.DEVNULL, text=True)
        cls.encoders = {row.split()[1] for row in rows.splitlines() if len(row.split()) > 1}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = Manager(self.root/'library')
        self.splitter = self.manager.splitter = Splitter(self.manager, self.root/'state')

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def fixture(self, extension, video='libx264', audio='aac', open_gop=False):
        if video not in self.encoders or audio not in self.encoders:
            self.skipTest(f'검증 자료 생성 인코더 미설치: {video} / {audio}')
        file = self.root/('테스트 공백'+extension)
        options = ['-preset', 'ultrafast'] if video in ('libx264', 'libx265') else []
        if video == 'libx265':
            options += ['-x265-params', f'log-level=error:pools=1:frame-threads=1:open-gop={int(open_gop)}', '-tag:v', 'hvc1']
        if video in ('libvpx-vp9', 'libvpx'):
            options += ['-deadline', 'realtime', '-cpu-used', '8']
        if video == 'libsvtav1':
            options += ['-preset', '12', '-crf', '45', '-svtav1-params', 'lp=1']
        if video == 'prores_ks':
            options += ['-pix_fmt', 'yuv422p10le']
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x96:rate=12:duration=6',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=6',
            '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000:duration=6',
            '-map', '0:v', '-map', '1:a', '-map', '2:a', '-c:v', video, '-threads', '1',
            '-g', '12', *options, '-c:a', audio, *(['-strict', '-2', '-ac', '2'] if audio == 'vorbis' else []), '-metadata:s:a:0', 'language=kor',
            '-metadata:s:a:1', 'language=eng', '-disposition:a:0', 'default', '-disposition:a:1', '0',
            '-f', split_formats.output({'path': str(file)})[1], str(file)], check=True, timeout=60)
        return file

    def finish(self):
        self.splitter.job.thread.join(30)
        self.assertTrue(self.splitter.job.closed)
        return self.splitter.state(self.splitter.job.value['id'])

    def roundtrip(self, extension, video='libx264', audio='aac', selected=False):
        file = self.fixture(extension, video, audio)
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        original = packets(file)
        registered = self.splitter.dispatch('register', {'path': str(file)})
        source = registered['source']
        self.assertIn('미리보기', source['preview_note'])
        self.splitter.dispatch('plan', {'source_id': registered['source_id'], 'points': [1.4, 3.4],
            'audio_selection': {'mode': 'selected', 'tracks': [2]} if selected else {'mode': 'all'}})
        result = self.finish()
        self.assertEqual(result['state'], 'ready', result['message'])
        self.splitter.dispatch('start', {'id': result['id'], 'folder': str(self.root)})
        result = self.finish()
        self.assertEqual(result['state'], 'complete', result['message'])
        actual = {i: [] for i in range(2 if selected else 3)}
        for index, record in result['outputs'].items():
            self.assertTrue(record['name'].endswith(extension))
            self.assertEqual(record['audio_tracks'], 1 if selected else 2)
            for stream, hashes in packets(self.splitter.media_file(run=result['id'], index=index)).items():
                actual[stream].extend(hashes)
        self.assertEqual(actual, {0: original[0], 1: original[2]} if selected else original)
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), digest)
        self.assertEqual(result['command'][result['command'].index('-c')+1], 'copy')
        # 서로 다른 오디오 트랙을 선택해도 미리듣기 파일에는 그 코덱 한 개만 복사한다.
        if source['streams'][2]['preview_supported']:
            info = self.splitter.dispatch('audio-preview', {'source_id': registered['source_id'], 'track': 2, 'at': 1})
            checked = split_media.probe(self.splitter.audio_preview.file(info['id']), threading.Event())
            self.assertEqual([s['codec_name'] for s in checked['streams']], [source['streams'][2]['codec_name']])
        else:
            with self.assertRaisesRegex(ValueError, '분할 저장'):
                self.splitter.dispatch('audio-preview', {'source_id': registered['source_id'], 'track': 2, 'at': 1})

    def test_mov_h264_pcm(self): self.roundtrip('.mov', audio='pcm_s16le')
    def test_mov_prores_pcm(self): self.roundtrip('.mov', video='prores_ks', audio='pcm_s24le')
    def test_mkv_h264_flac_selected(self): self.roundtrip('.mkv', audio='flac', selected=True)
    def test_webm_vp9_opus(self): self.roundtrip('.webm', video='libvpx-vp9', audio='libopus')
    def test_mp4_hevc(self): self.roundtrip('.mp4', video='libx265')
    def test_m4v_h264(self): self.roundtrip('.m4v')
    def test_mkv_ac3_keeps_audio_without_browser_preview(self): self.roundtrip('.mkv', audio='ac3')
    def test_webm_vp8_vorbis(self): self.roundtrip('.webm', video='libvpx', audio='vorbis')
    def test_av1_rejected_before_export_when_bundled_decoder_unavailable(self):
        file = self.fixture('.mkv', video='libsvtav1', audio='libopus')
        with self.assertRaisesRegex(ValueError, '검증 가능한'):
            split_media.inspect(str(file), threading.Event())
    def test_mov_mjpeg_alac(self): self.roundtrip('.mov', video='mjpeg', audio='alac')
    def test_mp4_mpeg4_mp3(self): self.roundtrip('.mp4', video='mpeg4', audio='libmp3lame')

    def test_forced_demuxer_and_external_reference_options(self):
        for extension in split_formats.VIDEO_FORMATS:
            args = split_formats.input_args('/tmp/local'+extension)
            self.assertEqual(args[args.index('-protocol_whitelist')+1], 'file')
            self.assertIn('-f', args)
            self.assertEqual('-enable_drefs' in args, extension in ('.mp4', '.m4v', '.mov'))
        with self.assertRaises(ValueError): split_formats.input_args('/tmp/list.m3u8')
        with self.assertRaises(ValueError): split_formats.output({'path': '/tmp/list.m3u8'})

    def test_open_gop_boundary_rejected_before_writing_outputs(self):
        file = self.fixture('.mp4', video='libx265', open_gop=True)
        source = split_media.inspect(str(file), threading.Event())
        with self.assertRaisesRegex(ValueError, '독립 재생'):
            split_media.boundaries(source, [1.4], threading.Event(), lambda **kw: None)

    def test_closed_boundary_can_follow_open_gop(self):
        packets = [{'pts_time': str(t), 'flags': 'K' if t in (2, 4) else ''}
                   for t in (2, 1.8, 2.2, 3, 4, 4.2, 5)]
        self.assertEqual(split_media.independent_keyframes(packets, 0, 6, 30), [4])

    def test_subtitles_rejected_without_touching_source(self):
        original = self.fixture('.mkv')
        subtitle = self.root/'captions.srt'
        subtitle.write_text('1\n00:00:00,000 --> 00:00:01,000\n시험 자막\n', encoding='utf-8')
        file = self.root/'자막.mkv'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(original), '-i', str(subtitle),
                        '-map', '0', '-map', '1', '-c', 'copy', str(file)], check=True)
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, '자막'):
            split_media.inspect(str(file), threading.Event())
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), digest)

    def test_chapters_rejected_without_touching_source(self):
        original = self.fixture('.mkv')
        metadata = self.root/'chapters.txt'
        metadata.write_text(';FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=6000\ntitle=시험\n', encoding='utf-8')
        file = self.root/'챕터.mkv'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(original), '-i', str(metadata),
                        '-map', '0', '-map_metadata', '1', '-c', 'copy', str(file)], check=True)
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, '챕터'):
            split_media.inspect(str(file), threading.Event())
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), digest)


if __name__ == '__main__': unittest.main()
