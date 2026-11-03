"""앱이 사용할 수 있는 치지직 재생 형식을 yt-dlp로 읽는다."""
from yt_dlp.extractor.chzzk import CHZZKVideoIE


def _audio_only(group):
    def audio(track):
        mime = track.get('mimeType') or group.get('mimeType') or ''
        return mime.startswith('audio/') if mime else (track.get('contentType') or group.get('contentType')) == 'audio'

    tracks = group.findall('{*}Representation')
    return bool(tracks) and all(audio(track) for track in tracks)


class ArchiveVodIE(CHZZKVideoIE):
    def _parse_mpd_periods(self, mpd_doc, *args, **kwargs):
        for period in mpd_doc.findall('{*}Period'):
            for group in period.findall('{*}AdaptationSet'):
                # 앱은 영상·음성이 함께 든 파일을 사용한다. 별도 음원의 같은 파일 내
                # 바이트 범위는 yt-dlp가 별도 조각 URL로 오인하므로 그 음원만 제외한다.
                if _audio_only(group) and any(
                    init.get('range') and not init.get('sourceURL')
                    for init in group.findall('.//{*}SegmentList/{*}Initialization')
                ):
                    period.remove(group)
        return super()._parse_mpd_periods(mpd_doc, *args, **kwargs)


def extract_vod(downloader, vod):
    extractor = ArchiveVodIE()
    downloader.add_info_extractor(extractor)
    return downloader.extract_info(f'https://chzzk.naver.com/video/{vod}', ie_key=extractor.ie_key(), download=False)
