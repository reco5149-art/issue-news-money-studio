import asyncio
import io
import json

import pytest
from PIL import Image
from app import frame_cleanup as cleanup, providers


def jpeg():
    b=io.BytesIO();Image.new('RGB',(1280,720),'green').save(b,format='JPEG');return b.getvalue()


def test_crop_bounds_and_resolution():
    d=cleanup.FrameDecision(frame=1,usable=True,left=250,top=0,right=750,bottom=800,reason='방송 그래픽 제외')
    image=Image.open(io.BytesIO(cleanup.crop_frame(jpeg(),d)))
    assert image.size==(640,576)
    d.right=300
    with pytest.raises(ValueError):cleanup.crop_frame(jpeg(),d)


def test_rejected_candidate_retried_and_all_rejected_returns_none(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    verdicts=[False,True]
    async def fake(*args,**kwargs):
        return {'output':[{'content':[{'type':'output_text','text':json.dumps({'clean':verdicts.pop(0),'reason':'checked'})}]}]}
    monkeypatch.setattr(providers,'api',fake)
    result=asyncio.run(cleanup.inspect_frame(jpeg()))
    assert Image.open(io.BytesIO(result)).size==(768,561)
    verdicts.extend([False]*len(cleanup.CROPS))
    assert asyncio.run(cleanup.inspect_frame(jpeg())) is None


def test_promo_excluded_and_shortage_blocks(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    calls=[]
    async def fake(raw):
        calls.append(raw)
        return None if raw==b'promo' else raw
    monkeypatch.setattr(cleanup,'inspect_frame',fake)
    frames=[(10,b'promo'),(20,jpeg())]
    out=asyncio.run(cleanup.clean_frames(frames,1))
    assert len(out)==1 and out[0][0]==20
    with pytest.raises(providers.ProviderError):asyncio.run(cleanup.clean_frames(frames,2))


def test_invalid_inspection_fails_closed(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    async def fake(*args,**kwargs):return {'output':[]}
    monkeypatch.setattr(providers,'api',fake)
    with pytest.raises(providers.ProviderError):asyncio.run(cleanup.inspect_frame(jpeg()))
