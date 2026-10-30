"""배포 FFmpeg의 디코딩·PNG 색 변환·합성을 같은 가상 입력으로 검사한다."""
import json
from pathlib import Path
import subprocess
import tempfile
from PIL import Image


def run(*args):
    return subprocess.check_output(['ffmpeg', '-v', 'error', '-y', *map(str, args)])


def sample(path, pix_fmt, flags=()):
    raw = run(*flags, '-i', path, '-frames:v', 1, '-pix_fmt', pix_fmt, '-f', 'rawvideo', '-')
    if pix_fmt == 'yuv420p':
        at = 180*640+320; chroma = 90*320+160; plane = 640*360
        return [raw[at], raw[plane+chroma], raw[plane+plane//4+chroma]]
    size = {'rgb24': 3, 'rgba': 4}[pix_fmt]; at = (180*640+320)*size
    return list(raw[at:at+size])


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); source = root/'source.mp4'; layer = root/'layer.png'
        run('-f', 'lavfi', '-i', 'color=c=navy:s=640x360:r=30:d=1', '-c:v', 'libx264', source)
        Image.new('RGBA', (640, 360), (239, 39, 69, 64)).save(layer)
        print('FFmpeg 색 변환 검사:', run('-version').decode(errors='replace').splitlines()[0], flush=True)
        results = {}
        for mode, flags in [('default', ()), ('scalar', ('-cpuflags', '0'))]:
            output = root/(mode+'.mp4')
            run(*flags, '-i', source, '-i', layer, '-filter_complex_threads', 1,
                '-filter_complex', '[1:v]format=yuva420p[p];[0:v][p]overlay=format=yuv420[v]',
                '-map', '[v]', '-t', 1, '-c:v', 'libx264', output)
            results[mode] = {'source_yuv': sample(source, 'yuv420p', flags),
                             'source_rgb': sample(source, 'rgb24', flags),
                             'png_rgba': sample(layer, 'rgba', flags),
                             'output_yuv': sample(output, 'yuv420p', flags),
                             'output_rgb': sample(output, 'rgb24', flags)}
        print(json.dumps(results, ensure_ascii=False), flush=True)
        for mode in results:
            assert all(abs(actual-expected) <= 5 for actual, expected in
                       zip(results[mode]['output_rgb'], (60, 10, 112))), '배포 FFmpeg의 PNG 합성 색상이 예상과 다릅니다'
        assert all(abs(a-b) <= 3 for a, b in zip(results['default']['output_rgb'],
                                                results['scalar']['output_rgb'])), 'CPU 최적화에 따라 PNG 합성 색상이 달라집니다'


if __name__ == '__main__':
    main()
