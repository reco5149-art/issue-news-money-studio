from .copy_policy import public_source_label
"""Light editorial cards that retain the complete source video frame."""
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps, ImageFont


def render_capture(post, media, assets, sizes, font, fit):
    base_font = font

    def font(size, bold=False):
        from .fonts import font as card_font
        return card_font(size, bold=bold, headline=bold)

    def text_block(draw, text, xy, width, height, size, color, bold=False):
        from .render import wrap
        for current_size in range(size, 17, -2):
            face = font(current_size, bold)
            lines = wrap(text, face, width)
            step = int(current_size * 1.42)
            if len(lines)*step <= height:
                break
        if len(lines)*step > height:
            raise ValueError('카드 문장이 너무 깁니다. 내용을 줄여 주세요.')
        for line_no, line in enumerate(lines):
            draw.text((xy[0], xy[1]+line_no*step), line, font=face, fill=color)

    w, h = sizes[post['ratio']]
    out = media / post['id']
    out.mkdir(exist_ok=True)
    paths = []
    for i, slide in enumerate(post['slides']):
        im = Image.new('RGB', (w, h), '#f6f5f1')
        d = ImageDraw.Draw(im)
        ink, muted, yellow = '#141414', '#62625f', '#ffdf36'
        d.text((60, 35), 'ISSUE / NEWS / MONEY', font=font(25, True), fill=ink)
        d.text((w-180, 35), f'{i+1:02} / {len(post["slides"]):02}', font=font(25), fill=muted)
        d.line((60, 92, w-60, 92), fill=ink, width=2)
        labels = post.get('section_labels') or ['논란과 해명', '영상 속 맥락', '당사자 설명']
        tag = labels[i] if i < len(labels) else '함께 확인할 내용'
        d.rectangle((60, 122, 85+int(font(26, True).getlength(tag)), 169), fill=yellow)
        d.text((73, 128), tag, font=font(26, True), fill=ink)
        photo_y = int(h * .30)
        photo_h = min(int((w-120)*9/16), int(h*.40))
        text_block(d, slide['title'], (58, 195), w-116, photo_y-214, 76, ink, True)
        asset_id = slide.get('asset_id') or post.get('asset_id') or ''
        asset = assets / (asset_id + '.jpg')
        if not asset.is_file():
            raise ValueError('영상 캡처 원본이 없습니다. 장면을 다시 선택하세요.')
        with Image.open(asset) as source:
            # Contain, never crop: faces, captions and source marks stay intact.
            photo = ImageOps.contain(source.convert('RGB'), (w-120, photo_h))
        d.rectangle((60, photo_y, w-60, photo_y+photo_h), fill='#111111')
        im.paste(photo, (60+(w-120-photo.width)//2, photo_y+(photo_h-photo.height)//2))
        d = ImageDraw.Draw(im)
        meta_path = assets / (asset_id + '.json')
        meta = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.exists() else {}
        credit = str(meta.get('frame_label') or '')
        fit(d, credit, (60, photo_y+photo_h+16), w-120, 48, 22, muted)
        body_y = photo_y+photo_h+85
        fit(d, slide['body'], (60, body_y), w-120, h-145-body_y, 36, ink)
        d.line((60, h-112, w-60, h-112), fill='#b9b9b2', width=1)
        fit(d, public_source_label(post['source_name']), (60, h-98), w-280, 32, 20, muted)
        d.text((60, h-59), '@issue_news_money', font=font(24, True), fill=ink)
        cue = '다음 장 →' if i < len(post['slides'])-1 else '저장 + 공유'
        cue_w = int(font(23, True).getlength(cue))
        d.rectangle((w-80-cue_w, h-62, w-55, h-20), fill=yellow)
        d.text((w-67-cue_w, h-58), cue, font=font(23, True), fill=ink)
        im.save(out/f'{i+1:02}.png')
        im.save(out/f'{i+1:02}.jpg', quality=93)
        paths.append(f'/media/{post["id"]}/{i+1:02}.png')
    return paths
