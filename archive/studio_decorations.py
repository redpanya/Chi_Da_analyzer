"""브라우저 미리보기와 영상 저장이 공유하는 자막·PNG 합성 준비."""
import base64
import io
from . import font_languages, caption_fonts, caption_styles, clip_contract, studio_images


def catalog(refresh=False):
    return dict(fonts=caption_fonts.catalog(refresh), languages=font_languages.LANGUAGES,
                templates=[dict(id='basic',label='기본 자막'),dict(id='box',label='박스 자막')])


def prepare(project, options, selection=None):
    if options['caption'] or (options['sidecar'] and selection):
        caption_styles.font(options, 22)
    return studio_images.load(project, options.get('image'))


def preview(project, data):
    size = data.get('size')
    if not isinstance(size, list) or len(size) != 2 or any(type(v) is not int or not 1 <= v <= 4096 for v in size) or size[0]*size[1] > 4_200_000:
        raise ValueError('미리보기 크기를 확인하세요')
    text = data.get('text', '')
    if not isinstance(text, str) or len(text) > 20000: raise ValueError('미리보기 자막 길이를 확인하세요')
    supplied = data.get('options', {})
    if not isinstance(supplied, dict): raise ValueError('자막·이미지 설정을 확인하세요')
    # 자막 레이어에는 화면 자르기·구간·저장 방식이 영향을 주지 않는다.
    keys = ('caption', 'style', 'caption_design', 'font', 'caption_language',
            'font_size', 'position', 'caption_x', 'caption_y', 'image')
    options = clip_contract.validate({'clips':[], 'options':{k:supplied[k] for k in keys if k in supplied}},
                                    dict(width=1920,height=1080,origin=0,duration=1), draft=True)['options']
    image = studio_images.layer(tuple(size), studio_images.load(project, options.get('image')), options.get('image'))
    if options['caption'] and text: caption_styles.paint(image, text, tuple(size), options)
    out = io.BytesIO(); image.save(out, format='PNG')
    return {'png':base64.b64encode(out.getvalue()).decode('ascii')}
