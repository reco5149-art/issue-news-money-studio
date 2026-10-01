import pytest
from PIL import Image
from app import render


@pytest.mark.parametrize('ratio', ['4:5', '1:1', '9:16'])
@pytest.mark.parametrize('photo', [True, False])
def test_editorial_maximum_content_fits(tmp_path, monkeypatch, ratio, photo):
    monkeypatch.setattr(render, 'MEDIA', tmp_path)
    monkeypatch.setattr(render, 'ASSETS', tmp_path)
    if photo:
        Image.new('RGB', (800, 600), '#f08050').save(tmp_path/'sample.jpg')
    p = dict(id='preview', ratio=ratio, category='AI', design_version=2,
             image_mode='ai' if photo else 'design', source_name='긴 출처 이름' * 20,
             slides=[dict(title='한글 제목 ' * 10, body='사실과 출처를 확인하는 자세한 설명입니다. ' * 9,
                          asset_id='sample' if photo else '')] * 3)
    paths = render.render(p)
    assert len(paths) == 3
    for index in range(1, 4):
        with Image.open(tmp_path/'preview'/f'{index:02}.jpg') as image:
            assert image.size == render.SIZES[ratio]
