import asyncio,json
import pytest
from app import overlay_guard as g,publishing,providers,storage as st
from test_studio import client,generate,approve_quality,configure_instagram

def response(clean=True):
 return {'output':[{'content':[{'type':'output_text','text':json.dumps({'cards':[{'card':1,'clean':clean,'reason':'검사 결과'}]})}]}]}

def test_blocked_overlay_cannot_be_overridden_and_cache_avoids_repeat_cost(client,monkeypatch):
 monkeypatch.setenv('OPENAI_API_KEY','test-only')
 p=generate(client,count=1);p.update(facts_checked=True,rights_checked=True);approve_quality(p);configure_instagram(monkeypatch)
 calls=[]
 async def inspect(*args,**kw):calls.append(1);return response(False)
 async def graph(*args,**kw):raise AssertionError('Meta must not be called')
 monkeypatch.setattr(g.p,'api',inspect);monkeypatch.setattr(publishing,'api',graph)
 for _ in range(2):
  with pytest.raises(providers.ProviderError,match='방송 로고'):asyncio.run(g.ensure_clean(p))
 assert len(calls)==1 and p['overlay_review']['status']=='blocked'

def test_overlay_error_and_changed_file_require_fresh_check(client,monkeypatch):
 monkeypatch.setenv('OPENAI_API_KEY','test-only')
 p=generate(client,count=1);calls=[]
 async def inspect(*args,**kw):calls.append(1);return response()
 monkeypatch.setattr(g.p,'api',inspect)
 asyncio.run(g.ensure_clean(p));asyncio.run(g.ensure_clean(p));assert len(calls)==1
 path=st.MEDIA/p['id']/'01.jpg';path.write_bytes(path.read_bytes()+b'changed')
 asyncio.run(g.ensure_clean(p));assert len(calls)==2
 async def broken(*args,**kw):return {}
 monkeypatch.setattr(g.p,'api',broken);p.pop('overlay_review')
 with pytest.raises(providers.ProviderError,match='완료하지 못해'):asyncio.run(g.ensure_clean(p))
 assert p['overlay_review']['status']=='error'


def test_publish_crop_repairs_once_and_preserves_original(client,monkeypatch):
 from app import frame_cleanup as fc,quality,render
 from PIL import Image
 p=generate(client,count=1)
 Image.new('RGB',(800,600),'white').save(st.ASSETS/'original.jpg')
 p['slides'][0]['asset_id']='original'
 calls=[]
 async def guard(post):
  calls.append(1)
  if len(calls)==1:
   post['overlay_review']={'status':'blocked','cards':[{'card':1,'clean':False}]}
   raise providers.ProviderError('logo')
  post['overlay_review']={'status':'passed'}
 async def rank(frames):
  return [fc.RankedFrame(frame=1,usable=True,left=100,top=100,right=900,bottom=900,reason='crop',score=80)]
 async def intact(*args):return True
 async def evaluate(post):return {'status':'passed'}
 monkeypatch.setattr(g,'ensure_clean',guard)
 monkeypatch.setattr(fc,'rank_frames',rank)
 monkeypatch.setattr(fc,'check_images',intact)
 monkeypatch.setattr(quality,'evaluate',evaluate)
 monkeypatch.setattr(quality,'ensure_passed',lambda post:None)
 asyncio.run(g.prepare_for_publish(p))
 assert len(calls)==2 and p['overlay_review']['status']=='passed'
 assert p['slides'][0]['asset_id']!='original'
 assert Image.open(st.ASSETS/'original.jpg').size==(800,600)
 assert Image.open(st.ASSETS/(p['slides'][0]['asset_id']+'.jpg')).size==(640,480)
 assert p['overlay_crop_attempt']['fingerprint']==g.digest(g.files(p))


def test_crop_retry_is_bounded(client,monkeypatch):
 p=generate(client,count=1)
 p['overlay_crop_attempt']={'fingerprint':g.digest(g.files(p))}
 async def blocked(post):
  post['overlay_review']={'status':'blocked'}
  raise providers.ProviderError('logo')
 monkeypatch.setattr(g,'ensure_clean',blocked)
 with pytest.raises(providers.ProviderError,match='다른 장면'):
  asyncio.run(g.prepare_for_publish(p))
