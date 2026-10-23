import asyncio
from datetime import datetime, timedelta
import pytest
from app import cadence, storage as st, main, quality
from app.models import PostingCadence
from test_studio import client, generate, approve_quality, configure_instagram

def test_twenty_slots_quiet_and_rollover():
    c=PostingCadence(enabled=True).model_dump()
    now=datetime(2026,10,8,5,59,tzinfo=st.KST)
    plan=cadence.plan([{'id':str(i)} for i in range(22)],[],now,c)
    times=[cadence.parse(x['at']) for x in plan]
    assert len(times)==22 and times[0].strftime('%H:%M')=='06:00'
    assert times[1].strftime('%H:%M')=='06:10' and times[19].strftime('%H:%M')=='19:40'
    assert times[20].date()==now.date()+timedelta(days=1)
    assert all(not cadence.quiet(x) for x in times)
    assert cadence.plan([],[],now,c)==[]
    with pytest.raises(ValueError):PostingCadence(start_hour=20)

def test_enable_excludes_old_and_canceled_posts(client):
    old={'id':'old','created_at':'2026-10-08T06:00:00+09:00','status':'draft','facts_checked':True,'rights_checked':True,'ratio':'4:5'}
    new={**old,'id':'new','created_at':'2026-10-08T08:00:00+09:00'}
    c={**PostingCadence(enabled=True).model_dump(),'enabled_at':'2026-10-08T07:00:00+09:00'}
    assert cadence.ready_new_posts([old,new,{**new,'id':'cancel','auto_schedule_excluded':True}],c,lambda p:None)==[new]

def test_batch_atomic_and_explicit_consecutive(client,monkeypatch):
    configure_instagram(monkeypatch)
    client.put('/api/posting-cadence',json={'enabled':True,'item_interval':5})
    posts=[generate(client,count=1) for _ in range(2)]
    for p in posts:p.update(facts_checked=True,rights_checked=True);approve_quality(p)
    posts[1]['facts_checked']=False;st.save(posts[1])
    payload={'post_ids':[p['id'] for p in posts]}
    assert client.post('/api/schedule/batch',json=payload).status_code==400
    assert all(st.get(p['id'])['status']=='draft' for p in posts)
    posts[1]['facts_checked']=True;st.save(posts[1])
    at=(datetime.now(st.KST)+timedelta(days=1)).replace(hour=9,minute=25,second=0,microsecond=0)
    r=client.post('/api/schedule/batch',json={**payload,'start_at':at.isoformat(),'consecutive':True})
    assert r.status_code==200,r.text
    times=[cadence.parse(x['at']) for x in r.json()['reservations']]
    assert times==[at,at+timedelta(minutes=5)]
    assert all(not st.get(p['id']).get('consecutive_group') for p in posts)
    assert client.post('/api/posts/'+posts[0]['id']+'/cancel').status_code==200
    assert st.get(posts[0]['id'])['auto_schedule_excluded']

def test_quiet_and_overdue_do_not_publish(client,monkeypatch):
    configure_instagram(monkeypatch)
    fixed=datetime(2026,10,8,2,0,tzinfo=st.KST)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return fixed
    monkeypatch.setattr(main,'datetime',Clock)
    st.set_setting(cadence.KEY,{**PostingCadence(enabled=True).model_dump(),'enabled_at':fixed.isoformat()})
    p=generate(client,count=1);p.update(status='scheduled',scheduled_at=(fixed-timedelta(hours=2)).isoformat());st.save(p)
    async def forbidden(p):pytest.fail('No publication during quiet hours')
    monkeypatch.setattr(main,'publish',forbidden)
    asyncio.run(main.tick())
    assert st.get(p['id'])['status']=='scheduled'
    assert cadence.parse(st.get(p['id'])['scheduled_at']).hour==6

def test_publishing_limit_and_unknown_reserve_capacity():
    c=PostingCadence(enabled=True).model_dump();now=datetime(2026,10,8,5,0,tzinfo=st.KST)
    existing=[{'id':str(i),'status':'needs_check','scheduled_at':(now+timedelta(hours=1,minutes=i)).isoformat()} for i in range(20)]
    assert cadence.parse(cadence.plan([{'id':'new'}],existing,now,c)[0]['at']).day==9

def test_worker_legacy_consecutive_group_cannot_bypass_spacing(client,monkeypatch):
    fixed=datetime(2026,10,8,9,25,tzinfo=st.KST)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return fixed
    monkeypatch.setattr(main,'datetime',Clock)
    st.set_setting(cadence.KEY,{**PostingCadence(enabled=True,item_interval=5).model_dump(),'enabled_at':fixed.isoformat()})
    first=generate(client,count=1);first.update(status='published',published_at=fixed.isoformat(),scheduled_at=fixed.isoformat(),consecutive_group='explicit-two');st.save(first)
    second=generate(client,count=1);second.update(status='scheduled',scheduled_at=fixed.isoformat(),consecutive_group='explicit-two');st.save(second)
    other=generate(client,count=1);other.update(status='scheduled',scheduled_at=fixed.isoformat());st.save(other)
    sent=[]
    async def publish(p):
        sent.append(p['id']);p.update(status='published',published_at=fixed.isoformat());st.save(p)
    monkeypatch.setattr(main,'publish',publish)
    asyncio.run(main.tick());asyncio.run(main.tick())
    assert sent==[]
    fixed+=timedelta(minutes=5)
    asyncio.run(main.tick());asyncio.run(main.tick())
    assert len(sent)==1 and sent[0] in {second['id'],other['id']}
    assert sum(st.get(p['id'])['status']=='scheduled' for p in (second,other))==1
