"""User-requested continuation of already-collected material; no new source attempts."""
import asyncio,json,io
from pathlib import Path
from dotenv import load_dotenv
load_dotenv('.env')
from app import storage as st, autopilot as a, main, frame_cleanup as fc, quality, publication_policy, overlay_guard
from app.models import Generate
from app.photo_finish import finish
from app import providers as p

DAY='2026-10-19'
IDS=['6ZfypnsvFMs','QpTuRzVVSKQ']
VERSION=fc.VERSION

def say(value):print(json.dumps(value,ensure_ascii=False),flush=True)
def journal():return st.setting(a.key(DAY),{})
def save(j):j['updated_at']=st.now();st.set_setting(a.key(DAY),j)

async def run():
    if not (st.DATA/'server.paused').exists():raise ValueError('Stop managed worker before maintenance continuation')
    await a.verify_delivery()
    for vid in IDS:
        j=journal();repairs=j.setdefault('repair_continuations',{})
        marker=vid+':'+VERSION
        if marker in repairs:say({'skip':vid,'existing':repairs[marker]});continue
        if j.get('generation_attempts',0)>=a.cadence.config()['daily_limit']:break
        folder=st.DATA/'source-audits'/vid
        if not all((folder/name).exists() for name in ('sources.json','transcript.json','frames.json','ranking.json')):
            say({'skip':vid,'reason':'saved evidence missing'});continue
        repairs[marker]={'status':'started','at':st.now(),'reason':'user-requested repair of cached captures; no source recollection'}
        j['status']='repairing';j['message']='저장된 캡처 보정 중: '+vid;save(j);post=None
        try:
            video=await a.source_policy.fetch_video(vid)
            a.source_policy.require_eligible(video)
            sources=json.loads((folder/'sources.json').read_text(encoding='utf-8'))
            meta=json.loads((folder/'frames.json').read_text(encoding='utf-8'))
            url='https://www.youtube.com/watch?v='+vid
            if meta['url']!=url or sources[0]['source_url']!=url:raise ValueError('source mismatch')
            originals=[(at,(folder/f'original-{i:02}.jpg').read_bytes()) for i,at in enumerate(meta['times'],1)]
            ranking=[fc.RankedFrame.model_validate(d) for d in json.loads((folder/'ranking.json').read_text(encoding='utf-8'))['data']]
            with fc.audit_to(folder/VERSION):frames=await fc.clean_frames(originals,0,ranking=ranking)
            if not frames:raise ValueError('실제 크롭과 장면 보존 검사를 통과한 컷 없음')
            assets=[]
            for at,raw in frames:
                data,enhancement=await asyncio.to_thread(finish,raw)
                asset=main.asset_save(data,'자료화면');assets.append(asset['asset_id'])
                (st.ASSETS/(asset['asset_id']+'.json')).write_text(json.dumps({'credit':'자료화면','source_url':url,'at':at,'cleanup':VERSION,'permission_verified':False,'enhancement':enhancement,'frame_label':'자료화면'},ensure_ascii=False),encoding='utf-8')
            say({'video':vid,'clean_frames':len(assets)})
            j=journal();j['generation_attempts']=j.get('generation_attempts',0)+1;j['message']='복구한 캡처로 카드 제작 중: '+vid;save(j)
            req=Generate(text=json.dumps(sources,ensure_ascii=False)[:30000],engine='ai',count=0,category='뉴스',source_url=url,source_name=video['snippet']['channelTitle'],image_mode='video',video_asset_ids=assets)
            post=await main.create(req,automation_day=DAY)
            j=journal();j.setdefault('created',[]).append(post['id']);j['repair_continuations'][marker]['post_id']=post['id'];save(j)
            rights=await a.photo_rights(post);review=await a.verify(post,sources)
            post['source_verification']={'sources':sources,'video':video,'review':review}
            post['rights_review']=rights;post['facts_checked']=bool(review['passed']);post['rights_checked']=False;st.save(post)
            if not review['passed']:raise ValueError('원문 대조: '+review.get('reason',''))
            quality.ensure_passed(post)
            await overlay_guard.prepare_for_publish(post)
            if not publication_policy.record_automatic(post):raise ValueError('자동 게시 승인 조건 미충족')
            st.save(post);await a.verify_delivery(post)
            j=journal();j['repair_continuations'][marker].update(status='ready',post_id=post['id'],at=st.now());save(j)
            say({'video':vid,'post_id':post['id'],'status':'ready','slides':len(post['slides'])})
        except Exception as exc:
            reason=str(exc)[:250] if isinstance(exc,ValueError) else type(exc).__name__
            j=journal();j['repair_continuations'][marker].update(status='held',reason=reason,at=st.now());save(j)
            if post:
                post['automation_hold']=reason;st.save(post)
            say({'video':vid,'status':'held','reason':reason})
            if p.stops_production(exc):
                j['status']='needs_action';j['blocker_code']=exc.code;j['message']=reason;save(j);break
    j=journal()
    if j.get('status')!='needs_action':
        j['status']='waiting';j['message']='저장된 원문·캡처 수정 완료. 준비된 콘텐츠 게시 확인 중.';save(j)
    (st.DATA/'repair-20261019'/'continuations.json').write_text(json.dumps(j.get('repair_continuations',{}),ensure_ascii=False,indent=2),encoding='utf-8')

asyncio.run(run())
