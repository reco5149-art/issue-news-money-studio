import asyncio
import io
import json
import os
import re
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
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
from .video_sources import is_video_url, extract_video
from . import quality
from .frame_cleanup import clean_frames
from .copy_policy import finish_caption, caption_urls
from . import cadence
from . import autopilot, source_policy, operations
from .photo_finish import finish as finish_photo
from .models import PostingCadence, BatchReservation
from .models import PublicationPolicy
from . import publication_policy

load_dotenv(st.ROOT/'.env')
st.init()
LOCK=asyncio.Lock()
DAILY_LOCK=asyncio.Lock()
VIDEO_LOCK=asyncio.Lock()
IMPORT_LOCK=asyncio.Lock()
PRODUCTION_TASK=None

def lookup(pid):
    obj=st.get(pid)
    if not obj:raise HTTPException(404,'콘텐츠를 찾지 못했습니다.')
    return obj

def writable(post):
    if post.get("trashed_at"):raise HTTPException(409,"휴지통에서 복원한 후 수정·예약하세요.")
    if post['status'] in ('scheduled','publishing','published','needs_check'):
        raise HTTPException(409,'예약을 취소한 뒤 수정하세요. 게시 중·완료·확인 필요 콘텐츠는 수정할 수 없습니다.')

def asset_save(data,credit):
    try:
        im=Image.open(io.BytesIO(data))
        if im.width*im.height>25_000_000:raise p.ProviderError('이미지는 2,500만 픽셀 이하만 지원합니다.')
        im.load()
        im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((3840,3840))
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as e:raise p.ProviderError('읽을 수 있는 이미지 파일이 아닙니다.') from e
    aid=uuid.uuid4().hex;im.save(st.ASSETS/(aid+'.jpg'),quality=92)
    (st.ASSETS/(aid+'.json')).write_text(json.dumps({'credit':credit},ensure_ascii=False),encoding='utf-8')
    return {'asset_id':aid,'url':'/assets/'+aid+'.jpg','credit':credit}

async def create(req,automation_day=None):
    if automation_day and (req.image_mode!='video' or not req.video_asset_ids):
        raise p.ProviderError('자동 제작은 유튜브 영상 캡처만 사용합니다. 캡처를 확보한 후 생성하세요.')
    if req.image_mode=='video' and req.video_asset_ids:
        for aid in req.video_asset_ids:
            if not re.fullmatch('[a-f0-9]{32}',aid) or not (st.ASSETS/(aid+'.jpg')).is_file():
                raise p.ProviderError('영상 장면을 다시 캡처하세요.')
        req.asset_id=''
    elif req.image_mode in ('upload','video') or (req.image_mode=='web' and req.asset_id):
        if not re.fullmatch('[a-f0-9]{32}',req.asset_id) or not (st.ASSETS/(req.asset_id+'.jpg')).is_file():
            messages={'web':'웹 검색 결과에서 사용할 사진의 선택 버튼을 누른 후 생성하세요.',
                      'upload':'사용할 사진 파일을 업로드한 후 생성하세요.',
                      'video':'사용할 영상 장면을 먼저 캡처하세요.'}
            raise p.ProviderError(messages[req.image_mode])
    if req.image_mode in ('design','ai'):req.asset_id=''
    kie=req.image_mode=='ai' and req.ai_image_provider=='kie'
    if kie:p.require('KIE_API_KEY') # fail before paid copy generation
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
    web_credits=[];web_notes=[]
    if req.image_mode=='web' and not req.asset_id:
        from .web_art import attach
        web_credits,web_notes=await attach(slides,asset_save)
    ai_label=f'AI 생성 이미지 (KIE AI · {os.getenv("KIE_IMAGE_MODEL","nano-banana-2")})' if kie else 'AI 생성 이미지'
    if req.image_mode=='ai':
        prompts=[(f'Card {i+1} of {len(slides)}. Create a distinct scene for THIS card. '
                  f'Visual scene only: {content["slides"][i].get("visual_brief") or (slide["title"] + ": " + slide["body"] + ". Interpret the topic visually; never draw these words.")}\n'
                  'Premium editorial still life: a single meaningful object or environment directly tied to this card. '
                  'Natural directional light, tactile materials, restrained palette, uncluttered background. '
                  'No generic handshake, pointing person, random face, cartoon, collage or stock-photo grin. '
                  'Never reconstruct real named people, medals, tears, protests or unverified events. '
                  'For real people and news incidents, illustrate relevant objects or locations as a clearly conceptual image. '
                  'Keep the complete subject within the central 65 percent, with generous crop-safe margins. '
                  'Vary scene and composition across cards. No lettering, logos or fabricated news photographs.')
                 for i,slide in enumerate(slides)]
        # KIE tasks are asynchronous jobs; run a few at once. Stop queuing new jobs after a failure.
        gate=asyncio.Semaphore(3 if kie else 1)
        async def one(prompt):
            async with gate:return await (p.kie_image(prompt,req.ratio) if kie else p.ai_image(prompt))
        jobs=[asyncio.create_task(one(x)) for x in prompts]
        try:images=await asyncio.gather(*jobs)
        except BaseException:
            for job in jobs:job.cancel()
            await asyncio.gather(*jobs,return_exceptions=True)
            raise
        for slide,data in zip(slides,images):
            asset=asset_save(data,ai_label)
            slide['asset_id']=asset['asset_id'];slide['image_credit']=ai_label
    credit=''
    if req.asset_id:credit=json.loads((st.ASSETS/(req.asset_id+'.json')).read_text(encoding='utf-8'))['credit']
    if req.image_mode=='ai':credit=ai_label+' · 카드별 생성'
    if req.image_mode=='video' and req.video_asset_ids:credit='영상 구간별 자동 캡처 — 장면별 출처는 편집 정보에 기록. 이용 권한 확인 필요'
    if req.image_mode=='web' and not req.asset_id:
        credit='웹 검색 자료사진 · CC0/PDM · 상세 출처는 다운로드 content.json 참고' if web_credits else ''
    caption=finish_caption(content['caption'],req.image_mode,credit)
    if len(caption)>2200:raise p.ProviderError('캡션을 2,200자 이하로 줄여 주세요.')
    post={**req.model_dump(),**content,'caption':caption,'slides':slides,'id':uuid.uuid4().hex,'created_at':st.now(),'design_version':4,'status':'draft','facts_checked':False,'rights_checked':False,'image_credit':credit,'scheduled_at':None}
    post['caption_source_urls']=caption_urls(content['caption'])
    post['copy_style']='compact-v1'
    if automation_day:
        post['automation_day']=automation_day
        post['auto_schedule_excluded']=True
    if req.image_mode=='web' and not req.asset_id:
        post['web_image_credits']=web_credits
        post['generation_note']=f'AI 웹 사진 자동 선택 {len(web_credits)}/{len(slides)}장. ' + ' / '.join(web_notes)
    if auto_video:post['generation_note']=f'원고와 사용 가능한 사진에 맞춰 {len(slides)}장으로 자동 구성했습니다.'
    post['images']=await asyncio.to_thread(render,post)
    st.save(post);st.log('카드 생성: '+post['slides'][0]['title'])
    if automation_day and req.image_mode=='web' and any(not s.get('asset_id') for s in slides):
        post['quality']={'status':'needs_photos','message':'사진 미확보 카드가 있어 유료 이미지 평가를 생략했습니다.'}
        st.save(post)
        return post
    digest=quality.fingerprint(post)
    try:result=await quality.evaluate(post)
    except (ValueError,OSError) as exc:
        if p.stops_production(exc):raise
        result={'status':'error','message':'자동 평가를 완료하지 못했습니다. 초안은 저장했으며, 재평가 전 게시가 제한됩니다.'}
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
            candidates=await autopilot.candidates()
            for video in candidates:
                if len(made)>=config['daily_target']:break
                url='https://www.youtube.com/watch?v='+video['id']
                if url in used:continue
                used.add(url)
                try:
                    transcript,sources,image=await autopilot.material(video,asset_save)
                    source_policy.require_eligible(video)
                    req=Generate(text=json.dumps(sources,ensure_ascii=False)[:30000],source_name=video['snippet']['channelTitle'],source_url=url,category='뉴스',engine='ai',**image)
                    post=await create(req,automation_day=day)
                    post['source_verification']={'sources':sources,'video':video}
                    st.save(post);made.append(post['id'])
                except Exception as e:
                    if p.stops_production(e):raise
                    errors.append(str(e))
            msg=f'{len(made)}/{config["daily_target"]}개 초안 생성. 적합한 원문 부족 시 억지로 채우지 않습니다.'
            if errors:msg+=' '+errors[0]
            with st.db() as c:c.execute('UPDATE runs SET status=?,message=? WHERE day=?',('complete',msg,day))
            st.log(msg);return {'created':made,'message':msg}
        except Exception:
            with st.db() as c:c.execute('UPDATE runs SET status=?,message=? WHERE day=?',('failed','일일 생성 실패. 로그 및 연결 설정 확인.',day))
            raise

def authorized_extra_post(post, at):
    """A locally recorded user approval applies only to this exact card and time."""
    approval=st.setting('extra_post_approval:'+post['id'],{})
    if not isinstance(approval,dict):return False
    if approval.get('requested_by')!='user' or not approval.get('approved_at'):return False
    if approval.get('at')!=at.astimezone(st.KST).isoformat():return False
    try:return approval.get('fingerprint')==quality.fingerprint(post)
    except (KeyError,ValueError,OSError):return False

async def tick():
    global PRODUCTION_TASK
    config=st.setting('daily',st.DEFAULT_SCHEDULE)
    now=datetime.now(st.KST)
    pacing=cadence.config()
    if autopilot.enabled() and now.hour>=max(0,pacing['start_hour']-1):
        run_state=autopilot.state()
        if autopilot.should_run(run_state,now) and (PRODUCTION_TASK is None or PRODUCTION_TASK.done()):
            PRODUCTION_TASK=asyncio.create_task(autopilot.run(create,asset_save,LOCK))
    elif config['enabled'] and not autopilot.enabled() and now.hour>=config['hour']:
        with st.db() as c:exists=c.execute('SELECT 1 FROM runs WHERE day=?',(now.date().isoformat(),)).fetchone()
        if not exists and (PRODUCTION_TASK is None or PRODUCTION_TASK.done()):
            async def draft_production():
                try:await daily_run()
                except Exception as e:st.log(str(e))
            PRODUCTION_TASK=asyncio.create_task(draft_production())
    async with LOCK:
        pacing=cadence.config()
        if pacing['enabled']:
            all_posts=st.posts()
            # A missed window is moved forward; never burst-publish the backlog.
            overdue=[x for x in all_posts if x['status']=='scheduled' and cadence.parse(x['scheduled_at']) < now-timedelta(minutes=5)]
            ready=cadence.ready_new_posts(all_posts,pacing,quality.ensure_passed)
            queued=sorted(overdue,key=lambda x:x['scheduled_at'])+ready
            if queued:
                p.require('INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','PUBLIC_MEDIA_BASE_URL')
                cadence.save_reservations(queued,cadence.plan(queued,all_posts,now,pacing))
            if cadence.quiet(now):return
        for post in sorted(st.posts(),key=lambda x:x.get('scheduled_at') or ''):
            if post['status']!='scheduled' or datetime.fromisoformat(post['scheduled_at'])>now:continue
            if pacing['enabled']:
                recent_posts=[x for x in st.posts() if x['status']=='published' and x.get('published_at') and now-cadence.event_time(x)<timedelta(minutes=pacing['item_interval'])]
                if recent_posts:continue
            published=sum(x['status']=='published' and x.get('published_at','')[:10]==now.date().isoformat() for x in st.posts())
            if published>=cadence.daily_limit() and (pacing['enabled'] or not authorized_extra_post(post,datetime.fromisoformat(post['scheduled_at']))):continue
            try:await publish(post)
            except Exception as e:
                current=st.get(post['id'])
                if current['status']!='needs_check':current['status']='failed';current['error']=str(e);st.save(current)
                st.log('게시 실패/확인 필요: '+post['id'])
            if pacing['enabled']:break

async def worker():
    while True:
        try:await tick()
        except Exception as e:st.log('작업 오류: '+str(e)[:200])
        await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app):
    global PRODUCTION_TASK
    # Interrupted publishing must be inspected, never blindly retried.
    for post in st.posts():
        if post['status']=='publishing':post['status']='needs_check';post['error']='앱이 게시 중 종료되었습니다. 실제 게시 여부를 확인하세요.';st.save(post)
    task=asyncio.create_task(worker())
    yield
    task.cancel()
    try:await task
    except asyncio.CancelledError:pass
    if PRODUCTION_TASK is not None and not PRODUCTION_TASK.done():
        PRODUCTION_TASK.cancel()
        try:await PRODUCTION_TASK
        except asyncio.CancelledError:pass
    PRODUCTION_TASK=None

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
    keys={'ai':bool(os.getenv(p.ai_key_name())),'kie':bool(os.getenv('KIE_API_KEY')),'news':bool(os.getenv('NAVER_CLIENT_ID') and os.getenv('NAVER_CLIENT_SECRET')),'youtube':bool(os.getenv('YOUTUBE_API_KEY')),'instagram':all(os.getenv(n) for n in ['INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','PUBLIC_MEDIA_BASE_URL'])}
    journal=autopilot.state()
    return {'ai_settings':p.ai_settings(),'connections':keys,'daily':st.setting('daily',st.DEFAULT_SCHEDULE),'cadence':cadence.config(),'autopilot':journal,'source_policy':source_policy.config(),'publication_policy':publication_policy.config(),'operations':operations.snapshot(journal,st.posts(),source_limit=autopilot.SOURCE_ATTEMPT_LIMIT,video_attempt_limit=autopilot.MAX_VIDEO_ATTEMPTS),'time':st.now(),'note':'설정 존재 여부입니다. 실제 인증·게시 성공을 의미하지 않습니다.'}

@app.put('/api/publication-policy')
async def set_publication_policy(req:PublicationPolicy):
    if req.enabled and not req.acknowledge_unverified_rights:
        raise HTTPException(400,'영상 이용 권한 기록과 별개인 자동 게시 승인이 필요합니다.')
    async with LOCK:
        previous=publication_policy.config()
        approval_id=previous.get('approval_id') if previous.get('enabled') and req.enabled else uuid.uuid4().hex
        approved_at=previous.get('approved_at') if previous.get('enabled') and req.enabled else st.now()
        st.set_setting(publication_policy.KEY,{**req.model_dump(),'requested_by':'user','approval_id':approval_id,'approved_at':approved_at})
        st.log('새 유튜브 캡처 자동 게시 승인 '+('활성화' if req.enabled else '중지')+' · 권한 확인 기록은 별도 유지')
        return publication_policy.config()

@app.put('/api/posting-cadence')
async def save_cadence(req:PostingCadence):
    async with LOCK:
        if req.enabled and req.autopilot:p.require('OPENAI_API_KEY','YOUTUBE_API_KEY','NAVER_CLIENT_ID','NAVER_CLIENT_SECRET','INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','PUBLIC_MEDIA_BASE_URL')
        old=cadence.config();value=req.model_dump()
        value['enabled_at']=(old.get('enabled_at') if old['enabled'] else None) or st.now()
        st.set_setting(cadence.KEY,value)
        if req.enabled and req.autopilot:
            daily=st.setting('daily',st.DEFAULT_SCHEDULE)
            daily.update(enabled=False,daily_target=req.daily_limit)
            st.set_setting('daily',daily)
        return value

@app.post('/api/autopilot/retry')
async def retry_autopilot():
    async with LOCK:
        if not autopilot.enabled():raise HTTPException(400,'자동 제작·게시 설정을 먼저 켜세요.')
        if PRODUCTION_TASK is not None and not PRODUCTION_TASK.done():raise HTTPException(409,'이미 자동 제작이 진행 중입니다.')
        journal=autopilot.state();c=cadence.config()
        if journal.get('generation_attempts',len(journal.get('created',[])))>=c['daily_limit'] or journal.get('source_attempts',len(journal.get('attempted',[])))>=autopilot.SOURCE_ATTEMPT_LIMIT:
            raise HTTPException(400,'오늘 시도 한도에 도달했습니다. 비용 제한을 유지하며 내일 다시 실행합니다.')
        journal.update(status='ready',message='원인 해결 후 재확인 대기')
        journal.pop('next_retry_at',None);journal.pop('blocker_code',None)
        st.set_setting(autopilot.key(datetime.now(st.KST).date().isoformat()),journal)
        return {'message':'재확인을 요청했습니다. 기존 예약과 게시 결과는 유지합니다.'}

@app.post('/api/schedule/batch')
async def batch_schedule(req:BatchReservation):
    async with LOCK:
        pacing=cadence.config()
        if not pacing['enabled']:raise ValueError('발행 일정에서 시간대별 자동 예약을 먼저 켜세요.')
        p.require('INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','PUBLIC_MEDIA_BASE_URL')
        selected=[lookup(pid) for pid in req.post_ids]
        for post in selected:
            writable(post)
            if not post.get('facts_checked') or not post.get('rights_checked'):raise ValueError('선택한 모든 콘텐츠의 사실관계·이미지 사용 권한을 확인하고 저장하세요.')
            quality.ensure_passed(post)
            if post['ratio']=='9:16':raise ValueError('카드뉴스 피드 예약은 4:5 또는 1:1만 지원합니다.')
        now=datetime.now(st.KST)
        start=cadence.parse(req.start_at) if req.start_at else now
        if start<now and req.start_at:raise ValueError('미래 시간을 선택하세요.')
        if req.consecutive:
            if not req.start_at or not 2<=len(selected)<=3:raise ValueError('연속 예약은 시각을 지정한 2~3개 게시물만 지원합니다.')
            if cadence.quiet(start):raise ValueError('새벽 1시부터 6시까지는 게시하지 않습니다.')
            occupied=[cadence.event_time(x) for x in st.posts() if x['status'] in cadence.ACTIVE and cadence.event_time(x)]
            if sum(x.date()==start.date() for x in occupied)+len(selected)>pacing['daily_limit']:raise ValueError('하루 게시 한도를 초과합니다.')
            times=[start+timedelta(minutes=i*pacing['item_interval']) for i in range(len(selected))]
            if any(at.date()!=start.date() or cadence.quiet(at) for at in times):raise ValueError('같은 날 게시 가능한 시간대를 선택하세요.')
            if any(abs(x-at)<timedelta(minutes=pacing['item_interval']) for x in occupied for at in times):raise ValueError('다른 예약과 게시 간격이 겹칩니다.')
            for post in selected:post.pop('consecutive_group',None)
            reservations=[{'id':post['id'],'at':at.isoformat()} for post,at in zip(selected,times)]
        else:
            reservations=cadence.plan(selected,st.posts(),start,pacing)
        cadence.save_reservations(selected,reservations)
        return {'reservations':reservations}

@app.post('/api/library/trash')
async def trash_posts(ids:list[str]):
    from .library import move
    async with LOCK:return move(ids)

@app.post('/api/library/restore')
async def restore_posts(ids:list[str]):
    from .library import move
    async with LOCK:return move(ids,restore=True)

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
        post['caption_source_urls']=list(dict.fromkeys(post.get('caption_source_urls',[])+caption_urls(post['caption'])))
        post['caption']=finish_caption(post['caption'],post['image_mode'],post['image_credit'])
        if len(post['caption'])>2200:raise p.ProviderError('캡션을 2,200자 이하로 줄여 주세요.')
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

@app.post('/api/posts/{pid}/approve')
async def approve_post(pid:str):
    async with LOCK:
        post=lookup(pid);writable(post)
        quality.approve_manual(post);st.save(post)
        st.log('사용자 게시 승인: '+pid)
        return post

@app.post('/api/posts/{pid}/publish-manual')
async def publish_manual(pid:str,request:Request):
    body=await request.json()
    if body.get('acknowledge_unverified_rights') is not True:
        raise HTTPException(400,'이용 권한 미확인 상태의 수동 게시 승인이 필요합니다.')
    async with LOCK:
        post=lookup(pid);writable(post)
        quality.ensure_passed(post)
        if not post.get('facts_checked'):raise HTTPException(400,'사실 확인이 필요합니다.')
        post['manual_publication_consent']={'at':st.now(),'fingerprint':quality.fingerprint(post),'rights_verified':bool(post.get('rights_checked'))}
        post['auto_schedule_excluded']=True
        st.save(post)
        return await publish(post,explicit_manual=True)

@app.post('/api/posts/{pid}/schedule')
async def schedule(pid:str,req:Schedule):
    async with LOCK:
        post=lookup(pid);writable(post)
        p.require('INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','PUBLIC_MEDIA_BASE_URL')
        if not post.get('facts_checked') or not (post.get('rights_checked') or req.acknowledge_unverified_rights):raise p.ProviderError('사실관계·이미지 사용 권한을 확인하고 저장하세요.')
        quality.ensure_passed(post)
        if post['ratio']=='9:16':raise p.ProviderError('피드 예약은 4:5 또는 1:1만 지원합니다.')
        at=datetime.fromisoformat(req.at)
        if at.tzinfo is None:at=at.replace(tzinfo=st.KST)
        at=at.astimezone(st.KST)
        if at<=datetime.now(st.KST):raise p.ProviderError('미래 시간을 선택하세요.')
        count=sum(x['id']!=pid and x['status'] in cadence.ACTIVE and cadence.event_time(x) is not None and cadence.event_time(x).date()==at.date() for x in st.posts())
        pacing=cadence.config()
        if pacing['enabled'] and cadence.quiet(at):raise p.ProviderError('새벽 1시부터 6시까지는 게시하지 않습니다.')
        if pacing['enabled'] and any(x['id']!=pid and x['status'] in cadence.ACTIVE and cadence.event_time(x) and abs(cadence.event_time(x)-at)<timedelta(minutes=pacing['item_interval']) for x in st.posts()):raise p.ProviderError('다른 게시물과 최소 '+str(pacing['item_interval'])+'분 간격을 두세요.')
        if count>=cadence.daily_limit() and (pacing['enabled'] or not authorized_extra_post(post,at)):raise p.ProviderError('하루 예약 한도는 '+str(cadence.daily_limit())+'개입니다.')
        if req.acknowledge_unverified_rights:
            post['manual_publication_consent']={'at':st.now(),'fingerprint':quality.fingerprint(post),'rights_verified':bool(post.get('rights_checked'))}
            post['auto_schedule_excluded']=True
        post.update(status='scheduled',scheduled_at=at.isoformat(),error='');st.save(post);return post

@app.post('/api/posts/{pid}/cancel')
async def cancel(pid:str):
    async with LOCK:
        post=lookup(pid)
        if post['status'] not in ('scheduled','failed'):raise HTTPException(409,'취소 가능한 예약이 아닙니다.')
        post.update(status='draft',scheduled_at=None,auto_schedule_excluded=True);st.save(post);return post

@app.get('/api/posts/{pid}/download')
def download(pid:str):
    post=lookup(pid);buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for i in range(len(post['slides'])):z.write(st.MEDIA/pid/f'{i+1:02}.png',f'{i+1:02}.png')
        z.writestr('caption.txt',post['caption']);z.writestr('content.json',json.dumps(post,ensure_ascii=False,indent=2))
    buf.seek(0)
    return StreamingResponse(buf,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="issue-{pid[:8]}.zip"'})

@app.post('/api/import')
async def import_url(req:UrlInput):
    if not is_video_url(req.url):return await p.extract(req.url)
    if IMPORT_LOCK.locked():raise HTTPException(409,'영상 내용을 분석 중입니다. 완료 후 다시 시도하세요.')
    async with IMPORT_LOCK:
        return await extract_video(req.url,st.DATA)

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
        assets=[]
        for at,data in frames:
            data,enhancement=await asyncio.to_thread(finish_photo,data)
            asset=asset_save(data,f'영상 캡처 {at:.1f}초 / 방송 그래픽 크롭 / {req.url} / 이용 권한 확인 필요')
            meta={'credit':asset['credit'],'source_url':req.url,'at':at,'frame_label':'',
                  'cleanup':'overlay-crop-v2','permission_verified':False,'enhancement':enhancement}
            (st.ASSETS/(asset['asset_id']+'.json')).write_text(json.dumps(meta,ensure_ascii=False),encoding='utf-8')
            assets.append({**asset,'at':at})
        return {'assets':assets,'note':'원본 고화질 우선 · 인접 순간 선명도 비교 · 눈감김/흐림/과한 얼굴 왜곡 검사 · 자연스러운 색감·선명도 보정. 원본에 따라 최대 2배, 긴 변 최대 4K로 확대하며 촬영 디테일이 새로 생기는 것은 아닙니다. 카드 게시 크기는 1080px 피드 규격입니다.'}

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
    assets=[]
    for index,data in cleaned:
        aid=req.asset_ids[int(index)]
        original=json.loads((st.ASSETS/(aid+'.json')).read_text(encoding='utf-8'))
        data,enhancement=await asyncio.to_thread(finish_photo,data)
        asset=asset_save(data,original['credit'])
        original.update(cleanup='overlay-crop-v2',original_asset_id=aid,enhancement=enhancement,frame_label='')
        (st.ASSETS/(asset['asset_id']+'.json')).write_text(json.dumps(original,ensure_ascii=False),encoding='utf-8')
        assets.append(asset)
    return {'assets':assets}

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
