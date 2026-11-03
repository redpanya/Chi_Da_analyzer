"""다른 트랙의 같은 파일 내 바이트 범위가 MP4 화질 조회를 막지 않아야 한다."""
import unittest
from xml.etree import ElementTree

from yt_dlp import YoutubeDL
from yt_dlp.extractor.chzzk import CHZZKVideoIE

from archive.source import ydl_options
from archive.vod_extractor import ArchiveVodIE


MPD = '''<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" mediaPresentationDuration="PT10S"><Period>
<AdaptationSet mimeType="video/mp4"><Representation id="mux" codecs="avc1.4d4020,mp4a.40.2" height="720">
<BaseURL>https://example.invalid/full.mp4</BaseURL></Representation></AdaptationSet>
<AdaptationSet mimeType="audio/mp4"><Representation id="ranges" codecs="mp4a.40.2">
<BaseURL>https://example.invalid/audio.m4a</BaseURL><SegmentList><Initialization range="0-49"/>
<SegmentURL mediaRange="50-999"/></SegmentList></Representation></AdaptationSet>
<AdaptationSet><Representation id="standard" mimeType="audio/mp4" codecs="mp4a.40.2">
<BaseURL>https://example.invalid/other.m4a</BaseURL></Representation></AdaptationSet>
</Period></MPD>'''


class VodExtractorTests(unittest.TestCase):
    def formats(self, extractor, xml):
        with YoutubeDL(ydl_options()) as downloader:
            rows, _ = extractor(downloader)._parse_mpd_formats_and_subtitles(ElementTree.fromstring(xml))
        return {f['format_id']: f for f in rows}

    def test_range_only_audio_does_not_hide_muxed_video(self):
        with self.assertRaisesRegex(KeyError, 'sourceURL'):
            self.formats(CHZZKVideoIE, MPD)
        rows = self.formats(ArchiveVodIE, MPD)
        self.assertEqual(set(rows), {'mux', 'standard'})
        self.assertEqual(rows['mux']['url'], 'https://example.invalid/full.mp4')
        self.assertEqual((rows['mux']['height'], rows['mux']['acodec']), (720, 'mp4a.40.2'))

    def test_standard_manifest_and_protection_unchanged(self):
        xml = MPD.replace('range="0-49"', 'sourceURL="init.m4a"').replace('mediaRange="50-999"', 'media="part.m4a"')
        xml = xml.replace('<AdaptationSet mimeType="video/mp4">', '<AdaptationSet mimeType="video/mp4"><ContentProtection/>')
        rows = self.formats(ArchiveVodIE, xml)
        self.assertEqual(rows, self.formats(CHZZKVideoIE, xml))
        self.assertTrue(rows['mux']['has_drm'])
