import asyncio
import io
from PIL import Image
from app import web_art


def test_selects_distinct_photo_with_provenance(monkeypatch):
    buf=io.BytesIO();Image.new('RGB',(600,600),'white').save(buf,format='JPEG')
    item=dict(url='https://example.com/image',title='School',credit='Author',license='CC0 1.0',license_url='https://example.com/license',page='https://example.com/page')
    async def structured(*args):
        return {'queries':['school building','school building']} if len(args[1])==1 else {'index':0}
    async def search(*args,**kwargs):return [item]
    async def fetch(*args):return buf.getvalue(),'image/jpeg',''
    monkeypatch.setattr(web_art,'structured',structured)
    monkeypatch.setattr(web_art.p,'web_images',search)
    monkeypatch.setattr(web_art.p,'fetch_public',fetch)
    slides=[dict(title='School',body='building') for _ in range(2)]
    credits,notes=asyncio.run(web_art.attach(slides,lambda data,credit:{'asset_id':'a'*32}))
    assert len(credits)==1 and 'https://example.com/page' in credits[0]
    assert slides[0]['web_illustration'] is True
    assert 'asset_id' not in slides[1] and len(notes)==1


def test_search_failure_falls_back_without_unrelated_photo(monkeypatch):
    async def structured(*args):return {'queries':['school']}
    async def search(*args,**kwargs):raise web_art.p.ProviderError('search unavailable')
    monkeypatch.setattr(web_art,'structured',structured)
    monkeypatch.setattr(web_art.p,'web_images',search)
    slides=[dict(title='School',body='building')]
    credits,notes=asyncio.run(web_art.attach(slides,lambda *args:None))
    assert not credits and '실패' in notes[0] and 'asset_id' not in slides[0]
