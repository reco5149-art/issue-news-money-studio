"""Versioned editorial layout; legacy drafts retain their original pixels."""
from PIL import Image, ImageDraw, ImageOps


def render_editorial(post, media, assets, sizes, colors, font, fit):
    w, h = sizes[post['ratio']]
    out = media / post['id']
    out.mkdir(exist_ok=True)
    accent = colors[post['category']]
    paths = []
    total = len(post['slides'])
    for i, slide in enumerate(post['slides']):
        cover = i == 0
        dark = cover or (total > 2 and i == total - 1)
        bg, ink, muted = ('#101719', '#f7f5ef', '#aab5b6') if dark else ('#f4f1e9', '#172022', '#5d6b6c')
        im = Image.new('RGB', (w, h), bg)
        d = ImageDraw.Draw(im)
        d.text((64, 36), 'ISSUE MONEY', font=font(25, True), fill=ink)
        d.text((w-205, 36), f'{i+1:02} / {total:02}', font=font(25), fill=muted)
        d.line((64, 89, w-64, 89), fill=muted, width=1)
        asset = assets / ((slide.get('asset_id') or post.get('asset_id') or '') + '.jpg')
        if asset.is_file():
            # Keep full contrast and color, with no text over the subject.
            top, bottom = 120, int(h * (.52 if cover else .43))
            with Image.open(asset) as original:
                photo = ImageOps.fit(original.convert('RGB'), (w-96, bottom-top), centering=(.5, .42))
            im.paste(photo, (48, top))
            d = ImageDraw.Draw(im)
            credit = slide.get('image_credit', '') or post.get('image_credit', '')
            if post.get('image_mode') == 'ai' or 'AI 생성' in credit:
                d.rectangle((64, top+16, 357, top+56), fill='#101719')
                d.text((77, top+19), 'AI 생성 · 설명용 이미지', font=font(21), fill='#ffffff')
            elif slide.get('web_illustration'):
                d.rectangle((64, top+16, 252, top+56), fill='#101719')
                d.text((77, top+19), '설명용 자료사진', font=font(21), fill='#ffffff')
            y = bottom + 28
        else:
            y = int(h * .24)
            d.text((w-280, 112), f'{i+1:02}', font=font(132, True), fill='#253236' if dark else '#dcded6')
        tag = post['category'] + ('  /  THE ISSUE' if cover else '  /  THE DETAIL')
        d.text((64, y), tag, font=font(24, True), fill=accent if dark else '#42604d')
        y += 56
        available = h - 150 - y
        title_h = int(available * .53)
        fit(d, slide['title'], (60, y), w-120, title_h, 82 if cover else 66, ink, True)
        rule_y = y + title_h + 6
        d.rectangle((64, rule_y, 142, rule_y+5), fill=accent if dark else '#42604d')
        body_y = rule_y + 24
        fit(d, slide['body'], (64, body_y), w-128, h-146-body_y, 36, muted)
        d.line((64, h-111, w-64, h-111), fill=muted, width=1)
        source = post['source_name'].replace('\n', ' ')
        while font(20).getlength(source) > w-280:
            source = source[:-2] + '…'
        d.text((64, h-96), source, font=font(20), fill=muted)
        d.text((64, h-60), '@issue_news_money', font=font(21, True), fill=ink)
        d.text((w-190, h-60), 'SWIPE  →' if i < total-1 else 'SAVE  +', font=font(22, True), fill=accent if dark else '#42604d')
        im.save(out / f'{i+1:02}.png')
        im.save(out / f'{i+1:02}.jpg', quality=93)
        paths.append(f'/media/{post["id"]}/{i+1:02}.png')
    return paths
