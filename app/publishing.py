import asyncio
import os
from datetime import datetime
from . import storage as st
from .providers import api, require, ProviderError, public_url
from .quality import ensure_passed
from .overlay_guard import prepare_for_publish as ensure_clean
from . import publication_policy, source_policy
from . import operations
from .delivery import verify as verify_delivery

async def verify_published(post):
    """Read back the live media; a lookup failure must never trigger a repost."""
    graph='https://graph.instagram.com/'+os.getenv('META_API_VERSION','v24.0')
    try:
        remote=await api('GET',f'{graph}/{post["instagram_id"]}',
                         params={'fields':'id,permalink,media_type,timestamp,children{id,media_type}'},
                         headers={'Authorization':'Bearer '+os.environ['INSTAGRAM_ACCESS_TOKEN']})
        children=(remote.get('children') or {}).get('data',[])
        expected=len(post['slides'])
        confirmed=(str(remote.get('id'))==str(post['instagram_id']) and
                   str(remote.get('permalink','')).startswith('https://www.instagram.com/') and
                   ((expected==1 and remote.get('media_type')=='IMAGE') or
                    (expected>1 and remote.get('media_type')=='CAROUSEL_ALBUM' and len(children)==expected)))
        result={'status':'verified' if confirmed else 'needs_check','checked_at':st.now(),
                'instagram_id':remote.get('id'),'permalink':remote.get('permalink'),
                'media_type':remote.get('media_type'),'timestamp':remote.get('timestamp'),
                'image_count':len(children) if children else (1 if remote.get('media_type')=='IMAGE' else 0)}
    except Exception:
        result={'status':'needs_check','checked_at':st.now(),
                'message':'게시 응답은 받았지만 실제 게시물 조회를 완료하지 못했습니다. 재게시하지 말고 확인하세요.'}
    post['publication_verification']=result
    st.save(post)
    st.log(('실제 게시 확인: ' if result['status']=='verified' else '게시 후 조회 확인 필요: ')+post['id'])
    return result

async def publish(post, *, explicit_manual=False):
    require('INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','PUBLIC_MEDIA_BASE_URL')
    operations.ensure_send_allowed(post)
    if post['ratio']=='9:16':raise ProviderError('9:16은 다운로드용입니다. 피드 자동 게시에는 4:5 또는 1:1을 사용하세요.')
    if not post.get('facts_checked') or not (post.get('rights_checked') or explicit_manual or publication_policy.authorized(post)):raise ProviderError('사실관계 확인과 게시 승인이 필요합니다.')
    source_video=await source_policy.ensure_publishable(post)
    operations.ensure_photos(post)
    ensure_passed(post)
    await ensure_clean(post)
    # A changed image/caption must not silently inherit a previous consent.
    if not post.get('rights_checked') and not explicit_manual and not publication_policy.authorized(post):
        raise ProviderError('수정된 최종 콘텐츠의 게시 승인을 다시 확인해야 합니다.')
    base=os.environ['PUBLIC_MEDIA_BASE_URL'].rstrip('/')
    if not base.startswith('https://'):raise ProviderError('공개 이미지 주소는 HTTPS여야 합니다.')
    public_url(base)
    await verify_delivery(post)
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
    if source_video is not None:
        source_policy.ensure_still_current(post,source_video)
    operations.ensure_send_allowed(post)
    operations.record_preflight(post)
    post['container_id']=cid; post['status']='publishing';st.save(post)
    try:
        r=await api('POST',f'{graph}/{uid}/media_publish',headers=headers,data={'creation_id':cid})
    except Exception:
        post['status']='needs_check';post['error']='게시 결과 확인 필요. 인스타그램에서 실제 게시 여부를 확인하세요. 자동 재시도하지 않습니다.';st.save(post)
        raise
    post['status']='published';post['instagram_id']=r['id'];post['published_at']=st.now();post['error']=''
    if post.get('automation_hold'):
        post['resolved_automation_hold']={'reason':post.pop('automation_hold'),'resolved_at':post['published_at']}
    st.save(post)
    st.log('인스타그램 게시 완료: '+post['id'])
    await verify_published(post)
    return post
