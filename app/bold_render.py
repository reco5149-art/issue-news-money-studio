from .copy_policy import public_source_label
"""High-contrast feed cards. Video overlays are cropped before rendering."""
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

BACKGROUND = '#080b0a'
LIME = '#c8ff16'
WHITE = '#ffffff'
YELLOW = '#ffe45e'
MUTED = '#bdc6bf'
HEADLINE_COLOR_POLICY = 'white-top-yellow-bottom-v1'


def render_bold(post, media, assets, sizes, base_font):
    def face(size, bold=True):
        from .fonts import font
        return font(size, bold=bold, headline=bold)

    def lines_for(text, font, width):
        # Keep Korean word units together, avoiding an isolated final syllable.
        rows = []
        for paragraph in text.split('\n'):
            line = ''
            for word in paragraph.split():
                candidate = (line + ' ' + word).strip()
                if font.getlength(candidate) <= width:
                    line = candidate
                    continue
                if line:
                    rows.append(line)
                line = ''
                for character in word:
                    if line and font.getlength(line + character) > width:
                        rows.append(line)
                        line = ''
                    line += character
            rows.append(line)
        return rows

    def block(draw, text, top, height, size, color, highlight_first=False, headline=False):
        from .fonts import font as card_font
        for actual in range(size, 17, -2):
            font = card_font(actual, bold=True, headline=headline)
            rows = lines_for(text, font, w-120)
            step = int(actual * 1.35)
            if len(rows) * step <= height:
                break
        else:
            raise ValueError('카드 문장이 너무 깁니다. 내용을 줄여 주세요.')
        for row, line in enumerate(rows):
            fill = (WHITE if row == 0 else YELLOW) if headline else (YELLOW if highlight_first and row == 0 else color)
            draw.text((60, top + row*step), line, font=font, fill=fill)

    def credit_line(draw, text, top, width):
        font = face(22, False)
        text = str(text).replace('\n', ' ')
        if font.getlength(text) > width:
            while text and font.getlength(text + '…') > width:
                text = text[:-1]
            text += '…'
        draw.text((60, top), text, font=font, fill=MUTED)

    w, h = sizes[post['ratio']]
    out = media / post['id']
    out.mkdir(exist_ok=True)
    paths = []
    total = len(post['slides'])
    for index, slide in enumerate(post['slides']):
        im = Image.new('RGB', (w, h), BACKGROUND)
        draw = ImageDraw.Draw(im)
        draw.rectangle((0, 0, w, 8), fill=LIME)
        draw.text((60, 36), 'ISSUE / NEWS / MONEY', font=face(25), fill=WHITE)
        draw.text((w-178, 36), f'{index+1:02} / {total:02}', font=face(25), fill=LIME)
        labels = post.get('section_labels') or []
        label = labels[index] if index < len(labels) else post['category'] + (' / 핵심 이슈' if index == 0 else ' / 맥락과 확인')
        draw.text((60, 103), label, font=face(26), fill=WHITE)
        growth = post.get('design_version') == 4
        compact = post.get('copy_style') == 'compact-v1'
        photo_top = int(h * (.29 if compact else .30))
        photo_height = (min(int((w-120)*.70), int(h*(.40 if post['ratio']=='1:1' else .46)))
                        if compact else min(int((w-120)*9/16), int(h*.40)))
        block(draw, slide['title'], 154, photo_top-172, 88, WHITE, headline=True)
        asset_id = slide.get('asset_id') or post.get('asset_id') or ''
        asset = assets / (asset_id + '.jpg')
        if not growth:
            draw.rectangle((60, photo_top, w-60, photo_top+photo_height), fill='#171d19')
        if asset.is_file():
            with Image.open(asset) as original:
                photo = ImageOps.contain(original.convert('RGB'), (w if growth else w-120, photo_height))
            if growth:
                photo_height = photo.height
            im.paste(photo, ((w-photo.width)//2, photo_top+(photo_height-photo.height)//2))
            draw = ImageDraw.Draw(im)
        elif post.get('image_mode') == 'video':
            raise ValueError('영상 캡처 원본이 없습니다. 장면을 다시 선택하세요.')
        else:
            draw.text((92, photo_top+30), f'{index+1:02}', font=face(132), fill=LIME)
        meta_file = assets / (asset_id + '.json')
        meta = json.loads(meta_file.read_text(encoding='utf-8')) if meta_file.is_file() else {}
        credit = slide.get('image_credit') or post.get('image_credit') or meta.get('credit') or ''
        if post.get('image_mode') == 'ai' or 'AI 생성' in credit:
            credit = 'AI 생성 · 설명용 이미지'
        elif post.get('image_mode') == 'video' or post.get('visual_style') == 'video_capture':
            credit = meta.get('frame_label') or ''
        elif slide.get('web_illustration'):
            credit = '이해를 돕는 자료사진'
        credit_line(draw, credit, photo_top+photo_height+13, w-120)
        body_top = photo_top+photo_height+(52 if compact else 67)
        block(draw, slide['body'], body_top, h-139-body_top, 46, WHITE, highlight_first=True)
        draw.line((60, h-110, w-60, h-110), fill='#485047', width=2)
        credit_line(draw, public_source_label(post['source_name']), h-94, w-120)
        draw.text((60, h-56), '@issue_news_money', font=face(24), fill=WHITE)
        cue = '다음 장 →' if index < total-1 else ('핵심 정리' if growth else '저장 + 공유')
        cue_width = int(face(24).getlength(cue))
        draw.rounded_rectangle((w-86-cue_width, h-63, w-55, h-18), radius=8, fill=LIME)
        draw.text((w-70-cue_width, h-58), cue, font=face(24), fill=BACKGROUND)
        im.save(out / f'{index+1:02}.png')
        im.save(out / f'{index+1:02}.jpg', quality=95)
        paths.append(f'/media/{post["id"]}/{index+1:02}.png')
    return paths
