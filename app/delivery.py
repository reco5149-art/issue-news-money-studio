"""Validate the account and the exact public images before sending to Meta."""
import hashlib
import os
from . import storage as st, providers as p

async def verify(post=None):
    if post is None:
        graph='https://graph.instagram.com/'+os.getenv('META_API_VERSION','v24.0')
        account=await p.api('GET',graph+'/'+os.environ['INSTAGRAM_USER_ID'],params={'fields':'username'},
                           headers={'Authorization':'Bearer '+os.environ['INSTAGRAM_ACCESS_TOKEN']})
        if account.get('username')!='issue_news_money':raise p.ProviderError('자동 게시 대상 계정 인증을 확인하지 못했습니다.')
        sample=next((x for x in st.posts() if x.get('slides') and (st.MEDIA/x['id']/'01.jpg').is_file()),None)
        if sample:await verify({**sample,'slides':sample['slides'][:1]})
        return
    base=os.environ['PUBLIC_MEDIA_BASE_URL'].rstrip('/')
    if not base.startswith('https://'):raise p.ProviderError('공개 이미지 연결은 HTTPS가 필요합니다.')
    for i in range(len(post['slides'])):
        try:raw,ctype,_=await p.fetch_public(f'{base}/{post["id"]}/{i+1:02}.jpg',limit=15_000_000)
        except p.ProviderError as exc:
            if exc.code=='dns_resolution':
                raise p.ProviderError('게시용 사진 공개 주소 연결 실패: '+str(exc),code='media_dns') from exc
            raise
        local=(st.MEDIA/post['id']/f'{i+1:02}.jpg').read_bytes()
        if not ctype.startswith('image/') or hashlib.sha256(raw).digest()!=hashlib.sha256(local).digest():
            raise p.ProviderError('외부 공개 이미지가 실제 게시 파일과 일치하지 않아 전송을 보류했습니다.',code='media_mismatch')
