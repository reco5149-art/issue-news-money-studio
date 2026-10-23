import asyncio
from datetime import datetime, timedelta
import pytest
from app import source_policy as policy, autopilot, publishing, storage as st, providers
from test_studio import client, generate, approve_quality, configure_instagram

NOW = datetime(2026,10,16,11,30,tzinfo=st.KST)

def video(age=6, views='100000', vid='abcdefghijk'):
    return {'id':vid,'snippet':{'title':'오늘 주요 경제 뉴스','channelTitle':'JTBC News',
            'publishedAt':(NOW-timedelta(hours=age)).isoformat()},
            'statistics':{'viewCount':views},'status':{'privacyStatus':'public'}}

def freeze(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW
    monkeypatch.setattr(policy,'datetime',Clock)
    monkeypatch.setattr(autopilot,'datetime',Clock)

@pytest.mark.parametrize('age,views,expected',[
    (12,'100000',True),(12+1/3600,'100000',False),(11,'99999',False),
    (0,'100000',True),(-1,'999999',False),(1,None,False),(1,'unknown',False)])
def test_exact_age_and_view_boundaries(age,views,expected):
    assert policy.assess(video(age,views),now=NOW)['passed'] is expected

def test_missing_private_deleted_and_future_data_fail_closed():
    for v in ({}, {'id':'abcdefghijk'}, {**video(),'status':{}}, {**video(),'status':{'privacyStatus':'private'}}):
        assert not policy.assess(v,now=NOW)['passed']
    assert not policy.assess(video(-1),now=NOW,at=NOW+timedelta(hours=2))['passed']

def test_later_reservation_expires_even_when_selection_passed():
    v=video(11)
    assert policy.assess(v,now=NOW)['passed']
    assert not policy.assess(v,now=NOW,at=NOW+timedelta(hours=2))['passed']

def test_search_uses_twelve_hour_window_and_api_metrics(monkeypatch):
    freeze(monkeypatch);monkeypatch.setenv('YOUTUBE_API_KEY','test')
    calls=[]
    rows=[video(),video(13,vid='oldoldold01'),video(3,'99999',vid='lowview001')]
    async def api(method,url,**kwargs):
        calls.append((url,kwargs['params']))
        if url.endswith('/search'):
            return {'items':[{'id':{'videoId':v['id']}} for v in rows]}
        return {'items':rows}
    monkeypatch.setattr(providers,'api',api)
    result=asyncio.run(autopilot.candidates())
    assert [v['id'] for v in result]==['abcdefghijk']
    assert result[0]['selection_evidence']['checked_at']==NOW.isoformat()
    assert all(datetime.fromisoformat(params['publishedAfter'])==NOW-timedelta(hours=12)
               for url,params in calls if url.endswith('/search'))

def test_stale_source_stops_before_material_ai_or_capture(monkeypatch):
    freeze(monkeypatch)
    async def stale(vid):return video(13)
    async def forbidden(*args):pytest.fail('No paid extraction for stale sources')
    monkeypatch.setattr(policy,'fetch_video',stale)
    monkeypatch.setattr(autopilot,'extract_video',forbidden)
    with pytest.raises(providers.ProviderError,match='12시간'):
        asyncio.run(autopilot.material(video(),None))

@pytest.mark.parametrize('kind',['stale','low','missing','unavailable'])
def test_publish_rechecks_before_any_meta_or_paid_review(client,monkeypatch,kind):
    freeze(monkeypatch);configure_instagram(monkeypatch)
    post=generate(client,count=1)
    post.update(facts_checked=True,rights_checked=True,automation_day='2026-10-15',
                source_url='https://www.youtube.com/watch?v=abcdefghijk')
    approve_quality(post)
    async def fresh(vid):
        if kind=='unavailable':raise providers.ProviderError('조회 실패')
        return video(13) if kind=='stale' else video(3,'99999') if kind=='low' else {'id':vid}
    async def forbidden(*args,**kwargs):pytest.fail('No Meta or AI request for ineligible source')
    monkeypatch.setattr(policy,'fetch_video',fresh)
    monkeypatch.setattr(publishing,'api',forbidden)
    monkeypatch.setattr(publishing,'ensure_clean',forbidden)
    with pytest.raises(providers.ProviderError):asyncio.run(publishing.publish(post,explicit_manual=True))
    assert st.get(post['id'])['source_eligibility']['passed'] is False
    assert st.get(post['id'])['status']!='published'

def test_container_delay_cannot_bypass_expiry(client,monkeypatch):
    freeze(monkeypatch)
    post=generate(client,count=1)
    with pytest.raises(providers.ProviderError):policy.ensure_still_current(post,video(12.01))
    assert not st.get(post['id'])['source_eligibility']['passed']

def test_status_reports_the_same_policy_used_by_worker(client):
    policy_from_server=client.get('/api/status').json()['source_policy']
    assert policy_from_server==policy.config()
    assert policy_from_server['max_age_hours']==12 and policy_from_server['min_views']==100000

@pytest.mark.parametrize('expires_during_upload',[False,True])
def test_fresh_post_sends_once_but_container_delay_blocks_expired_post(client,monkeypatch,expires_during_upload):
    freeze(monkeypatch);configure_instagram(monkeypatch)
    post=generate(client,count=1)
    post.update(facts_checked=True,rights_checked=True,automation_day='2026-10-16',
                source_url='https://www.youtube.com/watch?v=abcdefghijk')
    approve_quality(post)
    post['image_mode']='video'
    post['slides'][0]['asset_id']='a'*32
    (st.ASSETS/('a'*32+'.jpg')).write_bytes((st.MEDIA/post['id']/'01.jpg').read_bytes())
    approve_quality(post)
    current=[NOW];calls=[]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return current[0]
    monkeypatch.setattr(policy,'datetime',Clock)
    async def fresh(vid):return video(11.99)
    async def clean(post):pass
    async def api(method,url,**kwargs):
        calls.append((method,url))
        if url.endswith('/media'):
            if expires_during_upload:current[0]+=timedelta(minutes=1)
            return {'id':'container'}
        if url.endswith('/container'):return {'status_code':'FINISHED'}
        if url.endswith('/media_publish'):return {'id':'live'}
        if url.endswith('/live'):
            return {'id':'live','permalink':'https://www.instagram.com/p/test/',
                    'media_type':'IMAGE','timestamp':current[0].isoformat()}
        pytest.fail('unexpected remote request')
    monkeypatch.setattr(policy,'fetch_video',fresh)
    monkeypatch.setattr(publishing,'ensure_clean',clean)
    monkeypatch.setattr(publishing,'verify_delivery',clean)
    monkeypatch.setattr(publishing,'api',api)
    monkeypatch.setattr(publishing,'public_url',lambda url:url)
    if expires_during_upload:
        with pytest.raises(providers.ProviderError,match='12시간'):asyncio.run(publishing.publish(post))
        assert not st.get(post['id'])['source_eligibility']['passed']
        assert not any(url.endswith('/media_publish') for _,url in calls)
    else:
        asyncio.run(publishing.publish(post))
        assert st.get(post['id'])['publication_verification']['status']=='verified'
        assert sum(url.endswith('/media_publish') for _,url in calls)==1
