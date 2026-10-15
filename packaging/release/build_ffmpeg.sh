#!/usr/bin/env bash
# FFmpeg와 x264의 대응 소스는 실행 파일과 함께 Release 자산으로 제공한다.
set -euo pipefail
cd "$(dirname "$0")/../.."
root="$PWD"
x264_source=("$root"/build/native-src/x264/*)
ffmpeg_source=("$root"/build/native-src/ffmpeg/*)
prefix="$root/build/ffmpeg-prefix"
mkdir -p "$prefix" "$root/build/native/ffmpeg"
export PKG_CONFIG_PATH="$prefix/lib/pkgconfig"
extra=()
if [[ "${OSTYPE:-}" == msys* ]]; then
  extra=(--extra-ldflags=-static)
else
  export MACOSX_DEPLOYMENT_TARGET=14.0
fi
cd "${x264_source[0]}"
./configure --prefix="$prefix" --enable-static --disable-cli --disable-opencl --disable-asm
make -j3
make install
cd "${ffmpeg_source[0]}"
./configure --prefix="$prefix" --disable-autodetect --disable-shared --enable-static --disable-doc --disable-debug --disable-ffplay --disable-x86asm --enable-gpl --enable-libx264 "${extra[@]}"
make -j3 ffmpeg ffprobe
suffix=""
[[ "${OSTYPE:-}" != msys* ]] || suffix=.exe
cp "ffmpeg$suffix" "ffprobe$suffix" "$root/build/native/ffmpeg/"
cp COPYING.GPLv2 LICENSE.md "$root/build/native/ffmpeg/"
cp "${x264_source[0]}/COPYING" "$root/build/native/ffmpeg/x264-COPYING"
cp ffbuild/config.log "$root/build/native/ffmpeg/build-config.log"
