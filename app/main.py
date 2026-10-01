import asyncio
import io
import json
import os
import re
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError
from . import storage as st
from .models import Generate, Edit, Slide, Schedule, DailySchedule, UrlInput, AssetUrl
from . import providers as p
from .render import render
from .publishing import publish
from .models import VideoFrames, FrameCleanup
from .video_frames import youtube_frames
from . import quality
from .frame_cleanup import clean_frames

load_dotenv(st.ROOT/'.env')
st.init()
LOCK=asyncio.Lock()
DAILY_LOCK=asyncio.Lock()
VIDEO_LOCK=asyncio.Lock()

def lookup(pid):
    obj=st.get(pid)
    if not obj:raise HTTPException(404,'콘텐츠를 찾지 못했습니다.')
    return obj

def writable(post):
    if post['status'] in ('scheduled','publishing','published','needs_check'):
        raise HTTPException(409,'예약을 취소한 뒤 수정하세요. 게시 중·완료·확인 필요 콘텐츠는 수정할 수 없습니다.')

def asset_save(data,credit):
    try:
        im=Image.open(io.BytesIO(data))
        if im.width*im.height>25_000_000:raise p.ProviderError('이미지는 2,500만 픽셀 이하만 지원합니다.')
        im.load()
        im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((2048,2048))
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as e:raise p.ProviderError('읽을 수 있는 이미지 파일이 아닙니다.') from e
    aid=uuid.uuid4().hex;im.save(st.ASSETS/(aid+'.jpg'),quality=92)
    (st.ASSETS/(aid+'.json')).write_text(json.dumps({'credit':credit},ensure_ascii=False),encoding='utf-8')
    return {'asset_id':aid,'url':'/assets/'+aid+'.jpg','credit':credit}

async def create(req):
    if req.image_mode=='video' and req.video_asset_ids:
        for aid in req.video_asset_ids:
            if not re.fullmatch('[a-f0-9]{32}',aid) or not (st.ASSETS/(aid+'.jpg')).is_file():
                raise p.ProviderError('영상 장면을 다시 캡처하세요.')
        req.asset_id=''
    elif req.image_mode in ('upload','web','video'):
        if not re.fullmatch('[a-f0-9]{32}',req.asset_id) or not (st.ASSETS/(req.asset_id+'.jpg')).is_file():raise p.ProviderError('사용할 사진 또는 영상 캡처를 먼저 선택하세요.')
    if req.image_mode in ('design','ai'):req.asset_id=''
    copy_req=req
    auto_video=req.count==0 and req.image_mode=='video' and bool(req.video_asset_ids)
    if auto_video and len(req.video_asset_ids)==1:
        copy_req=req.model_copy(update={'count':1})
    content=await p.ai_copy(copy_req) if req.engine=='ai' else p.local_copy(copy_req)
    if auto_video and len(content['slides'])>len(req.video_asset_ids):
        # Recompose from the original source; never drop trailing facts or CTA.
        copy_req=req.model_copy(update={'count':len(req.video_asset_ids)})
        content=await p.ai_copy(copy_req) if req.engine=='ai' else p.local_copy(copy_req)
    slides=[Slide(**s).model_dump() for s in content['slides']]
    if req.image_mode=='video' and req.video_asset_ids:
        if len(req.video_asset_ids)<len(slides):raise p.ProviderError('카드 장수만큼 장면을 다시 캡처하세요.')
        for i,slide in enumerate(slides):
            aid=req.video_asset_ids[min(len(req.video_asset_ids)-1,int((i+.5)*len(req.video_asset_ids)/len(slides)))]
            slide['asset_id']=aid
            slide['image_credit']=json.loads((st.ASSETS/(aid+'.json')).read_text(encoding='utf-8'))['credit']
    if req.image_mode=='ai':
        for i,slide in enumerate(slides):
            prompt=(f'Card {i+1} of {len(slides)}. Create a distinct scene for THIS card. '
                    f'Overall topic: {slides[0]["title"]}\n'
                    f'This card title: {slide["title"]}\nThis card content: {slide["body"]}\n'
                    'Use one concrete visual metaphor matching this content, consistent editorial photography style. '
                    'Vary scene and composition across cards. No lettering, logos or fabricated news photographs.')
            asset=asset_save(await p.ai_image(prompt),'AI 생성 이미지')
            slide['asset_id']=asset['asset_id'];slide['image_credit']='AI 생성 이미지'
    credit=''
    if req.asset_id:credit=json.loads((st.ASSETS/(req.asset_id+'.json')).read_text(encoding='utf-8'))['credit']
    if req.image_mode=='ai':credit='AI 생성 이미지 (카드별 생성)'
    if req.image_mode=='video' and req.video_asset_ids:credit='영상 구간별 자동 캡처 — 장면별 출처는 편집 정보에 기록. 이용 권한 확인 필요'
    caption=content['caption']
    if credit:caption=caption[:max(0,2193-len(credit))]+'\n이미지: '+credit
    post={**req.model_dump(),**content,'caption':caption,'slides':slides,'id':uuid.uuid4().hex,'created_at':st.now(),'status':'draft','facts_checked':False,'rights_checked':False,'image_credit':credit,'scheduled_at':None}
    if auto_video:post['generation_note']=f'원고와 사용 가능한 사진에 맞춰 {len(slides)}장으로 자동 구성했습니다.'
    post['images']=await asyncio.to_thread(render,post)
    st.save(post);st.log('카드 생성: '+post['slides'][0]['title'])
    digest=quality.fingerprint(post)
    try:result=await quality.evaluate(post)
    except (ValueError,OSError):result={'status':'error','message':'자동 평가를 완료하지 못했습니다. 초안은 저장했으며, 재평가 전 게시가 제한됩니다.'}
    async with LOCK:
        current=st.get(post['id'])
        if quality.fingerprint(current)==digest:current['quality']=result;st.save(current)
    return current

async def daily_run():
    if DAILY_LOCK.locked():raise p.ProviderError('일일 생성 작업이 진행 중입니다.')
    async with DAILY_LOCK:
        p.require('OPENAI_API_KEY')
        day=datetime.now(st.KST).date().isoformat()
        with st.db() as c:
            inserted=c.execute('INSERT OR IGNORE INTO runs VALUES (?,?,?)',(day,'running','실행 중')).rowcount
        if not inserted:raise p.ProviderError('오늘의 일일 생성 작업은 이미 실행되었습니다. 실행 로그를 확인하세요.')
        config=st.setting('daily',st.DEFAULT_SCHEDULE);made=[];errors=[]
        used={x.get('source_url') for x in st.posts()}
        try:
            pools=[]
            for category in config['categories']:
                try:pools.append((await p.discover(category))['items'])
                except Exception as e:errors.append(str(e))
            candidates=[]
            # Round-robin avoids one subject occupying all daily slots.
            for i in range(20):
                for pool in pools:
                    if i<len(pool):candidates.append(pool[i])
            for item in candidates:
                if len(made)>=config['daily_target']:break
                if item['url'] in used or item['score']<70:continue
                used.add(item['url'])
                try:
                    source=await p.extract(item['url'])
                    if 'youtube.com' in item['url']:continue # description is not a verified transcript
                    req=Generate(text=source['text'],source_name=source['source_name'],source_url=source['source_url'],category=item['category'],engine='ai')
                    made.append((await create(req))['id'])
                except Exception as e:errors.append(str(e))
            msg=f'{len(made)}/{config["daily_target"]}개 초안 생성. 적합한 원문 부족 시 억지로 채우지 않습니다.'
            if errors:msg+=' '+errors[0]
            with st.db() as c:c.execute('UPDATE runs SET status=?,message=? WHERE day=?',('complete',msg,day))
            st.log(msg);return {'created':made,'message':msg}
        except Exception:
            with st.db() as c:c.execute('UPDATE runs SET status=?,message=? WHERE day=?',('failed','일일 생성 실패. 로그 및 연결 설정 확인.',day))
            raise

async def tick():
    config=st.setting('daily',st.DEFAULT_SCHEDULE)
    now=datetime.now(st.KST)
    if config['enabled'] and now.hour>=config['hour']:
        with st.db() as c:exists=c.execute('SELECT 1 FROM runs WHERE day=?',(now.date().isoformat(),)).fetchone()
        if not exists:
            try:await daily_run()
            except Exception as e:st.log(str(e))
    async with LOCK:
        for post in st.posts():
            if post['status']!='scheduled' or datetime.fromisoformat(post['scheduled_at'])>now:continue
            published=sum(x['status']=='published' and x.get('published_at','')[:10]==now.date().isoformat() for x in st.posts())
            if published>=10:break
            try:await publish(post)
            except Exception as e:
                current=st.get(post['id'])
                if current['status']!='needs_check':current['status']='failed';current['error']=str(e);st.save(current)
                st.log('게시 실패/확인 필요: '+post['id'])

async def worker():
    while True:
        try:await tick()
        except Exception as e:st.log('작업 오류: '+str(e)[:200])
        await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app):
    # Interrupted publishing must be inspected, never blindly retried.
    for post in st.posts():
        if post['status']=='publishing':post['status']='needs_check';post['error']='앱이 게시 중 종료되었습니다. 실제 게시 여부를 확인하세요.';st.save(post)
    task=asyncio.create_task(worker())
    yield
    task.cancel()
    try:await task
    except asyncio.CancelledError:pass

app=FastAPI(title='Issue Studio',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

@app.middleware('http')
async def local_origin(request:Request,call_next):
    origin=request.headers.get('origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765'):
        return JSONResponse({'detail':'다른 사이트에서 보낸 요청은 허용하지 않습니다.'},status_code=403)
    return await call_next(request)

@app.exception_handler(p.ProviderError)
async def provider_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)

@app.exception_handler(ValueError)
async def value_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)

@app.get('/api/status')
def status():
    keys={'ai':bool(os.getenv('OPENAI_API_KEY')),'news':bool(os.getenv('NAVER_CLIENT_ID') and os.getenv('NAVER_CLIENT_SECRET')),'youtube':bool(os.getenv('YOUTUBE_API_KEY')),'instagram':all(os.getenv(n) for n in ['INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','PUBLIC_MEDIA_BASE_URL'])}
    return {'connections':keys,'daily':st.setting('daily',st.DEFAULT_SCHEDULE),'time':st.now(),'note':'설정 존재 여부입니다. 실제 인증·게시 성공을 의미하지 않습니다.'}

@app.get('/api/posts')
def list_posts():return st.posts()

@app.get('/api/posts/{pid}')
def read_post(pid:str):return lookup(pid)

@app.post('/api/generate')
async def generate(req:Generate):return await create(req)

@app.put('/api/posts/{pid}')
async def edit(pid:str,req:Edit):
    async with LOCK:
        post=lookup(pid);writable(post)
        old_slides=post['slides']
        updated=[]
        for i,item in enumerate(req.slides):
            slide=item.model_dump()
            aid=item.asset_id or (old_slides[i].get('asset_id') if i<len(old_slides) else None) or post.get('asset_id')
            if aid:
                if not re.fullmatch('[a-f0-9]{32}',aid) or not (st.ASSETS/(aid+'.jpg')).is_file():
                    raise p.ProviderError('사용할 카드 사진을 다시 선택하세요.')
                slide['asset_id']=aid
                slide['image_credit']=json.loads((st.ASSETS/(aid+'.json')).read_text(encoding='utf-8'))['credit']
            updated.append(slide)
        post.update(req.model_dump());post['slides']=[s.model_dump() for s in req.slides]
        post['slides']=updated
        credits=list(dict.fromkeys(s.get('image_credit','') for s in updated if s.get('image_credit')))
        post['image_credit']=' / '.join(credits)
        if credits and post['image_credit'] not in post['caption']:
            suffix='\n이미지: '+post['image_credit']
            post['caption']=post['caption'][:max(0,2200-len(suffix))]+suffix
        if any((s.get('asset_id') or post.get('asset_id')) != ((old_slides[i].get('asset_id') or post.get('asset_id')) if i<len(old_slides) else None) for i,s in enumerate(updated)):
            post['rights_checked']=False
        post['images']=await asyncio.to_thread(render,post)
        if (post.get('quality') or {}).get('fingerprint')!=quality.fingerprint(post):
            post['quality']={'status':'stale','message':'내용 또는 사진이 변경되었습니다. 다시 평가하세요.'}
        st.save(post)
        return post

@app.post('/api/posts/{pid}/evaluate')
async def evaluate_post(pid:str):
    post=lookup(pid);writable(post)
    digest=quality.fingerprint(post)
    try:result=await quality.evaluate(post)
    except (ValueError,OSError):
        async with LOCK:
            current=lookup(pid)
            if quality.fingerprint(current)==digest:
                current['quality']={'status':'error','message':'평가 실패. 다시 평가하기 전에는 게시할 수 없습니다.'};st.save(current)
        raise p.ProviderError('평가를 완료하지 못했습니다. 연결 상태를 확인하고 다시 평가하세요.')
    async with LOCK:
        current=lookup(pid);writable(current)
        if quality.fingerprint(current)!=result['fingerprint']:
            raise HTTPException(409,'평가 중 내용이 바뀌었습니다. 다시 평가하세요.')
        current['quality']=result;st.save(current)
        return current

@app.post('/api/posts/{pid}/schedule')
async def schedule(pid:str,req:Schedule):
    async with LOCK:
        post=lookup(pid);writable(post)
        p.require('INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','PUBLIC_MEDIA_BASE_URL')
        if not post.get('facts_checked') or not post.get('rights_checked'):raise p.ProviderError('사실관계·이미지 사용 권한을 확인하고 저장하세요.')
        quality.ensure_passed(post)
        if post['ratio']=='9:16':raise p.ProviderError('피드 예약은 4:5 또는 1:1만 지원합니다.')
        at=datetime.fromisoformat(req.at)
        if at.tzinfo is None:at=at.replace(tzinfo=st.KST)
        at=at.astimezone(st.KST)
        if at<=datetime.now(st.KST):raise p.ProviderError('미래 시간을 선택하세요.')
        count=sum(x['id']!=pid and x['status'] in ('scheduled','published','publishing','needs_check') and (x.get('scheduled_at') or x.get('published_at',''))[:10]==at.date().isoformat() for x in st.posts())
        if count>=10:raise p.ProviderError('하루 예약 한도는 10개입니다.')
        post.update(status='scheduled',scheduled_at=at.isoformat(),error='');st.save(post);return post

@app.post('/api/posts/{pid}/cancel')
async def cancel(pid:str):
    async with LOCK:
        post=lookup(pid)
        if post['status'] not in ('scheduled','failed'):raise HTTPException(409,'취소 가능한 예약이 아닙니다.')
        post.update(status='draft',scheduled_at=None);st.save(post);return post

@app.get('/api/posts/{pid}/download')
def download(pid:str):
    post=lookup(pid);buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for i in range(len(post['slides'])):z.write(st.MEDIA/pid/f'{i+1:02}.png',f'{i+1:02}.png')
        z.writestr('caption.txt',post['caption']);z.writestr('content.json',json.dumps(post,ensure_ascii=False,indent=2))
    buf.seek(0)
    return StreamingResponse(buf,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="issue-{pid[:8]}.zip"'})

@app.post('/api/import')
async def import_url(req:UrlInput):return await p.extract(req.url)

@app.get('/api/discover')
async def discover(category:str='AI'):
    if category not in ['뉴스','이슈','연예','경제','AI']:raise HTTPException(400,'주제를 확인하세요.')
    return await p.discover(category)

@app.get('/api/images/search')
async def image_search(q:str):return await p.web_images(q[:100])

@app.post('/api/assets/upload')
async def upload(file:UploadFile=File(...)):
    data=await file.read(15_000_001)
    if len(data)>15_000_000:raise HTTPException(413,'이미지는 15MB 이하만 지원합니다.')
    return asset_save(data,'직접 업로드 — 사용 권한 확인 필요')

@app.post('/api/video/frames')
async def video_frames(req:VideoFrames):
    p.require('OPENAI_API_KEY')
    if VIDEO_LOCK.locked():raise HTTPException(409,'영상 캡처가 진행 중입니다. 완료 후 다시 시도하세요.')
    async with VIDEO_LOCK:
        frames=await asyncio.to_thread(youtube_frames,req.url,20 if req.count==0 else min(20,req.count*3),st.DATA)
        frames=await clean_frames(frames,req.count)
        assets=[{**asset_save(data,f'영상 캡처 {at:.1f}초 / 방송 그래픽 크롭 / {req.url} / 이용 권한 확인 필요'),'at':at} for at,data in frames]
        return {'assets':assets,'note':'영상 구간을 나눠 자동 캡처했습니다. 문장 의미 분석이나 자막 추출은 아니므로 장면과 문안의 관계를 검토하세요.'}

@app.post('/api/video/clean-frames')
async def clean_uploaded_frames(req:FrameCleanup):
    if VIDEO_LOCK.locked():raise HTTPException(409,'영상 캡처가 진행 중입니다. 완료 후 다시 시도하세요.')
    frames=[]
    for i,aid in enumerate(req.asset_ids):
        if not re.fullmatch('[a-f0-9]{32}',aid) or not (st.ASSETS/(aid+'.jpg')).is_file():
            raise p.ProviderError('영상 캡처를 다시 선택하세요.')
        frames.append((i,(st.ASSETS/(aid+'.jpg')).read_bytes()))
    async with VIDEO_LOCK:
        cleaned=await clean_frames(frames,req.count)
    return {'assets':[asset_save(data,'보유 영상 캡처 / 방송 그래픽 크롭 / 이용 권한 확인 필요') for _,data in cleaned]}

@app.post('/api/assets/web')
async def web_asset(req:AssetUrl):
    data,ctype,_=await p.fetch_public(req.url,15_000_000)
    if not ctype.startswith('image/'):raise p.ProviderError('이미지 URL이 아닙니다.')
    return asset_save(data,req.credit)

@app.put('/api/daily')
def daily_settings(req:DailySchedule):
    if req.enabled:p.require('OPENAI_API_KEY','NAVER_CLIENT_ID','NAVER_CLIENT_SECRET')
    st.set_setting('daily',req.model_dump());return req

@app.post('/api/daily/run')
async def run_daily():return await daily_run()

@app.get('/api/events')
def events():
    with st.db() as c:
        return {'events':[dict(x) for x in c.execute('SELECT * FROM events ORDER BY id DESC LIMIT 40')], 'runs':[dict(x) for x in c.execute('SELECT * FROM runs ORDER BY day DESC LIMIT 10')]}

@app.get('/')
def index():return FileResponse(st.ROOT/'static'/'index.html')

@app.get('/presentation')
def presentation():return FileResponse(st.ROOT/'Presentation'/'index.html')

app.mount('/static',StaticFiles(directory=st.ROOT/'static',check_dir=False),name='static')
app.mount('/media',StaticFiles(directory=st.MEDIA),name='media')
app.mount('/assets',StaticFiles(directory=st.ASSETS),name='assets')
