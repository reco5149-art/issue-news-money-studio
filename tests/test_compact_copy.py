import asyncio
import json
import pytest
from app import providers as p
from app.copy_policy import public_caption, finish_caption, caption_urls
from app.models import Generate


def test_remove_addresses_without_removing_claims_or_names():
    text='아직 확정은 아닙니다.\n\n출처: MBC https://imnews.imbc.com/a\n[보도 원문](https://example.com/a)\n출처 링크: https://youtu.be/abcdefghijk\nwww.example.org/test\n#국감'
    public=public_caption(text)
    assert '아직 확정은 아닙니다.' in public and 'MBC' not in public and '#국감' in public
    assert not caption_urls(public) and '출처 링크:' not in public
    assert len(caption_urls(text))==4


def test_video_asset_credit_cannot_reintroduce_urls():
    result=finish_caption('담백한 요약입니다.\n출처: JTBC','video','영상 캡처 4초 / https://youtube.com/watch?v=abcdefghijk / 이용 권한 확인 필요')
    assert '영상 캡처' not in result
    assert not caption_urls(result) and '이용 권한' not in result

def test_joined_broadcaster_brand_is_not_public_credit():
    from app.copy_policy import public_source_label
    assert public_source_label('MBCNEWS')==''
    assert public_source_label('JTBC News')==''
    assert public_source_label('개인 사진')=='개인 사진'


def test_ai_long_copy_recomposed_not_silently_truncated(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test')
    calls=[]
    async def fake(*args,**kwargs):
        calls.append(kwargs['json']['instructions'])
        result={'slides':[{'title':'일정은 아직 확정 전','body':'보도에 따르면 '*20 if len(calls)==1 else '당국이 검토 중이며 시행일은 미정입니다.','visual_brief':'building'}],
                'caption':'당국이 일정을 검토 중입니다.\n출처: 뉴스 https://example.com/report\n#뉴스'}
        return {'output':[{'content':[{'type':'output_text','text':json.dumps(result,ensure_ascii=False)}]}]}
    monkeypatch.setattr(p,'api',fake)
    result=asyncio.run(p.ai_copy(Generate(text='당국이 일정을 검토 중이며 아직 확정하지 않았습니다.',count=1)))
    assert len(calls)==2 and result['slides'][0]['body'].endswith('미정입니다.')
    assert not caption_urls(result['caption'])


def test_ai_length_failure_is_bounded(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test')
    calls=[]
    async def fake(*args,**kwargs):
        calls.append(1)
        return {'output':[{'content':[{'type':'output_text','text':json.dumps({'slides':[{'title':'긴 제목'*40,'body':'본문'}],'caption':'요약'})}]}]}
    monkeypatch.setattr(p,'api',fake)
    with pytest.raises(p.ProviderError,match='짧은 문안'):
        asyncio.run(p.ai_copy(Generate(text='확인할 원고입니다.')))
    assert len(calls)==2


def test_rewrite_keeps_topic_matched_share_cta(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test')
    calls=[]
    async def fake(*args,**kwargs):
        calls.append(kwargs['json']['instructions'])
        result={'slides':[{'title':'발리 주유 대기','body':'확인된 내용 '*30 if len(calls)==1 else '현지 주유 대기가 보도됐습니다.','visual_brief':'fuel station'}],
                'caption':'주유 대기는 14일 보도 기준입니다.\n\n발리 여행을 앞둔 동행에게 공유해 주세요.'}
        return {'output':[{'content':[{'type':'output_text','text':json.dumps(result,ensure_ascii=False)}]}]}
    monkeypatch.setattr(p,'api',fake)
    result=asyncio.run(p.ai_copy(Generate(text='발리 주유 대기. 14일 보도 기준.',count=1)))
    assert len(calls)==2
    assert '구체적인 질문 하나만 쓰고' not in calls[1]
    assert '선택한 저장·공유·팔로우 중 한 가지 행동과 그 이유를 유지' in calls[1]
    assert result['caption'].endswith('공유해 주세요.')
    assert result['story_policy_version']=='reader-value-v5'
    assert '사용자 지정 6가지 후킹' in calls[1]
