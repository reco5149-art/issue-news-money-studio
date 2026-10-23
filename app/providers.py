import asyncio
import base64
import html
import ipaddress
import json
import math
import os
import re
import socket
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, urljoin, parse_qs
import httpx
from bs4 import BeautifulSoup
from .storage import KST
from .copy_prompts import copy_instructions, STORY_VERSION
from .hook_policy import HOOK_VERSION
from .copy_policy import public_caption, story_paragraphs, compound_cta, has_broadcaster, TITLE_LIMIT, BODY_LIMIT, CAPTION_LIMIT

class ProviderError(ValueError):
    def __init__(self,message,*,code=None):
        super().__init__(message)
        self.code=code

def stops_production(exc):
    return isinstance(exc,ProviderError) and exc.code in ('openai_quota','ai_quota','api_auth','external_rate_limit','openai_rate_limit')

def require(*names):
    names=tuple(ai_key_name() if n=='OPENAI_API_KEY' else n for n in names)
    missing=[n for n in names if not os.getenv(n)]
    if missing: raise ProviderError('연결 설정이 필요합니다: '+', '.join(missing))

SCHOOL_BASE='https://factchat-cloud.mindlogic.ai/v1/gateway'

def ai_provider():
    provider=os.getenv('AI_PROVIDER','openai').strip().lower()
    if provider not in ('openai','semyung'):
        raise ProviderError('AI_PROVIDER는 openai 또는 semyung이어야 합니다.')
    return provider

def ai_key_name():
    return 'SEMYUNG_API_KEY' if ai_provider()=='semyung' else 'OPENAI_API_KEY'

def ai_headers():
    require('OPENAI_API_KEY')
    return {'Authorization':'Bearer '+os.environ[ai_key_name()]}

def ai_url(path):
    if ai_provider()=='openai':return 'https://api.openai.com/v1/'+path
    base=os.getenv('SEMYUNG_API_BASE_URL',SCHOOL_BASE).rstrip('/')
    if base!=SCHOOL_BASE:
        raise ProviderError('학교 API 주소가 공식 게이트웨이 주소와 다릅니다. 키 전송을 중단했습니다.')
    if path not in ('responses','models','credits'):
        raise ProviderError('학교 연결은 현재 문안 생성·사진 검수만 지원합니다. 음성 전사·AI 이미지 생성은 별도 연결이 필요하며 개인 API로 자동 전환하지 않습니다.')
    return base+'/'+path+'/'

def ai_model(role='TEXT'):
    if ai_provider()=='semyung':
        return os.getenv('SEMYUNG_'+role+'_MODEL') or os.getenv('SEMYUNG_TEXT_MODEL','gpt-5.4-mini')
    defaults={'TEXT':'gpt-4.1-mini','FRAME':'gpt-4.1','IMAGE':'gpt-image-1','TRANSCRIPTION':'gpt-transcribe'}
    return os.getenv('OPENAI_'+role+'_MODEL') or (os.getenv('OPENAI_TEXT_MODEL','gpt-4.1-mini') if role=='REVIEW' else defaults[role])

def ai_settings():
    return {'provider':ai_provider(),'configured':bool(os.getenv(ai_key_name())),
            'base_url':ai_url('responses').rsplit('/responses',1)[0],
            'models':{role.lower():ai_model(role) for role in ('TEXT','REVIEW','FRAME')},
            'personal_fallback':False}

def public_url(url):
    p=urlparse(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
        raise ProviderError('공개 HTTP/HTTPS 주소를 입력하세요.')
    if p.port not in (None,80,443): raise ProviderError('일반 웹 포트만 지원합니다.')
    try:
        addresses=socket.getaddrinfo(p.hostname,p.port or 443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ProviderError('내부 네트워크 주소는 가져올 수 없습니다.')
    except socket.gaierror as e: raise ProviderError(f'주소를 찾을 수 없습니다: {p.hostname} (DNS 조회 실패)',code='dns_resolution') from e
    return url

async def fetch_public(url, limit=3_000_000):
    # Validate each redirect. Local single-user server; never expose app as public proxy.
    async with httpx.AsyncClient(timeout=20,trust_env=False) as c:
        for _ in range(6):
            public_url(url)
            async with c.stream('GET',url,headers={'User-Agent':'IssueStudio/1.0 (+local research tool)'}) as r:
                if r.is_redirect:
                    url=urljoin(url,r.headers['location']); continue
                if r.status_code>=400: raise ProviderError(f'원문 사이트가 요청을 거절했습니다 ({r.status_code}). 원고를 붙여넣어 주세요.')
                chunks=[]; total=0
                async for chunk in r.aiter_bytes():
                    total+=len(chunk)
                    if total>limit: raise ProviderError('파일이 허용 크기를 초과했습니다.')
                    chunks.append(chunk)
                return b''.join(chunks),r.headers.get('content-type',''),url
    raise ProviderError('리디렉션이 너무 많습니다.')

async def api(method,url,**kwargs):
    try:
        async with httpx.AsyncClient(timeout=120,trust_env=False) as c:
            r=await c.request(method,url,**kwargs)
        if r.status_code>=400:
            if r.status_code in (401,402,403):
                service='학교 AI' if urlparse(url).hostname=='factchat-cloud.mindlogic.ai' else '외부 API'
                raise ProviderError(f'{service} 인증·결제·한도 확인 필요 ({r.status_code}). 자동 제작을 중단합니다.',code='ai_quota' if r.status_code==402 else 'api_auth')
            if r.status_code==429 and urlparse(url).hostname!='api.openai.com':
                host=urlparse(url).hostname
                service={'factchat-cloud.mindlogic.ai':'학교 AI','www.googleapis.com':'YouTube','openapi.naver.com':'Naver'}.get(host,'외부 API')
                raise ProviderError(f'{service} 요청 제한 (429): 요청 빈도 또는 사용 한도를 확인하세요. 자동 반복 요청을 중단했습니다.',code='external_rate_limit')
            if urlparse(url).hostname=='api.openai.com':
                try:error=r.json().get('error',{})
                except ValueError:error={}
                code=error.get('code')
                if code=='project_spend_limit_exceeded':
                    raise ProviderError('OpenAI 프로젝트 지출 한도를 초과했습니다. 프로젝트 한도·결제 설정을 확인해야 새 생성과 AI 검수를 재개할 수 있습니다.',code='openai_quota')
                if code=='insufficient_quota' or error.get('type')=='insufficient_quota':
                    raise ProviderError('OpenAI API 사용 한도 또는 크레딧이 부족합니다. 결제·한도 설정을 확인하세요.',code='openai_quota')
                if code=='rate_limit_exceeded':
                    raise ProviderError('OpenAI 요청이 일시적으로 집중됐습니다. 잠시 후 다시 시도합니다.',code='openai_rate_limit')
            raise ProviderError(f'외부 서비스 오류 ({r.status_code}). 키·권한·사용량을 확인하세요.')
        return r.json()
    except httpx.HTTPError as e:
        # Host and exception class identify the failing service without leaking URL keys.
        host=urlparse(url).hostname or 'unknown'
        service={'graph.instagram.com':'Instagram 게시 API','api.openai.com':'OpenAI',
                 'www.googleapis.com':'YouTube','naverapihub.apigw.ntruss.com':'Naver',
                 'openapi.naver.com':'Naver','factchat-cloud.mindlogic.ai':'학교 AI'}.get(host,'외부 API')
        raise ProviderError(f'{service} 연결 실패: {host} ({type(e).__name__}). 연결을 확인하세요.',code='external_connection') from e

def clean(s): return BeautifulSoup(html.unescape(s),'html.parser').get_text(' ',strip=True)

async def extract(url):
    host=(urlparse(url).hostname or '').lower()
    if host in ('youtube.com','www.youtube.com','m.youtube.com','youtu.be'):
        require('YOUTUBE_API_KEY')
        p=urlparse(url); vid=p.path.strip('/').split('/')[-1] if host=='youtu.be' or '/shorts/' in p.path else parse_qs(p.query).get('v',[''])[0]
        if not re.fullmatch(r'[\w-]{11}',vid):raise ProviderError('유튜브 영상 주소를 확인하세요.')
        data=await api('GET','https://www.googleapis.com/youtube/v3/videos',params={'id':vid,'part':'snippet,statistics','key':os.environ['YOUTUBE_API_KEY']})
        if not data.get('items'):raise ProviderError('접근 가능한 영상을 찾지 못했습니다.')
        s=data['items'][0]['snippet']
        return {'title':s['title'],'text':s['title']+'\n'+s.get('description',''),'source_name':s['channelTitle'], 'source_url':url,'warning':'영상 제목·설명만 가져왔습니다. 영상 내용·자막은 포함하지 않습니다.'}
    if host.endswith('instagram.com') or host.endswith('tiktok.com'):
        raise ProviderError('이 플랫폼의 본문 자동 추출은 지원하지 않습니다. 링크를 출처로 남기고 원고를 붙여넣거나 보유 영상을 업로드하세요.')
    data,ctype,final=await fetch_public(url)
    if 'html' not in ctype:raise ProviderError('HTML 기사·블로그 주소만 지원합니다.')
    soup=BeautifulSoup(data,'html.parser')
    title=soup.find('meta',property='og:title')
    title=title.get('content','') if title else (soup.title.get_text() if soup.title else '')
    for item in soup(['script','style','nav','footer','header','aside','noscript']):item.decompose()
    # Korean news sites often put the actual story in a div, not paragraph tags.
    article=soup.select_one('#dic_area, #newsct_article, #articleBody, #articleBodyContents, #article-view-content-div, .news_txt, .article_txt, .article-body, .article_body, .article-body-text, [itemprop="articleBody"]')
    root=article or soup.find('article') or soup.find('main') or soup
    paragraphs=[p.get_text(' ',strip=True) for p in root.find_all('p')]
    text='\n'.join(p for p in paragraphs if len(p)>25)
    if article is not None and len(text)<150:text=article.get_text(' ',strip=True)
    if len(text)<80:raise ProviderError('본문 추출이 제한된 페이지입니다. 원고를 직접 붙여넣어 주세요.')
    return {'title':title,'text':(title+'\n'+text)[:20000],'source_name':urlparse(final).hostname,'source_url':final,'warning':'추출된 본문을 원문과 비교해 확인하세요.'}

async def discover(category):
    result=[]; errors=[]
    if os.getenv('NAVER_CLIENT_ID') and os.getenv('NAVER_CLIENT_SECRET'):
        try:
            # New registrations use NAVER API HUB; legacy keys need explicit opt-in.
            mode=os.getenv('NAVER_API_MODE','hub').strip().lower()
            if mode=='hub':
                url='https://naverapihub.apigw.ntruss.com/search/v1/news'
                headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_CLIENT_SECRET']}
            elif mode=='legacy':
                url='https://openapi.naver.com/v1/search/news.json'
                headers={'X-Naver-Client-Id':os.environ['NAVER_CLIENT_ID'],'X-Naver-Client-Secret':os.environ['NAVER_CLIENT_SECRET']}
            else:
                raise ProviderError('NAVER_API_MODE는 hub 또는 legacy여야 합니다.')
            data=await api('GET',url,params={'query':category,'display':20,'sort':'date' if category in ('AI','경제','연예','뉴스','이슈') else 'sim'},headers=headers)
            for s in data.get('items',[]):
                age=max(0,(datetime.now(KST)-parsedate_to_datetime(s['pubDate'])).total_seconds()/3600)
                freshness=max(0,30-age*.7)
                title=clean(s['title']); utility=15 if any(k in title for k in ['지원','가격','출시','요금','세금','공개','발표']) else 5
                result.append({'title':title,'summary':clean(s['description']),'url':s.get('originallink') or s['link'],'portal_url':s.get('link',''),'source':'뉴스','category':category,'score':round(40+freshness+utility),'score_basis':'신선도 30 + 관련성 40 + 실용 키워드 15 (조회수 아님)','views':None,'published_at':s['pubDate']})
        except ProviderError as e:errors.append(str(e))
    if os.getenv('YOUTUBE_API_KEY') and category in ('AI','경제','연예','뉴스','이슈'):
        try:
            data=await api('GET','https://www.googleapis.com/youtube/v3/videos',params={'part':'snippet,statistics','chart':'mostPopular','regionCode':'KR','maxResults':30,'key':os.environ['YOUTUBE_API_KEY']})
            terms={'AI':['AI','인공지능','챗GPT','클로드'],'경제':['경제','주식','금리','부동산','투자'],'연예':['가수','아이돌','배우','뮤직','공연'],'뉴스':['뉴스','속보','정치'],'이슈':[]}[category]
            for s in data.get('items',[]):
                title=s['snippet']['title']
                if terms and not any(t.lower() in title.lower() for t in terms):continue
                views=int(s.get('statistics',{}).get('viewCount',0))
                result.append({'title':title,'summary':s['snippet'].get('description','')[:300],'url':'https://www.youtube.com/watch?v='+s['id'],'source':'YouTube','category':category,'score':min(99,round(40+math.log10(views+1)*8)),'score_basis':'YouTube 인기 차트 · 누적 조회수 기준 (뉴스 점수와 다른 기준)','views':views,'published_at':s['snippet']['publishedAt']})
        except ProviderError as e:errors.append(str(e))
    if not os.getenv('NAVER_CLIENT_ID') and not os.getenv('YOUTUBE_API_KEY'):
        raise ProviderError('실시간 소재 탐색에는 Naver 뉴스 또는 YouTube API 키가 필요합니다. 설정 안내를 확인하세요.')
    seen=set(); unique=[]
    for r in sorted(result,key=lambda a:a['score'],reverse=True):
        key=re.sub(r'\W','',r['title']).lower()
        if key not in seen:seen.add(key);unique.append(r)
    return {'items':unique,'warnings':errors}

def local_copy(req):
    # Deterministic extraction, clearly labelled in UI. Never fabricate current news.
    sentences=[s.strip() for s in re.split(r'\n+|(?<=[.!?。])\s+',req.text) if s.strip()]
    title=sentences[0][:55]
    chunks=[]
    for sentence in sentences[1:] or sentences:
        chunks.extend(sentence[i:i+180] for i in range(0,len(sentence),180))
    n=req.count or min(10,max(1,len(chunks)+2))
    if n==1: slides=[{'title':title,'body':chunks[0][:max(0,229-len(req.cta))]+'\n'+req.cta}]
    else:
        slides=[{'title':title,'body':chunks[0][:230] if n==2 else ('핵심을 함께 살펴봅니다.' if req.tone=='정보형' else '우리 일상에는 어떤 변화가 생길까요?')}]
        for i in range(n-2):
            body=chunks[i] if i<len(chunks) else '추가 내용을 입력해 주세요.'
            slides.append({'title':f'핵심 포인트 {i+1:02}','body':body})
        slides.append({'title':'여러분은 어떻게 생각하세요?','body':req.cta})
    excerpt=sentences[0] if len(sentences[0])<=200 else '원문 일부: '+sentences[0][:199]+'…'
    caption=public_caption(excerpt+'\n\n'+req.cta+'\n\n출처: '+req.source_name+'\n#'+req.category+' #카드뉴스 #이슈뉴스머니')
    return {'slides':slides,'caption':caption,'engine_note':'로컬 원문 배치 — AI 요약 아님. 생략된 내용과 빈 칸을 편집하세요.'}

async def ai_copy(req):
    require('OPENAI_API_KEY')
    slide={'type':'object','properties':{'title':{'type':'string'},'body':{'type':'string'},'visual_brief':{'type':'string'}},'required':['title','body','visual_brief'],'additionalProperties':False}
    schema={'type':'object','properties':{'slides':{'type':'array','items':slide},'caption':{'type':'string'}},'required':['slides','caption'],'additionalProperties':False}
    instructions=copy_instructions(req.tone)
    copy_input=req.model_dump()
    if copy_input['cta']=='나중에 다시 볼 수 있도록 저장하세요. 여러분의 생각은 댓글로 알려주세요.':
        copy_input['cta']='본문이 제공하는 가치에 맞춰 저장·공유·팔로우·구체적인 질문 중 주 행동 하나만 선택한다. 구체적인 이유가 없으면 생략한다.'
    payload={'model':ai_model('TEXT'),'store':False,'instructions':instructions,
             'input':json.dumps(copy_input,ensure_ascii=False)+'\n장수: '+(str(req.count) if req.count else '내용에 맞게 1~10'),
             'text':{'format':{'type':'json_schema','name':'cardnews','strict':True,'schema':schema}}}
    for attempt in range(2):
        data=await api('POST',ai_url('responses'),headers=ai_headers(),json=payload)
        text=''.join(c.get('text','') for o in data.get('output',[]) for c in o.get('content',[]) if c.get('type')=='output_text')
        try:
            result=json.loads(text)
            slides=result['slides']
            caption=story_paragraphs(result['caption'])
            valid=(1<=len(slides)<=10 and (not req.count or len(slides)==req.count) and
                   all(0<len(s['title'])<=TITLE_LIMIT and len(s['body'])<=BODY_LIMIT for s in slides) and
                   0<len(caption)<=CAPTION_LIMIT and not compound_cta(caption) and
                   not any(has_broadcaster(s['title']+' '+s['body']) for s in slides) and not has_broadcaster(caption))
        except (ValueError,TypeError,KeyError) as e:
            raise ProviderError('AI 응답을 읽을 수 없습니다. 다시 시도하세요.') from e
        if valid:
            result['caption']=caption
            result['engine_note']='AI 짧은 문안 — 출처 및 사실관계 검토 필요'
            result['story_policy_version']=STORY_VERSION
            result['hook_policy_version']=HOOK_VERSION
            return result
        # Recompose from the source instead of cutting off qualifying words.
        payload['instructions']=instructions+f' 이전 결과가 장수·길이·CTA·방송사명 제외 조건을 벗어났다. 원고에서 다시 요약하여 제목 32자·본문 70자·캡션 {CAPTION_LIMIT}자 이하와 요청 장수를 지켜라. 방송사 이름을 공개 문안에 쓰지 말고 확인된 사건을 직접 서술하되 의혹·전망·당사자 주장은 그대로 구분하라. 캡션 끝에는 소재에 맞춰 선택한 저장·공유·팔로우 중 한 가지 행동과 그 이유를 유지하라. 사용자가 질문을 요청한 경우에만 구체적인 질문 하나로 마무리하라. 여러 행동을 함께 요청하지 말라. 문장 중간을 자르거나 중요 조건을 빼지 말라.'
    raise ProviderError('짧은 문안 구성을 완료하지 못했습니다. 원고를 정리하거나 장수를 조정해 다시 생성하세요.')

IMAGE_RULES='Editorial conceptual illustration. No text. Do not depict actual news footage or real people. Topic: '

async def ai_image(prompt):
    require('OPENAI_API_KEY')
    data=await api('POST',ai_url('images/generations'),headers=ai_headers(),json={'model':ai_model('IMAGE'),'prompt':IMAGE_RULES+prompt[:1500],'n':1,'size':'1024x1024'})
    try:return base64.b64decode(data['data'][0]['b64_json'])
    except (KeyError,ValueError) as e:raise ProviderError('이미지 응답을 읽을 수 없습니다.') from e

KIE_BASE='https://api.kie.ai/api/v1'
# render.py places the photo in the upper 54% of the card, so request that slot's shape.
KIE_SLOT_RATIO={'4:5':'3:2','1:1':'16:9','9:16':'1:1'}
KIE_ERRORS={401:'KIE AI 키를 확인하세요.',402:'KIE AI 크레딧이 부족합니다.',422:'KIE AI 요청 형식이 맞지 않습니다. 이미지 모델 설정을 확인하세요.',429:'KIE AI 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.'}
KIE_LAYOUT=(' Composition: keep the key subject in the upper-middle of the frame; the lower part will sit under a dark '
            'gradient with card text, and the top corners hold small labels.')

def kie_data(data):
    # KIE reports most errors as HTTP 200 with a non-200 code field.
    code=data.get('code') if isinstance(data,dict) else None
    if code!=200:raise ProviderError(KIE_ERRORS.get(code,f'KIE AI 이미지 생성에 실패했습니다 (코드 {code}).'))
    return data.get('data') or {}

async def kie_image(prompt,ratio='4:5',poll=3.0,timeout=180):
    require('KIE_API_KEY')
    headers={'Authorization':'Bearer '+os.environ['KIE_API_KEY'].strip()}
    task=kie_data(await api('POST',KIE_BASE+'/jobs/createTask',headers=headers,json={
        'model':os.getenv('KIE_IMAGE_MODEL','nano-banana-2'),
        'input':{'prompt':IMAGE_RULES+prompt[:4000]+KIE_LAYOUT,'aspect_ratio':KIE_SLOT_RATIO.get(ratio,'3:2'),
                 'resolution':os.getenv('KIE_IMAGE_RESOLUTION','1K'),'output_format':'jpg'}}))
    tid=task.get('taskId')
    if not isinstance(tid,str) or not re.fullmatch(r'[\w-]{1,128}',tid):raise ProviderError('KIE AI 작업 번호를 받지 못했습니다.')
    loop=asyncio.get_running_loop();deadline=loop.time()+timeout;misses=0
    while True:
        try:info=kie_data(await api('GET',KIE_BASE+'/jobs/recordInfo',params={'taskId':tid},headers=headers));misses=0
        except ProviderError:
            misses+=1
            if misses>=3:raise
            info={}
        state=info.get('state')
        if state=='success':break
        if state=='fail':raise ProviderError('KIE AI 이미지 생성 실패: '+str(info.get('failMsg') or '원인 미상')[:200])
        # Never resubmit automatically: the task may already be billed.
        if loop.time()>=deadline:raise ProviderError(f'KIE AI 이미지 생성이 지연됩니다. KIE 기록에서 작업 {tid}을 확인하세요.')
        await asyncio.sleep(poll)
    try:url=json.loads(info.get('resultJson') or '{}')['resultUrls'][0]
    except (ValueError,KeyError,IndexError,TypeError) as e:raise ProviderError('KIE AI 결과 이미지 주소를 읽을 수 없습니다.') from e
    try:data,ctype,_=await fetch_public(url,20_000_000)
    except ProviderError as e:raise ProviderError(f'KIE AI 결과 이미지를 내려받지 못했습니다. KIE 기록에서 작업 {tid}을 확인하세요.') from e
    if not ctype.startswith('image/'):raise ProviderError('KIE AI 결과가 이미지 파일이 아닙니다.')
    return data

async def web_images(query,licenses="cc0,pdm,by,by-sa"):
    data=await api('GET','https://api.openverse.org/v1/images/',params={'q':query,'page_size':12,'license':licenses},headers={'User-Agent':'IssueStudio/1.0'})
    items=[]
    for item in data.get('results',[]):
        if item.get('license') not in ('cc0','pdm','by','by-sa'):continue
        items.append({'title':item.get('title',''),'url':item['url'],'thumbnail':item.get('thumbnail') or item['url'], 'page':item.get('foreign_landing_url',''),'credit':item.get('creator') or '제작자 확인 필요', 'license':item.get('license','').upper()+' '+item.get('license_version',''),'license_url':item.get('license_url','')})
    return items
