import asyncio,json
from dotenv import load_dotenv
load_dotenv('.env')
from app import main,storage as st,quality,autopilot as a,overlay_guard,publication_policy
from app.copy_policy import finish_caption

async def check(post):
 for key in ('quality','overlay_review','automatic_publication_consent','manual_publication_consent'):post.pop(key,None)
 post['images']=main.render(post);post['facts_checked']=False;st.save(post)
 post['quality']=await quality.evaluate(post);st.save(post);quality.ensure_passed(post)
 review=await a.verify(post,post['source_verification']['sources']);post['source_verification']['review']=review;post['facts_checked']=review['passed'];st.save(post)
 if not review['passed']:raise ValueError(review.get('reason','facts'))
 await overlay_guard.prepare_for_publish(post)
 if not publication_policy.record_automatic(post):raise ValueError('consent')
 st.save(post);await a.verify_delivery(post)
 print(json.dumps({'id':post['id'],'status':'ready','slides':len(post['slides'])},ensure_ascii=False),flush=True)

async def run():
 stock=st.get('1bd26e976f8d4a3cad7028818c144ad9')
 if stock['status']!='draft':raise ValueError('draft only')
 stock['caption']=finish_caption('코스피 하락을 두고 유승민 전 의원이 정부 책임론을 제기했습니다. 핵심은 단순한 주가 전망이 아니라 국민연금 운용 원칙과 단일종목 레버리지 상품 도입을 둘러싼 정책 비판입니다.\n\n유 전 의원은 국민연금의 리밸런싱 원칙이 훼손됐고, 주가 부양에 노후자금이 동원됐다는 취지로 주장했습니다. 삼성전자·SK하이닉스 관련 단일종목 레버리지 상품 도입도 문제로 지목했습니다. 이는 유 전 의원의 주장으로, 정책이 증시 하락의 유일한 원인이라고 확정된 것은 아닙니다.\n\n그는 국정감사와 국정조사, 책임자 고발 및 특검 등을 통한 진상 규명도 요구했습니다. 공개 발언을 읽을 때는 실제 시장 지표, 정책 내용, 정치인의 책임 주장을 구분하는 것이 중요합니다.\n\n공장 사진은 관련 산업을 보여 주는 자료화면입니다. 특정 기업의 투자 가치나 향후 주가를 뜻하지 않습니다.\n\n증시 관련 발언을 다시 볼 때 ‘확인된 수치’와 ‘발언자의 주장’을 나눠 확인할 수 있도록 저장해 두세요. #코스피 #국민연금 #증시쟁점','video','자료화면')
 await check(stock)
 post=st.get('a7214472ec86429c8baa59c4a9e7487d')
 if post['status']!='draft':raise ValueError('draft only')
 first=post['slides'][0].copy();second=post['slides'][2].copy()
 first.update(title='우크라이나 통신 장애, 미국 배후설은 확인됐나',body='젤렌스키는 미국 정부 개입을 주장했지만, 트럼프 행정부는 관련 지시를 부인했습니다.')
 second.update(title='스타실드와 스타링크, 무엇이 다른가',body='스타실드는 스타링크 기반의 군사·정부용 위성망으로, 보안 수준과 이용 목적에 차이가 있습니다.')
 post['slides']=[first,second]
 post['caption']=finish_caption('우크라이나군의 위성통신 제한 논란에서, 장애를 겪었다는 주장과 누가 지시했는지는 구분해야 합니다. 젤렌스키 대통령은 미국 정부 내부에서 군사용 위성통신 제한 지시가 나왔고 드론 운용에 영향을 줬다고 주장했습니다.\n\n미국 측 설명은 다릅니다. 트럼프 대통령은 책임을 부인했고, 베선트 재무장관도 행정부가 관련 조치를 지시하지 않았다는 입장을 밝혔습니다. 제한의 지시 주체에 대한 양측 주장이 맞서는 사안입니다. 어느 한쪽의 설명을 확정 사실처럼 받아들이지 않는 것이 중요합니다.\n\n이번 쟁점의 서비스는 스타실드입니다. 스페이스X의 스타링크 위성망을 기반으로 하지만 군사·정부 및 국가안보 목적에 맞춰 강화된 보안 기능을 갖춘 서비스로 설명됩니다. 일반 소비자·기업용 스타링크와 이름이나 이용 목적을 혼동하지 않아야 합니다.\n\n영상에 등장한 다른 무기체계의 문제까지 모두 이 통신 제한 때문이라고 단정할 수는 없습니다. 카드의 영상 캡처는 관련 자료화면이며, 사진 속 특정 장비에서 장애가 발생했다는 증거는 아닙니다.\n\n후속 보도를 볼 때 ‘서비스 구분·장애 내용·지시 주체’를 나눠 확인할 수 있도록 저장해 두세요. #우크라이나 #스타실드 #위성통신','video','자료화면')
 await check(post)

asyncio.run(run())
