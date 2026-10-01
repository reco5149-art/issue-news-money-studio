import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance
from .storage import MEDIA, ASSETS

SIZES = {'4:5': (1080,1350), '1:1': (1080,1080), '9:16': (1080,1920)}
COLORS = {'뉴스':'#afd96b','이슈':'#ff9569','연예':'#dda6ee','경제':'#83baff','AI':'#c7ee81'}

def font(size, bold=False):
    paths = [os.getenv('FONT_PATH',''), 'C:/Windows/Fonts/malgunbd.ttf' if bold else 'C:/Windows/Fonts/malgun.ttf',
             '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc' if bold else '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
    for p in paths:
        if p and Path(p).is_file(): return ImageFont.truetype(p,size)
    raise ValueError('한글 글꼴을 찾지 못했습니다. .env의 FONT_PATH를 지정하세요.')

def wrap(text, f, width):
    rows=[]
    for para in text.split('\n'):
        line=''
        for ch in para:
            if f.getlength(line+ch)>width and line:
                rows.append(line.rstrip()); line=''
            line+=ch
        rows.append(line.rstrip())
    return rows

def fit(draw, text, xy, width, height, size, color, bold=False):
    for s in range(size, 17, -2):
        f=font(s,bold); lines=wrap(text,f,width); step=int(s*1.42)
        if len(lines)*step<=height: break
    if len(lines)*step>height: raise ValueError('카드 문장이 너무 깁니다. 내용을 줄여 주세요.')
    for i,line in enumerate(lines): draw.text((xy[0],xy[1]+i*step),line,font=f,fill=color)

def render(post):
    out=MEDIA/post['id']; out.mkdir(exist_ok=True)
    w,h=SIZES[post['ratio']]; accent=COLORS[post['category']]
    paths=[]
    for i,slide in enumerate(post['slides']):
        asset=ASSETS/((slide.get('asset_id') or post.get('asset_id',''))+'.jpg')
        im=Image.new('RGB',(w,h),'#141d1b'); d=ImageDraw.Draw(im)
        if asset.is_file():
            photo=ImageOps.fit(Image.open(asset).convert('RGB'),(w,int(h*.54)))
            photo=ImageEnhance.Color(photo).enhance(.75)
            im.paste(photo,(0,0))
            overlay=Image.new('RGBA',(w,h),(0,0,0,0)); od=ImageDraw.Draw(overlay)
            for y in range(int(h*.22),int(h*.58)):
                alpha=min(255,int(255*(y-h*.22)/(h*.32)))
                od.line((0,y,w,y),fill=(20,29,27,alpha))
            im=Image.alpha_composite(im.convert('RGBA'),overlay).convert('RGB');d=ImageDraw.Draw(im)
        else:
            d.line((66,210,w-66,210),fill='#46584c',width=2)
            d.text((60,int(h*.25)),f'{i+1:02}',font=font(230,True),fill='#23382e')
        d.rounded_rectangle((64,58,204,111),radius=8,fill=accent)
        d.text((86,63),post['category'],font=font(28,True),fill='#142017')
        d.text((w-405,66),'ISSUE / NEWS / MONEY',font=font(24,True),fill='#ffffff')
        y=int(h*.44) if asset.is_file() else int(h*.39)
        title_h=int(h*.25)
        fit(d,slide['title'],(64,y),w-128,title_h,84,accent,True)
        fit(d,slide['body'],(66,y+title_h+12),w-132,h-(y+title_h+12)-150,38,'#f4f5ef')
        d.line((64,h-120,w-64,h-120),fill='#46584c',width=2)
        credit=post['source_name'][:50]
        d.text((64,h-97),credit,font=font(22),fill='#b4c1b7')
        d.text((64,h-62),'@issue_news_money',font=font(22,True),fill='#dfe6db')
        d.text((w-150,h-66),f'{i+1:02} / {len(post["slides"]):02}',font=font(24),fill=accent)
        if slide.get('image_credit')=='AI 생성 이미지' or (post['image_mode']=='ai' and not slide.get('image_credit')):
            d.text((64,136),'AI 생성 이미지',font=font(23),fill='#ffffff')
        im.save(out/f'{i+1:02}.png'); im.save(out/f'{i+1:02}.jpg',quality=93)
        paths.append(f'/media/{post["id"]}/{i+1:02}.png')
    return paths
