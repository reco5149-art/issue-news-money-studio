from datetime import datetime, timedelta
import pytest
from test_studio import client, generate, approve_quality, configure_instagram
from app import storage as st, quality


def pending(client):
    post=generate(client)
    post.update(facts_checked=True,rights_checked=True)
    approve_quality(post)
    post['quality']['status']='blocked'
    post['quality']['cards'][0]['hook']=5
    post['quality']['cards'][0]['sync']=24
    st.save(post)
    return post


def test_explicit_approval_allows_reservation_without_changing_scores(client,monkeypatch):
    configure_instagram(monkeypatch)
    post=pending(client)
    r=client.post(f'/api/posts/{post["id"]}/approve')
    assert r.status_code==200
    assert r.json()['quality']['cards']==post['quality']['cards']
    at=(datetime.now(st.KST)+timedelta(minutes=10)).isoformat()
    r=client.post(f'/api/posts/{post["id"]}/schedule',json={'at':at})
    assert r.status_code==200 and r.json()['status']=='scheduled'


@pytest.mark.parametrize('reason',['critical','stale','unchecked','error','missing','trash'])
def test_manual_approval_cannot_bypass_review_integrity(client,reason):
    post=pending(client)
    if reason=='critical':post['quality']['cards'][0]['critical']=True
    if reason=='stale':post['caption']+='changed'
    if reason=='unchecked':post['rights_checked']=False
    if reason=='error':post['quality']['status']='error'
    if reason=='missing':post.pop('quality')
    if reason=='trash':post['trashed_at']=st.now()
    st.save(post)
    assert client.post(f'/api/posts/{post["id"]}/approve').status_code in (400,409)


def test_approval_invalidated_by_later_edit(client):
    post=pending(client);quality.approve_manual(post)
    quality.ensure_passed(post)
    post['caption']+='later edit'
    with pytest.raises(ValueError):quality.ensure_passed(post)
