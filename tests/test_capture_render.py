import json
import pytest
from PIL import Image, ImageDraw
from app import render


@pytest.mark.parametrize('ratio', ['4:5', '1:1', '9:16'])
@pytest.mark.parametrize('version', [2, 3, 4])
def test_capture_keeps_all_four_source_edges(tmp_path, monkeypatch, ratio, version):
    monkeypatch.setattr(render, 'MEDIA', tmp_path)
    monkeypatch.setattr(render, 'ASSETS', tmp_path)
    source = Image.new('RGB', (960, 540), 'white')
    d = ImageDraw.Draw(source)
    for color, box in [('red', (0,0,95,53)), ('green', (864,0,959,53)),
                       ('blue', (0,486,95,539)), ('yellow', (864,486,959,539))]:
        d.rectangle(box, fill=color)
    source.save(tmp_path/'sample.jpg', quality=100, subsampling=0)
    (tmp_path/'sample.json').write_text(json.dumps({'frame_label':'JTBC 영상 00:08'}), encoding='utf-8')
    p = dict(id='preview', ratio=ratio, category='이슈', design_version=version,
             visual_style='video_capture', image_mode='video', source_name='영상 출처',
             slides=[dict(title='금메달 세리머니,\n왜 사과까지 했나?',
                          body='영상 속 행동과 당사자의 해명을 함께 확인하세요.', asset_id='sample')])
    render.render(p)
    with Image.open(tmp_path/'preview'/'01.png') as result:
        w,h=render.SIZES[ratio]
        assert result.size == (w,h)
        box_h=min(int((w-120)*9/16), int(h*.40))
        scaled_w=round(box_h*16/9)
        left=60+(w-120-scaled_w)//2
        top=int(h*.30)
        samples=[result.getpixel((left+int(scaled_w*x), top+int(box_h*y)))
                 for x,y in [(.05,.05),(.95,.05),(.05,.95),(.95,.95)]]
        r,g,b,y=samples
        assert r[0]>220 and r[1]<40 and r[2]<40
        assert g[1]>100 and g[0]<40 and g[2]<40
        assert b[2]>220 and b[0]<40 and b[1]<40
        assert y[0]>220 and y[1]>220 and y[2]<40
