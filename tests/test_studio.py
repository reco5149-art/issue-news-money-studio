import asyncio
import io
import zipfile
from datetime import datetime,timedelta
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app import main,storage as st,providers,publishing,render

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(st,'DATA',tmp_path)
    monkeypatch.setattr(st,'MEDIA',tmp_path/'media')
    monkeypatch.setattr(st,'ASSETS',tmp_path/'assets')
    monkeypatch.setattr(render,'MEDIA',tmp_path/'media')
    monkeypatch.setattr(render,'ASSETS',tmp_path/'assets')
    for key in ['OPENAI_API_KEY','NAVER_CLIENT_ID','NAVER_CLIENT_SECRET','YOUTUBE_API_KEY','INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','PUBLIC_MEDIA_BASE_URL']:
        monkeypatch.delenv(key,raising=False)
    st.init()
    return TestClient(main.app)

def generate(client,**kw):
    r=client.post('/api/generate',json={'text':'AI 정보를 확인하는 방법\n원문과 숫자를 확인하세요.\n출처를 직접 읽어보세요.','count':3,**kw})
    assert r.status_code==200,r.text
    return r.json()

@pytest.mark.parametrize('ratio,size,count',[('4:5',(1080,1350),1),('1:1',(1080,1080),2),('9:16',(1080,1920),10)])
def test_generate_png_zip(client,ratio,size,count):
    p=generate(client,ratio=ratio,count=count)
    assert len(p['images'])==count and p['status']=='draft'
    for i in range(count):assert Image.open(st.MEDIA/p['id']/f'{i+1:02}.png').size==size
    r=client.get(f'/api/posts/{p["id"]}/download')
    z=zipfile.ZipFile(io.BytesIO(r.content))
    assert len(z.namelist())==count+2
    assert '출처:' in z.read('caption.txt').decode('utf-8')

def test_edit_persists(client):
    p=generate(client)
    body={'slides':[{'title':'변경한 제목','body':'본문 확인'}],'caption':'새 캡션','source_name':'검증한 출처','source_url':'https://example.com','facts_checked':True,'rights_checked':True}
    assert client.put('/api/posts/'+p['id'],json=body).status_code==200
    stored=client.get('/api/posts/'+p['id']).json()
    assert stored['slides'][0]['title']=='변경한 제목' and stored['facts_checked']

def test_invalid_input_and_missing_keys(client):
    assert client.post('/api/generate',json={'text':'너무 짧음','count':11}).status_code==422
    assert client.post('/api/generate',json={'text':'검증할 원고입니다.','engine':'ai'}).status_code==400
    assert client.get('/api/discover').status_code==400
    assert client.post('/api/generate',json={'text':'사진으로 생성할 원고','image_mode':'upload','asset_id':'../../secret'}).status_code==400

def test_no_private_fetch(client):
    for url in ['http://127.0.0.1:8765','http://127.0.0.1/','file:///etc/passwd','http://169.254.169.254/']:
        assert client.post('/api/import',json={'url':url}).status_code==400

def test_cross_origin_blocked(client):
    r=client.post('/api/generate',json={'text':'다른 사이트 요청'},headers={'Origin':'https://evil.example'})
    assert r.status_code==403

def test_image_upload(client):
    buf=io.BytesIO();Image.new('RGB',(400,300),'blue').save(buf,format='PNG')
    asset=client.post('/api/assets/upload',files={'file':('test.png',buf.getvalue(),'image/png')}).json()
    p=generate(client,image_mode='upload',asset_id=asset['asset_id'])
    assert p['image_credit'] and '이미지:' in p['caption']

def configure_instagram(monkeypatch):
    for k,v in {'INSTAGRAM_ACCESS_TOKEN':'test-only','INSTAGRAM_USER_ID':'123','PUBLIC_MEDIA_BASE_URL':'https://example.com/media'}.items():monkeypatch.setenv(k,v)

def test_schedule_checks_cancel_and_edit_lock(client,monkeypatch):
    p=generate(client);at=(datetime.now(st.KST)+timedelta(hours=1)).isoformat()
    assert client.post(f'/api/posts/{p["id"]}/schedule',json={'at':at}).status_code==400
    configure_instagram(monkeypatch)
    assert client.post(f'/api/posts/{p["id"]}/schedule',json={'at':at}).status_code==400
    p.update(facts_checked=True,rights_checked=True);st.save(p)
    assert client.post(f'/api/posts/{p["id"]}/schedule',json={'at':at}).status_code==200
    edit={'slides':p['slides'],'caption':p['caption'],'source_name':'x','source_url':''}
    assert client.put('/api/posts/'+p['id'],json=edit).status_code==409
    assert client.post(f'/api/posts/{p["id"]}/cancel').json()['status']=='draft'

def test_daily_cap(client,monkeypatch):
    configure_instagram(monkeypatch);p=generate(client)
    at=(datetime.now(st.KST)+timedelta(hours=1)).isoformat()
    for n in range(10):st.save({**p,'id':f'cap-{n}','status':'scheduled','scheduled_at':at})
    p.update(facts_checked=True,rights_checked=True);st.save(p)
    r=client.post(f'/api/posts/{p["id"]}/schedule',json={'at':at})
    assert r.status_code==400 and '10개' in r.json()['detail']

@pytest.mark.parametrize('fail',[False,True])
def test_publish_result_uncertainty(client,monkeypatch,fail):
    configure_instagram(monkeypatch);p=generate(client,count=2)
    p.update(facts_checked=True,rights_checked=True,status='scheduled');st.save(p)
    calls=[]
    async def fake(method,url,**kwargs):
        calls.append(url)
        if url.endswith('media_publish'):
            if fail:raise providers.ProviderError('connection lost')
            return {'id':'published-id'}
        if method=='GET':return {'status_code':'FINISHED'}
        return {'id':'container-'+str(len(calls))}
    monkeypatch.setattr(publishing,'api',fake)
    monkeypatch.setattr(publishing,'public_url',lambda url:url)
    if fail:
        with pytest.raises(providers.ProviderError):asyncio.run(publishing.publish(p))
        assert st.get(p['id'])['status']=='needs_check'
    else:
        asyncio.run(publishing.publish(p));assert st.get(p['id'])['instagram_id']=='published-id'
    assert sum(u.endswith('media_publish') for u in calls)==1

def test_daily_dedupe(client,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    st.set_setting('daily',{'daily_target':10,'categories':['AI'],'hour':8,'enabled':False})
    async def discover(category):return {'items':[{'title':'검증된 기사','url':'https://example.com/article','score':80,'category':'AI'}]}
    async def extract(url):return {'text':'기사가 설명하는 사실입니다.','source_name':'test','source_url':url}
    async def ai(req):return providers.local_copy(req)
    monkeypatch.setattr(providers,'discover',discover);monkeypatch.setattr(providers,'extract',extract);monkeypatch.setattr(providers,'ai_copy',ai)
    r=client.post('/api/daily/run');assert r.status_code==200 and len(r.json()['created'])==1
    assert client.post('/api/daily/run').status_code==400
