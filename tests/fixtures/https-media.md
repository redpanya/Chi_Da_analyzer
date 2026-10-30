# HTTPS 구간 수신 검사 자료

사용자 VOD와 무관하게 FFmpeg의 `testsrc2` 패턴과 440Hz 사인파로 직접 생성한
4초짜리 H.264/AAC MP4다. 외부 영상·음원·모델·개인정보를 포함하지 않는다.
일반 사용자 영상 제외 규칙의 예외는 아래 합성 검사 파일로 제한한다.

- 파일: `https-media.mp4`
- 크기: 37,978 bytes
- SHA-256: `064e914cf3ac2c20cc1df6761abc348cecdf7cf898c0a3e68373624e76eef653`
- 저장소 커밋 SHA에 고정된 GitHub raw HTTPS 주소에서 실제 구간을 받아 검사한다.
- FFmpeg의 인증서 검증을 끄거나 OS 인증서 저장소를 수정하지 않는다.
- 앱 패키지에는 넣지 않으며 검사 소스에서만 사용한다.

HLS 하위 연결 검사도 같은 합성 영상을 사용한다. `https-master.m3u8` →
`https-media.m3u8` → `https-segment.ts` 순서로 상대 주소를 따라 세 번 HTTPS를 연다.

| 파일 | SHA-256 |
|---|---|
| `https-master.m3u8` | `6bcce75c2bbe6bcf82c8f835f6f5dc4a1b792e5a0b68553e734ced27465d4c9e` |
| `https-media.m3u8` | `ed7a9e5fb71c28f0733657513c879292740d3c6f18c9ab6afc0690499954461e` |
| `https-segment.ts` | `f07419d4427ec4927855a6caefbf3a0628cdda746d31794b30abb5790db89010` |

`check_https.py`는 지정한 배포 FFmpeg·ffprobe의 절대 경로로 실제 프로세스를
실행하고 경로·실행 횟수·바이너리 해시를 기록한다. MP4 및 HLS의 1~3초 구간을
수신하고 전체 디코딩 검사까지 진행한다. 자체서명 인증서는 검사 임시 폴더에서
생성·폐기하며 OS 신뢰 저장소를 바꾸지 않는다. 해당 인증서를 쓰는 직접 HTTPS와
HLS 하위 playlist·segment·key 연결 네 가지가 모두 거부되어야 통과한다.

HLS 전송 형식 생성 명령:

```sh
ffmpeg -hide_banner -v error -i tests/fixtures/https-media.mp4 \
  -map 0:v:0 -map 0:a:0 -c copy -bsf:v h264_mp4toannexb \
  -map_metadata -1 -f mpegts -n tests/fixtures/https-segment.ts
```

생성 명령:

```sh
ffmpeg -hide_banner -v error \
  -f lavfi -i 'testsrc2=size=128x72:rate=15:duration=4' \
  -f lavfi -i 'sine=frequency=440:sample_rate=16000:duration=4' \
  -map 0:v:0 -map 1:a:0 -c:v libx264 -preset veryslow -crf 30 \
  -pix_fmt yuv420p -g 15 -c:a aac -b:a 24k -movflags +faststart \
  -map_metadata -1 -n tests/fixtures/https-media.mp4
```

이 합성 검사 자료는 프로젝트의 MIT 라이선스로 제공한다. 생성에 사용한 도구의
소스 코드가 출력 영상에 포함되는 것은 아니며, 도구 자체의 고지는 기존대로 유지한다.

## fMP4 HLS 확장자 호환 검사

같은 `https-media.mp4`의 영상·오디오를 재인코딩 없이 fMP4 초기화 파일과
2초 조각 두 개로 나눴다. `.m4v`·`.m4s` 조각은 바이트가 같고 파일명만 다르다.
쿼리 대조군은 초기화 파일·조각·재생목록에 공개 테스트 값 `?fixture=1`을 붙인다.
사용자의 VOD 주소나 접근 토큰은 포함하지 않는다.

| 파일 | 크기(bytes) | SHA-256 |
|---|---:|---|
| `https-fmp4-init.mp4` | 1376 | `a34730609e59f11847fd298b6a4255dda534318fd1b3928de3f8bd250be0d2af` |
| `https-fmp4-00.m4v` | 18163 | `073ae0a2a4c6c469d990e20ed5d721fd56de797fb70ad880a522503448b448a3` |
| `https-fmp4-00.m4s` | 18163 | `073ae0a2a4c6c469d990e20ed5d721fd56de797fb70ad880a522503448b448a3` |
| `https-fmp4-01.m4v` | 18625 | `b10e4b64e8d66058e43964d86e45f7957cd12659b0407f5274ec8d59c72dd590` |
| `https-fmp4-01.m4s` | 18625 | `b10e4b64e8d66058e43964d86e45f7957cd12659b0407f5274ec8d59c72dd590` |
| `https-fmp4-m4v.m3u8` | 222 | `76725e9617380b1e16e1f361b503a970a8c1cc245cddf02bf5ba155a435aeea3` |
| `https-fmp4-m4s.m3u8` | 222 | `fb8261d86d4c89b7a4381c46d4c83c3e17987f8062430ffdefda77dd38243a94` |
| `https-fmp4-query.m3u8` | 252 | `418246d03e14a0c3f093453aab4c960492db8d4c3ed925626e0b85c6d9f550be` |

`tests/fixtures` 폴더에서 생성:

```sh
ffmpeg -hide_banner -v error -i https-media.mp4 \
  -map 0:v:0 -map 0:a:0 -c copy -map_metadata -1 \
  -hls_time 2 -hls_segment_type fmp4 -hls_playlist_type vod \
  -hls_fmp4_init_filename https-fmp4-init.mp4 \
  -hls_segment_filename 'https-fmp4-%02d.m4v' -n https-fmp4-m4v.m3u8
```

`.m4s` 대조군은 `.m4v` 두 파일을 같은 바이트로 복사하고 재생목록의 조각 확장자만
바꾼다. 쿼리 대조군은 `.m4v` 재생목록에서 초기화 URI와 두 조각 URI 끝에
`?fixture=1`을 붙인다. 생성 도구 버전이 달라 바이트가 달라지면 체크섬도 함께 검토한다.

`check_https.py`는 직접 MP4, MPEG-TS HLS, fMP4 `.m4v`, fMP4 `.m4s`,
쿼리가 붙은 fMP4 HLS 총 5개에서 **1~3초 구간**을 실제 HTTPS로 수신한다.
각 결과는 2초 길이와 전체 디코딩을 확인한다. fMP4는 2초 경계를 넘어 두 조각을 읽는다.

`check_hls_compat.py`는 검사 임시 폴더에서 같은 자료로 다음 거부 대조군을 만든다.

- AAC 내용을 `.m4v`로 명명: MP4로 오인하지 않고 형식 불일치로 거부.
- MPEG-TS 내용을 `.m4v`로 명명: 형식 불일치로 거부.
- fMP4 내용을 `.png`로 명명: 허용 세그먼트 확장자 목록에서 거부.

거부 대조군은 로컬 파일로 검사한다. `extension_picky=0`, `allowed_*=ALL`을
사용하지 않으며, 기존 자체서명 TLS 거부 네 가지도 그대로 실행한다.
