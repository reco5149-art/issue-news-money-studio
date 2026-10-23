import asyncio,json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv('.env')
from app import main, storage as st, autopilot as a, quality, overlay_guard, publication_policy, providers as p
from app.photo_finish import finish
from app.copy_policy import finish_caption

async def run():
 post=st.get('57f857f73e904b18906571e104d81177')
 if post['status']!='draft':raise ValueError('draft only')
 old=[s['asset_id'] for s in post['slides']]
 root=st.DATA/'source-audits'/'HXXSJFOowbY'/'actual-crop-first-20261019-v3'
 times=json.loads((root/'crop-times.json').read_text(encoding='utf8'))['data']
 index=next(i for i,at in enumerate(times,1) if 40<at<45)
 reviews=json.loads((root/'crop-reviews.json').read_text(encoding='utf8'))['data']
 if not next(x for x in reviews if x['frame']==index)['clean']:raise ValueError('clean crop required')
 kept=[x for x in sorted(reviews,key=lambda x:x['frame']) if x['clean']]
 pair=next(i for i,x in enumerate(kept,1) if x['frame']==index)
 integrity=json.loads((root/'integrity-reviews.json').read_text(encoding='utf8'))['data']
 if not next(x for x in integrity if x['frame']==pair)['clean']:raise ValueError('integrity required')
 data,enhancement=finish((root/f'crop-{index:02}.jpg').read_bytes());asset=main.asset_save(data,'자료화면');aid=asset['asset_id']
 (st.ASSETS/(aid+'.json')).write_text(json.dumps({'credit':'자료화면','source_url':post['source_url'],'at':times[index-1],'cleanup':'actual-crop-first-20261019-v3','permission_verified':False,'enhancement':enhancement,'frame_label':'자료화면'},ensure_ascii=False),encoding='utf8')
 lines=[
 ('프랑스 시위, 처음엔 무엇 때문이었나','학생들의 교육 환경 개선 요구가 생활비 문제와 맞물리며 커졌습니다.'),
 ('학생 밖으로 번진 이유, 생활비 부담','노동단체와 시민들도 고물가 항의 시위에 나서며 규모가 커졌습니다.'),
 ('일부 지역에선 방화·약탈로 번졌다','일부 참가자의 폭력 행위로 상점·차량·공공건물 등이 피해를 입었습니다.'),
 ('마크롱, 청년 우려 인정·폭력엔 단호','젊은이들의 불안을 이해한다면서도 폭동에는 타협하지 않겠다고 밝혔습니다.'),
 ('유럽 고물가 시위, 후속 변화가 관건','다른 유럽 국가에서도 물가·주거비 부담에 항의하는 집회가 이어지고 있습니다.')]
 ids=[aid,old[2],old[0],old[3],old[4]]
 for s,(title,body),assetid in zip(post['slides'],lines,ids):s.update(title=title,body=body,asset_id=assetid,image_credit='자료화면')
 post['caption']=finish_caption('프랑스 시위는 왜 학생들 밖으로 번졌을까요? 출발점은 열악한 교육 환경에 대한 항의였습니다. 여기에 주거비와 생활비 부담, 공공서비스 악화에 대한 불만이 겹치면서 노동단체와 시민들의 참여로 이어졌습니다.\n\n10월 17일 현지 시각, 파리를 비롯한 프랑스 주요 도시에서 대규모 집회가 열렸습니다. 교육 환경 개선 요구와 고물가 항의가 맞물렸고, 일부 지역에서는 경찰과의 충돌·방화·약탈도 발생했습니다. 상점과 차량, 공공건물의 피해가 보도됐습니다. 생활 여건 개선이라는 시위 요구와 일부 참가자의 폭력 행위는 구분해서 볼 필요가 있습니다.\n\n마크롱 대통령은 젊은 세대의 우려와 불안을 이해한다고 밝히면서도 폭동에는 타협하지 않겠다는 입장을 냈습니다. 교육 문제에서 시작된 불만이 생활비 문제로 확대된 만큼 정부의 대응과 시위의 다음 움직임이 관건입니다.\n\n이탈리아·벨기에 등 다른 유럽 국가에서도 고물가와 주거비 부담에 항의하는 집회가 이어지고 있습니다. 각국의 배경과 요구가 모두 같은 것은 아닙니다.\n\n유럽 시위의 후속 변화와 쟁점을 이어서 정리합니다. 다음 소식이 필요하면 팔로우해 두세요. #프랑스시위 #고물가 #유럽뉴스', 'video','자료화면')
 for key in ('quality','overlay_review','automatic_publication_consent','manual_publication_consent'):post.pop(key,None)
 post['images']=main.render(post);post['facts_checked']=False;st.save(post)
 post['quality']=await quality.evaluate(post);st.save(post);quality.ensure_passed(post)
 sources=post['source_verification']['sources'];review=await a.verify(post,sources)
 post['source_verification']['review']=review;post['facts_checked']=review['passed'];st.save(post)
 if not review['passed']:raise ValueError(review.get('reason','source check failed'))
 await overlay_guard.prepare_for_publish(post)
 if not publication_policy.record_automatic(post):raise ValueError('automatic consent failed')
 st.save(post);await a.verify_delivery(post)
 print(json.dumps({'id':post['id'],'status':'ready','quality':post['quality']['status'],'facts':post['facts_checked'],'slides':len(post['slides'])},ensure_ascii=False),flush=True)

asyncio.run(run())
