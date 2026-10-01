import asyncio
import io
import zipfile
from datetime import datetime,timedelta
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app import main,storage as st,providers,publishing,render,quality
REAL_EVALUATE=quality.evaluate

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(st,'DATA',tmp_path)
    monkeypatch.setattr(st,'MEDIA',tmp_path/'media')
    monkeypatch.setattr(st,'ASSETS',tmp_path/'assets')
    monkeypatch.setattr(render,'MEDIA',tmp_path/'media')
    monkeypatch.setattr(render,'ASSETS',tmp_path/'assets')
    for key in ['OPENAI_API_KEY','NAVER_CLIENT_ID','NAVER_CLIENT_SECRET','YOUTUBE_API_KEY','INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','PUBLIC_MEDIA_BASE_URL']:
        monkeypatch.delenv(key,raising=False)
    async def no_review(post):raise providers.ProviderError('test review unavailable')
    monkeypatch.setattr(quality,'evaluate',no_review)
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

def test_ai_images_follow_each_slide_and_survive_edit(client,monkeypatch):
    prompts=[]
    async def fake_image(prompt):
        prompts.append(prompt)
        buf=io.BytesIO();Image.new('RGB',(200,200),['red','green','blue'][len(prompts)-1]).save(buf,format='PNG')
        return buf.getvalue()
    monkeypatch.setattr(providers,'ai_image',fake_image)
    p=generate(client,image_mode='ai')
    ids=[s['asset_id'] for s in p['slides']]
    assert len(set(ids))==3 and len(prompts)==3
    for i,s in enumerate(p['slides']):
        assert s['title'] in prompts[i] and s['body'] in prompts[i]
    colors=[Image.open(st.MEDIA/p['id']/f'{i+1:02}.png').getpixel((500,180)) for i in range(3)]
    assert len(set(colors))==3
    body={'slides':[{'title':s['title'],'body':s['body']} for s in p['slides']],
          'caption':p['caption'],'source_name':p['source_name'],'source_url':''}
    r=client.put('/api/posts/'+p['id'],json=body)
    assert r.status_code==200
    assert [s['asset_id'] for s in r.json()['slides']]==ids

def test_replace_one_photo_preserves_others_and_resets_rights(client):
    p=generate(client)
    buf=io.BytesIO();Image.new('RGB',(200,200),'orange').save(buf,format='PNG')
    asset=client.post('/api/assets/upload',files={'file':('card.png',buf.getvalue(),'image/png')}).json()
    body={'slides':p['slides'],'caption':p['caption'],'source_name':p['source_name'],
          'source_url':'','facts_checked':True,'rights_checked':True}
    body['slides'][1]['asset_id']=asset['asset_id']
    r=client.put('/api/posts/'+p['id'],json=body)
    assert r.status_code==200
    slides=r.json()['slides']
    assert slides[1]['asset_id']==asset['asset_id']
    assert not slides[0]['asset_id'] and not slides[2]['asset_id']
    assert not r.json()['rights_checked']
    body['slides'][1]['asset_id']='../private'
    assert client.put('/api/posts/'+p['id'],json=body).status_code==422

def test_video_frames_to_individual_cards(client,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    def fake_capture(url,count,data):
        out=[]
        for i in range(count):
            b=io.BytesIO();Image.new('RGB',(100,100),['red','blue','green'][i%3]).save(b,format='PNG')
            out.append((i*10,b.getvalue()))
        return out
    async def fake_cleanup(frames,count):return frames[:count]
    monkeypatch.setattr(main,'clean_frames',fake_cleanup)
    monkeypatch.setattr(main,'youtube_frames',fake_capture)
    response=client.post('/api/video/frames',json={'url':'https://youtu.be/NHXFgBSAwS8','count':3})
    assert response.status_code==200
    ids=[a['asset_id'] for a in response.json()['assets']]
    p=generate(client,image_mode='video',video_asset_ids=ids)
    assert [s['asset_id'] for s in p['slides']]==ids
    assert '영상 캡처' in p['slides'][1]['image_credit']
    bad=client.post('/api/generate',json={'text':'영상 캡처 테스트입니다.','image_mode':'video','video_asset_ids':['../../bad']})
    assert bad.status_code==400

def test_video_url_and_timestamps():
    from app.video_frames import youtube_url,capture_times
    assert youtube_url('https://youtu.be/NHXFgBSAwS8?t=5')=='https://www.youtube.com/watch?v=NHXFgBSAwS8'
    assert capture_times(100,4)==[12.5,37.5,62.5,87.5]
    for url in ['http://127.0.0.1/video','https://youtube.com.evil.com/watch?v=NHXFgBSAwS8','file:///video','https://user@youtube.com/watch?v=NHXFgBSAwS8']:
        with pytest.raises(ValueError):youtube_url(url)
    with pytest.raises(ValueError):capture_times(float('inf'),3)

def approve_quality(p):
    p['quality']={'status':'passed','version':quality.VERSION,'fingerprint':quality.fingerprint(p),
                  'cards':[{'card':i+1,'hook':25,'sync':40,'grounding':25,'cta':10,'critical':False,'reason':'test','fix':'test'} for i in range(len(p['slides']))]}
    st.save(p)


def configure_instagram(monkeypatch):
    for k,v in {'INSTAGRAM_ACCESS_TOKEN':'test-only','INSTAGRAM_USER_ID':'123','PUBLIC_MEDIA_BASE_URL':'https://example.com/media'}.items():monkeypatch.setenv(k,v)

@pytest.mark.parametrize('problem',['missing','low_sync','critical','changed_image','changed_text','bad_schema'])
def test_quality_gate_blocks_schedule_and_direct_publish(client,monkeypatch,problem):
    configure_instagram(monkeypatch);p=generate(client)
    p.update(facts_checked=True,rights_checked=True);approve_quality(p)
    if problem=='missing':p.pop('quality')
    elif problem=='low_sync':p['quality']['cards'][0]['sync']=29
    elif problem=='critical':p['quality']['cards'][0]['critical']=True
    elif problem=='changed_image':(st.MEDIA/p['id']/'01.jpg').write_bytes(b'changed')
    elif problem=='changed_text':p['slides'][0]['title']='평가 후 달라진 제목'
    elif problem=='bad_schema':p['quality']['cards'][0]['sync']=100
    st.save(p)
    at=(datetime.now(st.KST)+timedelta(hours=1)).isoformat()
    r=client.post(f'/api/posts/{p["id"]}/schedule',json={'at':at})
    assert r.status_code==400 and '자가평가' in r.json()['detail']
    async def forbidden(*args,**kwargs):pytest.fail('Blocked review must not call Meta')
    monkeypatch.setattr(publishing,'api',forbidden)
    with pytest.raises(providers.ProviderError):asyncio.run(publishing.publish(p))

def test_review_failure_invalidates_previous_pass(client):
    p=generate(client);approve_quality(p)
    assert client.post(f'/api/posts/{p["id"]}/evaluate').status_code==400
    assert st.get(p['id'])['quality']['status']=='error'

def test_edit_invalidates_review_but_checkbox_save_preserves_it(client):
    p=generate(client);approve_quality(p)
    body={'slides':p['slides'],'caption':p['caption'],'source_name':p['source_name'],'source_url':p['source_url'],'facts_checked':True,'rights_checked':True}
    r=client.put('/api/posts/'+p['id'],json=body)
    assert r.status_code==200 and r.json()['quality']['status']=='passed'
    body['slides'][0]['title']='수정한 제목'
    r=client.put('/api/posts/'+p['id'],json=body)
    assert r.json()['quality']['status']=='stale'

def test_review_uses_actual_images_and_rejects_incomplete_response(client,monkeypatch):
    import json
    p=generate(client);approve_quality(p)
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    cards=p['quality']['cards']
    async def fake_api(*args,**kwargs):
        content=kwargs['json']['input'][0]['content']
        images=[c for c in content if c['type']=='input_image']
        assert len(images)==len(p['slides'])
        assert all(c['image_url'].startswith('data:image/jpeg;base64,') for c in images)
        return {'output':[{'content':[{'type':'output_text','text':json.dumps({'cards':cards})}]}]}
    monkeypatch.setattr(providers,'api',fake_api)
    assert asyncio.run(REAL_EVALUATE(p))['status']=='passed'
    cards.pop()
    with pytest.raises(providers.ProviderError):asyncio.run(REAL_EVALUATE(p))

def test_schedule_checks_cancel_and_edit_lock(client,monkeypatch):
    p=generate(client);at=(datetime.now(st.KST)+timedelta(hours=1)).isoformat()
    assert client.post(f'/api/posts/{p["id"]}/schedule',json={'at':at}).status_code==400
    configure_instagram(monkeypatch)
    assert client.post(f'/api/posts/{p["id"]}/schedule',json={'at':at}).status_code==400
    p.update(facts_checked=True,rights_checked=True);approve_quality(p)
    assert client.post(f'/api/posts/{p["id"]}/schedule',json={'at':at}).status_code==200
    edit={'slides':p['slides'],'caption':p['caption'],'source_name':'x','source_url':''}
    assert client.put('/api/posts/'+p['id'],json=edit).status_code==409
    assert client.post(f'/api/posts/{p["id"]}/cancel').json()['status']=='draft'

def test_daily_cap(client,monkeypatch):
    configure_instagram(monkeypatch);p=generate(client)
    at=(datetime.now(st.KST)+timedelta(hours=1)).isoformat()
    for n in range(10):st.save({**p,'id':f'cap-{n}','status':'scheduled','scheduled_at':at})
    p.update(facts_checked=True,rights_checked=True);approve_quality(p)
    r=client.post(f'/api/posts/{p["id"]}/schedule',json={'at':at})
    assert r.status_code==400 and '10개' in r.json()['detail']

@pytest.mark.parametrize('fail',[False,True])
def test_publish_result_uncertainty(client,monkeypatch,fail):
    configure_instagram(monkeypatch);p=generate(client,count=2)
    p.update(facts_checked=True,rights_checked=True,status='scheduled');approve_quality(p)
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


def test_uploaded_frames_cleaned_to_new_assets(client,monkeypatch):
    b=io.BytesIO();Image.new('RGB',(640,480),'blue').save(b,format='JPEG')
    original=main.asset_save(b.getvalue(),'original source')
    async def fake(frames,count):
        assert count==1 and len(frames)==1
        return frames
    monkeypatch.setattr(main,'clean_frames',fake)
    response=client.post('/api/video/clean-frames',json={'asset_ids':[original['asset_id']],'count':1})
    assert response.status_code==200
    assert response.json()['assets'][0]['asset_id']!=original['asset_id']
    assert (st.ASSETS/(original['asset_id']+'.jpg')).exists()
    assert client.post('/api/video/clean-frames',json={'asset_ids':['../../bad'],'count':1}).status_code==400
