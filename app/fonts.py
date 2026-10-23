"""Bundled, licensed Korean typefaces keep card rendering consistent offline."""
import os
from pathlib import Path
from PIL import ImageFont

ROOT = Path(__file__).resolve().parent.parent / 'assets' / 'fonts'

def font(size, bold=False, headline=False):
    weight = 'ExtraBold' if headline else 'SemiBold' if bold else 'Regular'
    override = os.getenv('FONT_BOLD_PATH' if bold or headline else 'FONT_PATH', '')
    paths = [override, ROOT / f'Pretendard-{weight}.otf',
             'C:/Windows/Fonts/malgunbd.ttf' if bold or headline else 'C:/Windows/Fonts/malgun.ttf',
             '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc' if bold or headline else '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
    for path in paths:
        if path and Path(path).is_file():return ImageFont.truetype(str(path), size)
    raise ValueError('한글 글꼴을 찾지 못했습니다.')
