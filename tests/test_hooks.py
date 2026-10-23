import asyncio
import json

import pytest

from app.models import Generate
from app import providers


@pytest.mark.parametrize('tone', ['후킹형', '정보형', '공감형', '질문형'])
def test_ai_tone_reaches_provider_and_preserves_request(monkeypatch, tone):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only')
    req = Generate(text='도서관 운영 안내입니다. 토요일에는 오후 6시에 문을 닫습니다.',
                   tone=tone, count=1, engine='ai', cta='방문 전에 저장해 두세요.')
    async def fake_api(method, url, **kwargs):
        payload = kwargs['json']
        assert tone + ':' in payload['instructions']
        assert '오후 6시' in payload['input']
        assert req.cta in payload['input']
        assert '행동 요청은 캡션 마지막에 하나만' in payload['instructions']
        for family in ['호기심 갭', '권위차용', '사회적 증거', '이득 숫자', '손실회피', '잃을 뻔한 이야기']:
            assert family in payload['instructions']
        assert '예시의 소재·숫자·직함은 사실이 아니라 형식' in payload['instructions']
        result = {'slides': [{'title': '토요일 도서관, 6시 전에 방문하세요',
                              'body': '토요일 운영은 오후 6시까지입니다. 방문 전에 저장해 두세요.'}],
                  'caption': '도서관 운영 안내'}
        return {'output': [{'content': [{'type': 'output_text', 'text': json.dumps(result)}]}]}
    monkeypatch.setattr(providers, 'api', fake_api)
    result = asyncio.run(providers.ai_copy(req))
    assert len(result['slides']) == 1
    assert '오후 6시' in result['slides'][0]['body']
    assert result['hook_policy_version'] == 'targeted-six-hooks-v1'


def test_hook_default_keeps_local_copy_factual():
    req = Generate(text='도서관 운영 안내\n토요일에는 오후 6시에 문을 닫습니다.', count=1)
    assert req.tone == '후킹형'
    result = providers.local_copy(req)
    assert result['slides'][0]['title'] == '도서관 운영 안내'
    assert 'AI 요약 아님' in result['engine_note']
