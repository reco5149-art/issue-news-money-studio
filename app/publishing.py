import asyncio
import os
from datetime import datetime
from . import storage as st
from .providers import api, require, ProviderError, public_url

async def publish(post):
    require('INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','PUBLIC_MEDIA_BASE_URL')
    if post['ratio']=='9:16':raise ProviderError('9:16은 다운로드용입니다. 피드 자동 게시에는 4:5 또는 1:1을 사용하세요.')
    if not post.get('facts_checked') or not post.get('rights_checked'):raise ProviderError('사실관계·이미지 권한 확인 후 예약하세요.')
    base=os.environ['PUBLIC_MEDIA_BASE_URL'].rstrip('/')
    if not base.startswith('https://'):raise ProviderError('공개 이미지 주소는 HTTPS여야 합니다.')
    public_url(base)
    graph='https://graph.instagram.com/'+os.getenv('META_API_VERSION','v24.0')
    uid=os.environ['INSTAGRAM_USER_ID']; token=os.environ['INSTAGRAM_ACCESS_TOKEN']
    headers={'Authorization':'Bearer '+token}
    async def wait_ready(cid):
        for _ in range(30):
            r=await api('GET',f'{graph}/{cid}',params={'fields':'status_code'},headers=headers)
            if r.get('status_code')=='FINISHED':return
            if r.get('status_code') in ('ERROR','EXPIRED'):raise ProviderError('Meta 이미지 처리에 실패했습니다.')
            await asyncio.sleep(2)
        raise ProviderError('Meta 이미지 처리가 지연됩니다. 상태를 확인한 뒤 다시 예약하세요.')
    children=[]
    for i in range(len(post['slides'])):
        payload={'image_url':f'{base}/{post["id"]}/{i+1:02}.jpg'}
        if len(post['slides'])>1:payload['is_carousel_item']='true'
        else:payload['caption']=post['caption']
        r=await api('POST',f'{graph}/{uid}/media',headers=headers,data=payload)
        children.append(r['id']);await wait_ready(r['id'])
    cid=children[0]
    if len(children)>1:
        r=await api('POST',f'{graph}/{uid}/media',headers=headers,data={'media_type':'CAROUSEL','children':','.join(children),'caption':post['caption']})
        cid=r['id'];await wait_ready(cid)
    # Save before the irreversible request. Never automatically retry an ambiguous publish.
    post['container_id']=cid; post['status']='publishing';st.save(post)
    try:
        r=await api('POST',f'{graph}/{uid}/media_publish',headers=headers,data={'creation_id':cid})
    except Exception:
        post['status']='needs_check';post['error']='게시 결과 확인 필요. 인스타그램에서 실제 게시 여부를 확인하세요. 자동 재시도하지 않습니다.';st.save(post)
        raise
    post['status']='published';post['instagram_id']=r['id'];post['published_at']=st.now();post['error']='';st.save(post)
    st.log('인스타그램 게시 완료: '+post['id'])
    return post
