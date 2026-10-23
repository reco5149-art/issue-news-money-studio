import asyncio
from datetime import datetime
import pytest
from app import autopilot as a, cadence, main, storage as st
from app.models import PostingCadence
from test_studio import client,generate,approve_quality,configure_instagram

def test_news_search_rejects_unrelated_viral_results():
    assert not a.news_candidate({'snippet':{'title':'New Phone Bana Diya GIVEAWAY','channelTitle':'Viral shorts'}})
    assert not a.news_candidate({'snippet':{'title':'뉴스보다 재밌는 게임','channelTitle':'게임 채널'}})
    assert a.news_candidate({'snippet':{'title':'오늘 경제 소식','channelTitle':'JTBC News'}})

def test_keyword_search_and_portal_fallback_keep_publisher_identity(monkeypatch):
    async def plan(*args):return {'queries':['코넬대 의혹','없는이름 새로운사건']}
    queries=[]
    async def discover(q):
        queries.append(q)
        return {'items':[{'url':'https://first.example/a','portal_url':'https://news.naver.com/a'}, {'url':'https://second.example/b'}]}
    async def extract(url):
        if url=='https://first.example/a':raise ValueError('unavailable')
        return {'source_url':url,'source_name':'news','title':'코넬대 의혹','text':'기사 본문입니다. '*40}
    monkeypatch.setattr(a,'structured',plan);monkeypatch.setattr(a.p,'discover',discover);monkeypatch.setattr(a.p,'extract',extract)
    sources=asyncio.run(a.evidence({'snippet':{'title':'코넬대 의혹, 어떻게 됐나?','channelTitle':'뉴스'}}, {'text':'코넬대 의혹에 관한 발언','source_url':'https://youtube.com/watch?v=abc'}))
    assert queries==['코넬대 의혹']
    assert len(sources)==3 and sources[1]['publisher_domain']=='first.example'
    assert sources[1]['source_url']=='https://news.naver.com/a'

def test_no_results_waits_with_bounds_instead_of_claiming_completion(client,monkeypatch):
    now=configured(monkeypatch)
    calls=[]
    async def empty():calls.append(1);return []
    monkeypatch.setattr(a,'candidates',empty)
    asyncio.run(a.run(None,None,main.LOCK))
    journal=a.state()
    assert journal['status']=='waiting' and not a.should_run(journal,now)
    asyncio.run(a.run(None,None,main.LOCK))
    assert len(calls)==1
    journal.update(round=2,next_retry_at=now.isoformat())
    st.set_setting(a.key(now.date().isoformat()),journal)
    asyncio.run(a.run(None,None,main.LOCK))
    assert a.state()['status']=='waiting' and a.state()['round']==3 and len(calls)==2
    journal=a.state();journal.update(round=10,next_retry_at=now.isoformat())
    st.set_setting(a.key(now.date().isoformat()),journal)
    asyncio.run(a.run(None,None,main.LOCK))
    assert a.state()['status']=='waiting' and a.state()['round']==11 and len(calls)==3

def test_retry_remains_bounded_without_round_limit(client,monkeypatch):
    now=configured(monkeypatch)
    assert a.can_retry({'round':100,'source_attempts':149,'generation_attempts':19},now)
    assert not a.can_retry({'source_attempts':150,'generation_attempts':0},now)
    assert not a.can_retry({'source_attempts':0,'generation_attempts':20},now)
    assert not a.can_retry({},now.replace(hour=23,minute=50))

@pytest.mark.parametrize('error_code',['openai_quota','ai_quota','api_auth','external_rate_limit','openai_rate_limit'])
def test_quota_failure_requires_action_without_repeated_calls(client,monkeypatch,error_code):
    now=configured(monkeypatch);calls=[]
    async def exhausted():
        calls.append(1);raise a.p.ProviderError('프로젝트 한도 초과',code=error_code)
    monkeypatch.setattr(a,'candidates',exhausted)
    asyncio.run(a.run(None,None,main.LOCK))
    assert a.state()['status']=='needs_action' and not a.should_run(a.state(),now)
    asyncio.run(a.run(None,None,main.LOCK));assert len(calls)==1

def test_retry_preserves_attempt_budget_and_existing_reservations(client,monkeypatch):
    now=configured(monkeypatch)
    st.set_setting(a.key(now.date().isoformat()),{'status':'needs_action','attempted':['one'],'created':[],'source_attempts':2,'generation_attempts':1})
    monkeypatch.setattr(main,'PRODUCTION_TASK',None)
    response=client.post('/api/autopilot/retry')
    assert response.status_code==200 and a.state()['status']=='ready'
    assert a.state()['source_attempts']==2 and a.state()['generation_attempts']==1
    journal=a.state();journal['generation_attempts']=20;st.set_setting(a.key(now.date().isoformat()),journal)
    assert client.post('/api/autopilot/retry').status_code==400

@pytest.mark.parametrize('attempts,expected',[(100,200),(149,200),(150,400)])
def test_candidate_budget_one_hundred_fifty(client,monkeypatch,attempts,expected):
    now=configured(monkeypatch)
    st.set_setting(a.key(now.date().isoformat()),{'status':'blocked','attempted':[],'created':[], 'source_attempts':attempts,'generation_attempts':0})
    monkeypatch.setattr(main,'PRODUCTION_TASK',None)
    assert client.post('/api/autopilot/retry').status_code==expected
    assert a.state()['source_attempts']==attempts

def configured(monkeypatch):
    configure_instagram(monkeypatch)
    for k in ['OPENAI_API_KEY','YOUTUBE_API_KEY','NAVER_CLIENT_ID','NAVER_CLIENT_SECRET']:monkeypatch.setenv(k,'test')
    async def delivery(post=None):pass
    monkeypatch.setattr(a,'verify_delivery',delivery)
    fixed=datetime(2026,10,8,7,0,tzinfo=st.KST)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return fixed
    monkeypatch.setattr(a,'datetime',Clock);monkeypatch.setattr(main,'datetime',Clock)
    monkeypatch.setattr(a.source_policy,'datetime',Clock)
    st.set_setting(cadence.KEY,PostingCadence(enabled=True,autopilot=True).model_dump())
    return fixed

def test_verification_rejects_invented_quotes(monkeypatch):
    result={'passed':True,'independent':True,'reason':'ok','claims':[{'claim':'fact','supported':True,'evidence':[{'source':0,'passage':0},{'source':1,'passage':99}]}]}
    async def fake(*args):return result
    monkeypatch.setattr(a,'structured',fake)
    sources=[{'text':'This sentence exists.','source_url':'https://one.example/a'},{'text':'The second report agrees.','source_url':'https://two.example/b'}]
    assert not asyncio.run(a.verify({'slides':[],'caption':'fact'},sources))['passed']
    result['evidence']=None
    result['claims'][0]['evidence'][1]['passage']=0
    result['passed']=True
    assert asyncio.run(a.verify({'slides':[],'caption':'fact'},sources))['passed']

def test_unsupported_claim_cannot_pass_with_real_passages(monkeypatch):
    async def fake(*args):
        return {'passed':True,'independent':True,'reason':'ok','claims':[{'claim':'unsupported','supported':False,'evidence':[{'source':0,'passage':0},{'source':1,'passage':0}]}]}
    monkeypatch.setattr(a,'structured',fake)
    result=asyncio.run(a.verify({'slides':[],'caption':'fact'},[{'text':'First source text.','source_url':'https://one.example/a'},{'text':'Second source text.','source_url':'https://two.example/a'}]))
    assert not result['passed'] and '근거 미확인' in result['reason']

def test_missing_auto_photos_skip_paid_quality_review(client,monkeypatch):
    from app import web_art
    from app.models import Generate
    async def attach(*args):return [],['missing']
    async def unexpected(*args):raise AssertionError('paid review must not run')
    monkeypatch.setattr(web_art,'attach',attach)
    monkeypatch.setattr(main.quality,'evaluate',unexpected)
    before=len(st.posts())
    with pytest.raises(ValueError,match='유튜브 영상 캡처'):
        asyncio.run(main.create(Generate(text='사진 없는 뉴스 내용입니다.',image_mode='web',count=2),automation_day='2026-10-10'))
    assert len(st.posts())==before

def test_state_counts_repaired_posts_from_current_status(client):
    post=generate(client,count=1)
    post.update(status='published',instagram_id='confirmed');st.save(post)
    st.set_setting(a.key(datetime.now(st.KST).date().isoformat()),{'status':'waiting','created':[post['id']],'message':'자동 예약/게시 0개 · 보류 기록 1개'})
    assert a.state()['delivery_counts']['published']==1
    assert '자동 예약/게시 1개' in a.state()['message']

def test_rights_need_original_page_evidence(monkeypatch):
    post={'slides':[{'asset_id':'a','license_evidence':{'license':'CC0 1.0','license_url':'https://creativecommons.org/publicdomain/zero/1.0/','page':'https://photos.example/a'}}]}
    async def missing(*args):return b'All rights reserved','text/html','https://photos.example/a'
    monkeypatch.setattr(a.p,'fetch_public',missing)
    assert not asyncio.run(a.photo_rights(post))['passed']
    async def present(*args):return b'<a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a>','text/html','https://photos.example/a'
    monkeypatch.setattr(a.p,'fetch_public',present)
    assert asyncio.run(a.photo_rights(post))['passed']
    assert not asyncio.run(a.photo_rights({'slides':[{}]}))['passed']

@pytest.mark.parametrize('facts,rights,expected',[(True,True,'scheduled'),(False,True,'draft'),(True,False,'draft')])
def test_pipeline_schedules_only_verified_new_content(client,monkeypatch,facts,rights,expected):
    now=configured(monkeypatch)
    old=generate(client,count=1)
    video={'id':'abcdefghijk','snippet':{'title':'확인할 뉴스','channelTitle':'뉴스','publishedAt':now.isoformat()},'statistics':{'viewCount':'100000'},'status':{'privacyStatus':'public'}}
    async def candidates():return [video]
    async def material(*args):return {},[{'text':'확인한 본문'}],{'image_mode':'web'}
    made=[]
    async def create(req,automation_day=None):
        p=generate(client,count=1);p.update(source_url=req.source_url,automation_day=automation_day,auto_schedule_excluded=True)
        approve_quality(p);made.append(p['id']);return p
    async def verify(*args):return {'passed':facts,'reason':'근거 검토'}
    async def photo(*args):return {'passed':rights,'reason':'라이선스 검토'}
    for name,fn in [('candidates',candidates),('material',material),('verify',verify),('photo_rights',photo)]:monkeypatch.setattr(a,name,fn)
    asyncio.run(a.run(create,lambda *args:None,main.LOCK))
    assert st.get(made[0])['status']==expected
    assert st.get(old['id'])['status']=='draft'
    assert st.get(made[0])['facts_checked']==facts and st.get(made[0])['rights_checked']==rights
    asyncio.run(a.run(create,lambda *args:None,main.LOCK))
    assert len(made)==1 # completed day cannot duplicate paid generation or posts

def test_save_enables_pipeline_and_disables_duplicate_draft_runner(client,monkeypatch):
    configured(monkeypatch)
    st.set_setting('daily',{'enabled':True,'hour':10,'daily_target':20,'categories':['뉴스']})
    r=client.put('/api/posting-cadence',json={'enabled':True,'autopilot':True})
    assert r.status_code==200 and r.json()['autopilot']
    assert not st.setting('daily')['enabled']
    monkeypatch.delenv('OPENAI_API_KEY')
    assert client.put('/api/posting-cadence',json={'enabled':True,'autopilot':True}).status_code==400

def test_production_does_not_block_due_publish(client,monkeypatch):
    now=configured(monkeypatch);p=generate(client,count=1)
    p.update(status='scheduled',scheduled_at=now.isoformat());st.save(p)
    sent=[]
    async def slow(*args):await asyncio.sleep(100)
    async def publish(p):sent.append(p['id'])
    monkeypatch.setattr(a,'run',slow);monkeypatch.setattr(main,'publish',publish);monkeypatch.setattr(main,'PRODUCTION_TASK',None)
    async def exercise():
        await asyncio.wait_for(main.tick(),timeout=2)
        main.PRODUCTION_TASK.cancel()
        try:await main.PRODUCTION_TASK
        except asyncio.CancelledError:pass
    asyncio.run(exercise());assert sent==[p['id']]


def test_material_captures_max_15_and_never_falls_back(client,monkeypatch):
    import io,json
    from PIL import Image
    b=io.BytesIO();Image.new('RGB',(640,480),'blue').save(b,format='JPEG')
    async def refresh(video):return video
    monkeypatch.setattr(a.source_policy,'refresh',refresh)
    async def extract(*args):return {'text':'영상 원문'}
    async def evidence(*args):return [{'text':'기사 원문'}]
    def capture(url,count,path):
        assert count==15
        return [(1.5,b.getvalue())]
    async def clean(frames,count):return frames
    monkeypatch.setattr(a,'extract_video',extract);monkeypatch.setattr(a,'evidence',evidence)
    monkeypatch.setattr(a,'youtube_frames',capture);monkeypatch.setattr(a,'clean_frames',clean)
    _,_,image=asyncio.run(a.material({'id':'abcdefghijk'},main.asset_save))
    assert image['image_mode']=='video' and len(image['video_asset_ids'])==1
    meta=json.loads((st.ASSETS/(image['video_asset_ids'][0]+'.json')).read_text(encoding='utf8'))
    assert meta['at']==1.5 and meta['permission_verified'] is False
    async def empty(*args):return []
    monkeypatch.setattr(a,'clean_frames',empty)
    with pytest.raises(ValueError,match='사진 없는 초안'):
        asyncio.run(a.material({'id':'abcdefghijk'},main.asset_save))


@pytest.mark.parametrize('duration,live,expected',[
    ('PT20M','none',True),('PT20M1S','none',False),('PT1H30M','none',False),
    ('PT10M','live',False),('PT10M','upcoming',False),('P0D','none',False),('', 'none',False)])
def test_source_support_is_checked_before_paid_collection(duration,live,expected):
    v={'snippet':{'liveBroadcastContent':live},'contentDetails':{'duration':duration}}
    assert a.capture_support(v)['passed'] is expected


def test_grounded_query_handles_spacing_and_uses_source_fallback():
    assert a.grounded_queries({'queries':['한국증시 하락']},'한국 증시 하락','')==['한국증시 하락']
    assert a.grounded_queries({'queries':['가짜이름 사기']},'[뉴스] 코스피 급락 외국인 매도 / MBC','')==['코스피 급락 외국인 매도']
    assert a.grounded_queries({'queries':['없는말 추측']},'[뉴스] 속보','')==[]


def test_unsupported_candidates_do_not_consume_material_attempts(client,monkeypatch):
    configured(monkeypatch)
    v={'id':'livevideo01','capture_support':{'passed':False,'code':'live_video','reason':'live'}}
    async def pool():return [v]
    async def forbidden(*args):pytest.fail('unsupported video must not reach paid material collection')
    monkeypatch.setattr(a,'candidates',pool);monkeypatch.setattr(a,'material',forbidden)
    asyncio.run(a.run(None,None,main.LOCK))
    journal=a.state()
    assert journal['source_attempts']==0 and journal['processable_count']==0
    assert journal['excluded_candidates'][0]['code']=='live_video'
