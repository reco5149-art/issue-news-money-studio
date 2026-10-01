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
from .copy_prompts import copy_instructions

class ProviderError(ValueError): pass

def require(*names):
    missing=[n for n in names if not os.getenv(n)]
    if missing: raise ProviderError('연결 설정이 필요합니다: '+', '.join(missing))

def public_url(url):
    p=urlparse(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
        raise ProviderError('공개 HTTP/HTTPS 주소를 입력하세요.')
    if p.port not in (None,80,443): raise ProviderError('일반 웹 포트만 지원합니다.')
    try:
        addresses=socket.getaddrinfo(p.hostname,p.port or 443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ProviderError('내부 네트워크 주소는 가져올 수 없습니다.')
    except socket.gaierror as e: raise ProviderError('주소를 찾을 수 없습니다.') from e
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
        if r.status_code>=400: raise ProviderError(f'외부 서비스 오류 ({r.status_code}). 키·권한·사용량을 확인하세요.')
        return r.json()
    except httpx.HTTPError as e: raise ProviderError('외부 서비스 연결이 지연되거나 실패했습니다. 연결을 확인하세요.') from e

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
    root=soup.find('article') or soup.find('main') or soup
    paragraphs=[p.get_text(' ',strip=True) for p in root.find_all('p')]
    text='\n'.join(p for p in paragraphs if len(p)>25)
    if len(text)<80:raise ProviderError('본문 추출이 제한된 페이지입니다. 원고를 직접 붙여넣어 주세요.')
    return {'title':title,'text':(title+'\n'+text)[:20000],'source_name':urlparse(final).hostname,'source_url':final,'warning':'추출된 본문을 원문과 비교해 확인하세요.'}

async def discover(category):
    result=[]; errors=[]
    if os.getenv('NAVER_CLIENT_ID') and os.getenv('NAVER_CLIENT_SECRET'):
        try:
            data=await api('GET','https://openapi.naver.com/v1/search/news.json',params={'query':category,'display':20,'sort':'date'},headers={'X-Naver-Client-Id':os.environ['NAVER_CLIENT_ID'],'X-Naver-Client-Secret':os.environ['NAVER_CLIENT_SECRET']})
            for s in data.get('items',[]):
                age=max(0,(datetime.now(KST)-parsedate_to_datetime(s['pubDate'])).total_seconds()/3600)
                freshness=max(0,30-age*.7)
                title=clean(s['title']); utility=15 if any(k in title for k in ['지원','가격','출시','요금','세금','공개','발표']) else 5
                result.append({'title':title,'summary':clean(s['description']),'url':s.get('originallink') or s['link'],'source':'뉴스','category':category,'score':round(40+freshness+utility),'score_basis':'신선도 30 + 관련성 40 + 실용 키워드 15 (조회수 아님)','views':None,'published_at':s['pubDate']})
        except ProviderError as e:errors.append(str(e))
    if os.getenv('YOUTUBE_API_KEY'):
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
    caption=(req.text[:1400]+'\n\n'+req.cta+'\n\n출처: '+req.source_name+' '+req.source_url+'\n#'+req.category+' #카드뉴스 #오늘의이슈 #정보공유 #이슈뉴스머니')[:2200]
    return {'slides':slides,'caption':caption,'engine_note':'로컬 원문 배치 — AI 요약 아님. 생략된 내용과 빈 칸을 편집하세요.'}

async def ai_copy(req):
    require('OPENAI_API_KEY')
    slide={'type':'object','properties':{'title':{'type':'string'},'body':{'type':'string'},'visual_brief':{'type':'string'}},'required':['title','body','visual_brief'],'additionalProperties':False}
    schema={'type':'object','properties':{'slides':{'type':'array','items':slide},'caption':{'type':'string'}},'required':['slides','caption'],'additionalProperties':False}
    instructions=copy_instructions(req.tone)
    payload={'model':os.getenv('OPENAI_TEXT_MODEL','gpt-4.1-mini'),'store':False,'instructions':instructions,
             'input':json.dumps(req.model_dump(),ensure_ascii=False)+'\n장수: '+(str(req.count) if req.count else '내용에 맞게 1~10'),
             'text':{'format':{'type':'json_schema','name':'cardnews','strict':True,'schema':schema}}}
    data=await api('POST','https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},json=payload)
    text=''.join(c.get('text','') for o in data.get('output',[]) for c in o.get('content',[]) if c.get('type')=='output_text')
    try:result=json.loads(text)
    except (ValueError,TypeError) as e:raise ProviderError('AI 응답을 읽을 수 없습니다. 다시 시도하세요.') from e
    if not 1<=len(result['slides'])<=10 or (req.count and len(result['slides'])!=req.count):raise ProviderError('AI 응답 장수가 요청과 다릅니다. 다시 시도하세요.')
    result['engine_note']='AI 초안 — 출처 및 사실관계 검토 필요'
    return result

async def ai_image(prompt):
    require('OPENAI_API_KEY')
    data=await api('POST','https://api.openai.com/v1/images/generations',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},json={'model':os.getenv('OPENAI_IMAGE_MODEL','gpt-image-1'),'prompt':'Editorial conceptual illustration. No text. Do not depict actual news footage or real people. Topic: '+prompt[:1500],'n':1,'size':'1024x1024'})
    try:return base64.b64decode(data['data'][0]['b64_json'])
    except (KeyError,ValueError) as e:raise ProviderError('이미지 응답을 읽을 수 없습니다.') from e

async def web_images(query,licenses="cc0,pdm,by,by-sa"):
    data=await api('GET','https://api.openverse.org/v1/images/',params={'q':query,'page_size':12,'license':licenses},headers={'User-Agent':'IssueStudio/1.0'})
    items=[]
    for item in data.get('results',[]):
        if item.get('license') not in ('cc0','pdm','by','by-sa'):continue
        items.append({'title':item.get('title',''),'url':item['url'],'thumbnail':item.get('thumbnail') or item['url'], 'page':item.get('foreign_landing_url',''),'credit':item.get('creator') or '제작자 확인 필요', 'license':item.get('license','').upper()+' '+item.get('license_version',''),'license_url':item.get('license_url','')})
    return items
