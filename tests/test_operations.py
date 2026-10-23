import asyncio
from datetime import datetime, timedelta
import pytest
from app import operations, publishing, delivery, providers, storage as st, cadence, main
from test_studio import client, generate, approve_quality, configure_instagram


@pytest.mark.parametrize('manual',[False,True])
def test_shared_publish_gap_prevents_remote_or_paid_calls(client,monkeypatch,manual):
    configure_instagram(monkeypatch)
    st.set_setting(cadence.KEY,{'enabled':False,'item_interval':5})
    post=generate(client,count=1)
    st.save({**post,'id':'earlier','status':'published','published_at':st.now(),'instagram_id':'live'})
    async def forbidden(*args,**kwargs):pytest.fail('No API calls inside the five-minute gap')
    monkeypatch.setattr(publishing,'api',forbidden)
    monkeypatch.setattr(publishing,'ensure_clean',forbidden)
    with pytest.raises(providers.ProviderError,match='최소 5분'):
        asyncio.run(publishing.publish(post,explicit_manual=manual))


def test_exact_gap_and_uncertain_previous_publication(client,monkeypatch):
    post=generate(client,count=1)
    fixed=datetime(2026,10,16,14,0,tzinfo=st.KST)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return fixed
    monkeypatch.setattr(operations,'datetime',Clock)
    st.set_setting(cadence.KEY,{'item_interval':5})
    prior={**post,'id':'prior','status':'published','published_at':(fixed-timedelta(minutes=5)).isoformat()}
    st.save(prior);operations.ensure_send_allowed(post)
    prior['published_at']=(fixed-timedelta(minutes=5)+timedelta(seconds=1)).isoformat();st.save(prior)
    with pytest.raises(providers.ProviderError):operations.ensure_send_allowed(post)
    prior['status']='needs_check';st.save(prior)
    with pytest.raises(providers.ProviderError,match='결과가 확인되지'):operations.ensure_send_allowed(post)


@pytest.mark.parametrize('state',['published','publishing','needs_check'])
def test_stale_caller_cannot_resend_remote_post(client,state):
    post=generate(client,count=1)
    st.save({**post,'status':state})
    with pytest.raises(providers.ProviderError,match='다시 전송하지'):operations.ensure_send_allowed(post)


@pytest.mark.parametrize('problem',['no_asset','wrong_mode','missing_file','damaged_file'])
def test_every_automatic_slide_needs_a_readable_capture(client,problem):
    post=generate(client,count=2)
    post.update(automation_day=st.now()[:10],image_mode='video')
    for i,slide in enumerate(post['slides']):
        slide['asset_id']=str(i)*32
        (st.ASSETS/(slide['asset_id']+'.jpg')).write_bytes((st.MEDIA/post['id']/'01.jpg').read_bytes())
    operations.ensure_photos(post)
    if problem=='no_asset':post['slides'][1].pop('asset_id')
    if problem=='wrong_mode':post['image_mode']='none'
    if problem=='missing_file':(st.ASSETS/(post['slides'][1]['asset_id']+'.jpg')).unlink()
    if problem=='damaged_file':(st.MEDIA/post['id']/'02.jpg').write_bytes(b'broken')
    with pytest.raises(providers.ProviderError):operations.ensure_photos(post)


@pytest.mark.parametrize('problem',['dns','mismatch','wrong_type'])
def test_public_image_failure_stops_before_meta(client,monkeypatch,problem):
    configure_instagram(monkeypatch);post=generate(client,count=1)
    post.update(facts_checked=True,rights_checked=True);approve_quality(post)
    async def clean(*args):pass
    async def fetch(*args,**kwargs):
        if problem=='dns':raise providers.ProviderError('public.example DNS 조회 실패',code='dns_resolution')
        return ((b'wrong' if problem=='mismatch' else (st.MEDIA/post['id']/'01.jpg').read_bytes()),
                'text/html' if problem=='wrong_type' else 'image/jpeg','https://example.com')
    async def forbidden(*args,**kwargs):pytest.fail('No Meta calls for missing public images')
    monkeypatch.setattr(publishing,'ensure_clean',clean)
    monkeypatch.setattr(providers,'fetch_public',fetch)
    monkeypatch.setattr(publishing,'public_url',lambda url:url)
    monkeypatch.setattr(publishing,'api',forbidden)
    with pytest.raises(providers.ProviderError):asyncio.run(publishing.publish(post))
    assert not st.get(post['id']).get('publication_preflight')


def test_status_separates_enabled_waiting_and_live_success(client):
    journal={'status':'waiting','held':[{'reason':'원문 확보 실패'}]*3,
             'delivery_counts':{'draft':3,'published':0,'scheduled':0,'publishing':0}}
    result=operations.snapshot(journal,[],source_limit=150,video_attempt_limit=2)
    assert result['status']=='needs_attention' and result['today_live_verified']==0
    assert result['hold_reasons']==[{'reason':'원문 확보 실패','count':3}]
    journal['delivery_counts']['scheduled']=1
    result=operations.snapshot(journal,[],source_limit=150,video_attempt_limit=2)
    assert result['status']=='observing' and result['today_live_verified']==0
    post={'status':'published','published_at':st.now(),'publication_verification':{'status':'needs_check'}}
    result=operations.snapshot(journal,[post],source_limit=150,video_attempt_limit=2)
    assert result['today_published']==1 and result['today_live_verified']==0
    post['publication_verification']['status']='verified'
    assert operations.snapshot(journal,[post],source_limit=150,video_attempt_limit=2)['today_live_verified']==1
    state=client.get('/api/status').json()
    assert state['operations']['rules']['source_attempt_limit']==main.autopilot.SOURCE_ATTEMPT_LIMIT
    assert state['operations']['version']==operations.VERSION


def test_hold_overview_preserves_history_and_separates_excluded_and_recovered():
    from app.operations import hold_overview
    journal={'held':[{'source_url':'one','reason':'capture'},{'source_url':'one','reason':'capture'},
        {'source_url':'two','reason':'long'},{'source_url':'three','reason':'pending'}],
        'excluded_candidates':[{'source_url':'two'}]}
    posts=[{'source_url':'one','status':'published','publication_verification':{'status':'verified'}}]
    h=hold_overview(journal,posts)
    assert h['unresolved_count']==1 and h['excluded_count']==1 and h['recovered_published_count']==1
    assert h['historical_record_count']==4 and len(journal['held'])==4
    posts[0]['publication_verification']['status']='needs_check'
    assert hold_overview(journal,posts)['recovered_published_count']==0
