import io
import pytest
from PIL import Image
from app.photo_finish import finish
from app.fonts import font

@pytest.mark.parametrize('size,expected', [((640,360),(1280,720)), ((1280,720),(2560,1440)), ((1920,1080),(3840,2160)), ((4000,2000),(3840,1920))])
def test_photo_resizing_preserves_geometry_without_claiming_new_details(size,expected):
    out=io.BytesIO();Image.new('RGB',size,(100,110,120)).save(out,format='JPEG')
    data,meta=finish(out.getvalue())
    with Image.open(io.BytesIO(data)) as im:
        assert im.size==expected
        assert max(abs(a-b) for a,b in zip(im.getpixel((0,0)),(100,110,120)))<10
    assert not meta['generative_reconstruction'] and meta['source_size']==list(size)
    assert meta['output_size']==list(expected)

def test_bundled_headline_and_body_have_distinct_weights(monkeypatch):
    monkeypatch.delenv('FONT_BOLD_PATH',raising=False);monkeypatch.delenv('FONT_PATH',raising=False)
    assert font(64,headline=True).getname()==('Pretendard','ExtraBold')
    assert font(40,bold=True).getname()==('Pretendard','SemiBold')
