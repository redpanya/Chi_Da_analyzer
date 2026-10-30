# HTTPS 구간 수신 검사 자료

사용자 VOD와 무관하게 FFmpeg의 `testsrc2` 패턴과 440Hz 사인파로 직접 생성한
4초짜리 H.264/AAC MP4다. 외부 영상·음원·모델·개인정보를 포함하지 않는다.
일반 사용자 영상 제외 규칙의 예외는 이 파일 하나로 제한한다.

- 파일: `https-media.mp4`
- 크기: 37,978 bytes
- SHA-256: `064e914cf3ac2c20cc1df6761abc348cecdf7cf898c0a3e68373624e76eef653`
- 저장소 커밋 SHA에 고정된 GitHub raw HTTPS 주소에서 실제 구간을 받아 검사한다.
- FFmpeg의 인증서 검증을 끄거나 OS 인증서 저장소를 수정하지 않는다.
- 앱 패키지에는 넣지 않으며 검사 소스에서만 사용한다.

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
