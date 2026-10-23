from datetime import datetime,timedelta
import json
import pytest
from app import publication_policy as policy, storage as st, quality, overlay_guard, cadence
from app.hook_policy import HOOK_VERSION
from app.copy_prompts import STORY_VERSION
from test_studio import client,generate,approve_quality,configure_instagram
import asyncio
from app import autopilot,main
from test_autopilot import configured

def eligible_post(client):
    post=generate(client,count=1)
    aid='a'*32
    (st.ASSETS/(aid+'.jpg')).write_bytes((st.MEDIA/post['id']/'01.jpg').read_bytes())
    post.update(image_mode='video',automation_day=post['created_at'][:10],facts_checked=True,rights_checked=False,
                source_verification={'review':{'passed':True}},hook_policy_version=HOOK_VERSION,story_policy_version=STORY_VERSION)
    post['slides'][0]['asset_id']=aid
    approve_quality(post)
    post['overlay_review']={'version':overlay_guard.VERSION,'status':'passed','fingerprint':overlay_guard.digest(overlay_guard.files(post))}
    st.save(post)
    st.set_setting(policy.KEY,{'enabled':True,'acknowledge_unverified_rights':True,'requested_by':'user','approval_id':'test-approval',
                              'approved_at':(datetime.fromisoformat(post['created_at'])-timedelta(seconds=1)).isoformat()})
    return post

def test_automatic_consent_preserves_rights_and_expires_on_changes(client):
    post=eligible_post(client)
    assert policy.record_automatic(post)
    assert policy.authorized(post)
    assert post['rights_checked'] is False
    assert post['automatic_publication_consent']['rights_verified'] is False
    post['caption']+=' changed'
    assert not policy.authorized(post)

@pytest.mark.parametrize('change',['old','facts','hook','overlay','quality','revoked'])
def test_automatic_consent_requires_every_gate(client,change):
    post=eligible_post(client)
    if change=='old':post['created_at']='2020-01-01T00:00:00+09:00'
    if change=='facts':post['source_verification']['review']['passed']=False
    if change=='hook':post['hook_policy_version']='old'
    if change=='overlay':post['overlay_review']['status']='blocked'
    if change=='quality':post['quality']['status']='blocked'
    if change=='revoked':st.set_setting(policy.KEY,{'enabled':False})
    if change=='quality':
        with pytest.raises(ValueError):policy.record_automatic(post)
    else:assert not policy.record_automatic(post)
    assert not policy.authorized(post)

def test_revocation_invalidates_existing_automatic_consent(client):
    post=eligible_post(client);assert policy.record_automatic(post)
    st.set_setting(policy.KEY,{'enabled':False})
    assert not policy.authorized(post)

def test_schedule_requires_explicit_consent_and_preserves_five_minute_gap(client,monkeypatch):
    configure_instagram(monkeypatch)
    st.set_setting(cadence.KEY,{'enabled':True,'item_interval':5,'daily_limit':20})
    post=generate(client,count=1);post.update(facts_checked=True,rights_checked=False);approve_quality(post)
    at=(datetime.now(st.KST)+timedelta(days=1)).replace(hour=12,minute=0,second=0,microsecond=0)
    url='/api/posts/'+post['id']+'/schedule'
    assert client.post(url,json={'at':at.isoformat()}).status_code==400
    r=client.post(url,json={'at':at.isoformat(),'acknowledge_unverified_rights':True})
    assert r.status_code==200,r.text
    saved=st.get(post['id']);assert not saved['rights_checked'] and policy.authorized(saved)
    other=generate(client,count=1);other.update(facts_checked=True,rights_checked=False);approve_quality(other)
    body={'at':(at+timedelta(minutes=4)).isoformat(),'acknowledge_unverified_rights':True}
    assert client.post('/api/posts/'+other['id']+'/schedule',json=body).status_code==400
    body['at']=(at+timedelta(minutes=5)).isoformat()
    assert client.post('/api/posts/'+other['id']+'/schedule',json=body).status_code==200

def test_policy_enable_is_explicit_and_idempotent(client):
    assert client.put('/api/publication-policy',json={'enabled':True}).status_code==400
    body={'enabled':True,'acknowledge_unverified_rights':True}
    first=client.put('/api/publication-policy',json=body).json()
    again=client.put('/api/publication-policy',json=body).json()
    assert first['approval_id']==again['approval_id'] and first['approved_at']==again['approved_at']
    assert client.get('/api/status').json()['publication_policy']['hook_policy_version']==HOOK_VERSION

@pytest.mark.parametrize('approved',[True,False])
def test_video_pipeline_honors_standing_consent_without_forging_licence(client,monkeypatch,approved):
    now=configured(monkeypatch)
    post=eligible_post(client)
    if not approved:st.set_setting(policy.KEY,{'enabled':False})
    old=generate(client,count=1)
    video={'id':'new-video-id','snippet':{'title':'검증한 새 영상','channelTitle':'뉴스','publishedAt':now.isoformat()},'statistics':{'viewCount':'100000'},'status':{'privacyStatus':'public'}}
    async def candidates():return [video]
    async def material(*args):return {},[{'text':'검증한 본문'}],{'image_mode':'video'}
    async def create(req,automation_day=None):
        post.update(source_url=req.source_url,automation_day=automation_day,auto_schedule_excluded=True)
        approve_quality(post)
        st.save(post)
        return post
    async def verify(*args):return {'passed':True,'reason':'본문 대조 통과'}
    async def clean(post):return None
    monkeypatch.setattr(autopilot,'candidates',candidates)
    monkeypatch.setattr(autopilot,'material',material)
    monkeypatch.setattr(autopilot,'verify',verify)
    monkeypatch.setattr(overlay_guard,'prepare_for_publish',clean)
    asyncio.run(autopilot.run(create,lambda *args:None,main.LOCK))
    saved=st.get(post['id'])
    assert saved['status']==('scheduled' if approved else 'draft')
    assert saved['rights_checked'] is False
    assert bool(saved.get('automatic_publication_consent')) is approved
    assert st.get(old['id'])['status']=='draft'
