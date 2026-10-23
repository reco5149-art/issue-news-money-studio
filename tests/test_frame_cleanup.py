import asyncio
import io
import json

import pytest
from PIL import Image
from app import frame_cleanup as cleanup, providers


async def all_clean(frames):return frames

@pytest.fixture(autouse=True)
def no_paid_integrity_in_unit_tests(monkeypatch):
    async def intact(originals,frames):return frames
    monkeypatch.setattr(cleanup,'review_integrity',intact)


def jpeg():
    b=io.BytesIO();Image.new('RGB',(1280,720),'green').save(b,format='JPEG');return b.getvalue()

def test_cleanup_budget_stops_at_fifteen(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','openai')
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    calls=[]
    async def ranked(frames):
        calls.append(len(frames))
        return [cleanup.RankedFrame(frame=i+1,usable=True,left=0,top=0,right=1000,bottom=1000,reason='best available',score=i) for i in range(len(frames))]
    monkeypatch.setattr(cleanup,'rank_frames',ranked)
    monkeypatch.setattr(cleanup,'review_crops',all_clean)
    out=asyncio.run(cleanup.clean_frames([(i,jpeg()) for i in range(20)],0))
    assert calls==[15]
    assert [x[0] for x in out]==[10,11,12,13,14]


def test_crop_bounds_and_resolution():
    d=cleanup.FrameDecision(frame=1,usable=True,left=250,top=0,right=750,bottom=800,reason='방송 그래픽 제외')
    image=Image.open(io.BytesIO(cleanup.crop_frame(jpeg(),d)))
    assert image.size==(640,576)
    d.right=300
    with pytest.raises(ValueError):cleanup.crop_frame(jpeg(),d)


def test_rejected_candidate_retried_and_all_rejected_returns_none(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    verdicts=[False,False,False,True,True]
    plan={'frame':1,'usable':True,'left':80,'top':100,'right':920,'bottom':900,'reason':'가장자리 그래픽 제외'}
    async def fake(*args,**kwargs):
        if kwargs['json']['text']['format']['name']=='frame_crop_plan':
            return {'output':[{'content':[{'type':'output_text','text':json.dumps(plan)}]}]}
        return {'output':[{'content':[{'type':'output_text','text':json.dumps({'clean':verdicts.pop(0),'reason':'checked'})}]}]}
    monkeypatch.setattr(providers,'api',fake)
    result=asyncio.run(cleanup.inspect_frame(jpeg()))
    assert Image.open(io.BytesIO(result)).size==(1075,576)
    verdicts.extend([False,False,False,False,False])
    assert asyncio.run(cleanup.inspect_frame(jpeg())) is None


def test_unsafe_adaptive_crop_is_not_used(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    async def fake(*args,**kwargs):
        return {'output':[{'content':[{'type':'output_text','text':json.dumps({'frame':1,'usable':True,'left':300,'top':0,'right':700,'bottom':1000,'reason':'too narrow'})}]}]}
    monkeypatch.setattr(providers,'api',fake)
    assert asyncio.run(cleanup.proposed_crop(jpeg())) is None


def test_gentle_crop_retains_ninety_one_percent_dimensions(monkeypatch):
    async def checked(original,candidate):
        assert original==jpeg()
        return True
    async def unnecessary(raw):pytest.fail('accepted gentle crop needs no further calls')
    monkeypatch.setattr(cleanup,'checked_crop',checked)
    monkeypatch.setattr(cleanup,'proposed_crop',unnecessary)
    result=asyncio.run(cleanup.inspect_frame(jpeg()))
    assert Image.open(io.BytesIO(result)).size==(1165,655)


def test_promo_excluded_and_shortage_blocks(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    async def ranked(frames):
        return [cleanup.RankedFrame(frame=i+1,usable=i>0,left=0,top=0,right=1000,bottom=1000,reason='scene',score=1) for i in range(len(frames))]
    monkeypatch.setattr(cleanup,'rank_frames',ranked)
    async def reviews(frames):return [x for x in frames if x[0]==20]
    monkeypatch.setattr(cleanup,'review_crops',reviews)
    frames=[(10,jpeg()),(20,jpeg())]
    assert asyncio.run(cleanup.clean_frames(frames,1))[0][0]==20
    with pytest.raises(providers.ProviderError):asyncio.run(cleanup.clean_frames(frames,2))


def test_invalid_inspection_fails_closed(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    async def fake(*args,**kwargs):return {'output':[]}
    monkeypatch.setattr(providers,'api',fake)
    with pytest.raises(providers.ProviderError):asyncio.run(cleanup.inspect_frame(jpeg()))


def test_auto_accepts_one_or_zero_frames(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    async def ranked(frames):
        return [cleanup.RankedFrame(frame=i+1,usable=False,left=0,top=0,right=1000,bottom=1000,reason='promo',score=0) for i in range(len(frames))]
    monkeypatch.setattr(cleanup,'rank_frames',ranked)
    async def rejected(frames):return []
    monkeypatch.setattr(cleanup,'review_crops',rejected)
    assert asyncio.run(cleanup.clean_frames([(1,jpeg())],0))==[]


def test_overlay_check_isolated_from_original_and_integrity_still_checked(monkeypatch):
    calls=[]
    async def check(instructions,images,name):
        calls.append((name,images))
        return name=='clean_frame_check'
    monkeypatch.setattr(cleanup,'check_images',check)
    assert asyncio.run(cleanup.checked_crop(b'logo-original',b'clean-crop')) is False
    assert calls==[('clean_frame_check',[('CANDIDATE ONLY',b'clean-crop')]),
                   ('frame_integrity_check',[('ORIGINAL',b'logo-original'),('CROPPED CANDIDATE',b'clean-crop')])]


def test_crop_batch_reviews_actual_crops_once_and_filters_individually(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    calls=[]
    async def api(*args,**kwargs):
        calls.append(kwargs['json'])
        return {'output':[{'content':[{'type':'output_text','text':json.dumps({'frames':[
            {'frame':2,'clean':True,'reason':'clean'}, {'frame':1,'clean':False,'reason':'logo'}]})}]}]}
    monkeypatch.setattr(providers,'api',api)
    frames=[(10,b'crop-one'),(20,b'crop-two')]
    assert asyncio.run(cleanup.review_crops(frames))==[frames[1]]
    assert len(calls)==1
    content=calls[0]['input'][0]['content']
    assert len([c for c in content if c['type']=='input_image'])==2
    assert all(c.get('detail')=='high' for c in content if c['type']=='input_image')
    assert asyncio.run(cleanup.review_crops([]))==[] and len(calls)==1


@pytest.mark.parametrize('numbers',[[1],[1,1],[1,3]])
def test_crop_batch_incomplete_or_duplicate_verdicts_fail_without_retry(monkeypatch,numbers):
    monkeypatch.setenv('OPENAI_API_KEY','test-only');calls=[]
    async def api(*args,**kwargs):
        calls.append(1)
        return {'output':[{'content':[{'type':'output_text','text':json.dumps({'frames':[
            {'frame':n,'clean':True,'reason':'ok'} for n in numbers]})}]}]}
    monkeypatch.setattr(providers,'api',api)
    with pytest.raises(providers.ProviderError):asyncio.run(cleanup.review_crops([(1,b'a'),(2,b'b')]))
    assert len(calls)==1


def test_lower_ranked_clean_scene_is_not_discarded(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    async def ranked(frames):
        return [cleanup.RankedFrame(frame=i+1,usable=True,left=0,top=0,right=1000,bottom=1000,reason='scene',score=100-i) for i in range(len(frames))]
    async def reviewed(frames):
        assert len(frames)==8
        return frames[5:]
    monkeypatch.setattr(cleanup,'rank_frames',ranked)
    monkeypatch.setattr(cleanup,'review_crops',reviewed)
    assert [at for at,_ in asyncio.run(cleanup.clean_frames([(i,jpeg()) for i in range(8)],0))]==[5,6,7]


def test_predicted_impossible_crop_is_checked_on_real_pixels(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    ranking=[cleanup.RankedFrame(frame=1,usable=False,left=0,top=0,right=1000,bottom=1000,reason='predicted impossible',score=0)]
    async def checked(frames):
        assert Image.open(io.BytesIO(frames[0][1])).size==(973,389)
        return frames
    monkeypatch.setattr(cleanup,'review_crops',checked)
    out=asyncio.run(cleanup.clean_frames([(1,jpeg())],0,ranking=ranking))
    assert len(out)==1
