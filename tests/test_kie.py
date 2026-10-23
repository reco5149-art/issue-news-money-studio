import asyncio
import json

import pytest
from app import providers


def run(monkeypatch, responses, download=(b'jpeg-bytes', 'image/jpeg', 'u')):
    monkeypatch.setenv('KIE_API_KEY', 'test-kie-key')
    monkeypatch.delenv('KIE_IMAGE_MODEL', raising=False)
    calls = []
    async def fake_api(method, url, **kw):
        calls.append((method, url, kw))
        return responses.pop(0)
    fetched = []
    async def fake_fetch(url, limit):
        fetched.append(url)
        return download
    monkeypatch.setattr(providers, 'api', fake_api)
    monkeypatch.setattr(providers, 'fetch_public', fake_fetch)
    return calls, fetched


def ok(data):
    return {'code': 200, 'msg': 'success', 'data': data}


def test_kie_creates_task_polls_and_downloads(monkeypatch):
    calls, fetched = run(monkeypatch, [
        ok({'taskId': 'task_abc123'}),
        ok({'state': 'generating'}),
        ok({'state': 'success', 'resultJson': json.dumps({'resultUrls': ['https://cdn.example.com/a.jpg']})}),
    ])
    data = asyncio.run(providers.kie_image('카드 제목', '4:5', poll=0))
    assert data == b'jpeg-bytes' and fetched == ['https://cdn.example.com/a.jpg']
    method, url, kw = calls[0]
    assert (method, url) == ('POST', 'https://api.kie.ai/api/v1/jobs/createTask')
    assert kw['headers']['Authorization'] == 'Bearer test-kie-key'
    body = kw['json']
    assert body['model'] == 'nano-banana-2'
    assert body['input']['aspect_ratio'] == '3:2'  # photo slot of a 4:5 card
    assert '카드 제목' in body['input']['prompt'] and 'No text' in body['input']['prompt']
    assert 'test-kie-key' not in json.dumps(body)
    assert calls[1][1].endswith('/jobs/recordInfo') and calls[1][2]['params'] == {'taskId': 'task_abc123'}


@pytest.mark.parametrize('ratio,slot', [('1:1', '16:9'), ('9:16', '1:1')])
def test_kie_slot_ratio(monkeypatch, ratio, slot):
    calls, _ = run(monkeypatch, [ok({'taskId': 't1'}), ok({'state': 'success', 'resultJson': '{"resultUrls":["https://x.example/b.jpg"]}'})])
    asyncio.run(providers.kie_image('p', ratio, poll=0))
    assert calls[0][2]['json']['input']['aspect_ratio'] == slot


def test_kie_insufficient_credit_is_reported(monkeypatch):
    calls, fetched = run(monkeypatch, [{'code': 402, 'msg': 'insufficient'}])
    with pytest.raises(providers.ProviderError, match='크레딧'):
        asyncio.run(providers.kie_image('p', poll=0))
    assert len(calls) == 1 and fetched == []


def test_kie_failed_task_does_not_download(monkeypatch):
    calls, fetched = run(monkeypatch, [ok({'taskId': 't2'}), ok({'state': 'fail', 'failMsg': 'content policy'})])
    with pytest.raises(providers.ProviderError, match='content policy'):
        asyncio.run(providers.kie_image('p', poll=0))
    assert fetched == []


def test_kie_timeout_never_resubmits(monkeypatch):
    calls, fetched = run(monkeypatch, [ok({'taskId': 't3'})] + [ok({'state': 'queuing'})] * 50)
    with pytest.raises(providers.ProviderError, match='t3'):
        asyncio.run(providers.kie_image('p', poll=0, timeout=0))
    assert sum(c[1].endswith('/createTask') for c in calls) == 1 and fetched == []


def test_kie_rejects_non_image_result(monkeypatch):
    run(monkeypatch, [ok({'taskId': 't4'}), ok({'state': 'success', 'resultJson': '{"resultUrls":["https://x.example/c"]}'})],
        download=(b'<html>', 'text/html', 'u'))
    with pytest.raises(providers.ProviderError, match='이미지 파일이 아닙니다'):
        asyncio.run(providers.kie_image('p', poll=0))


def test_kie_requires_key(monkeypatch):
    monkeypatch.delenv('KIE_API_KEY', raising=False)
    with pytest.raises(providers.ProviderError, match='KIE_API_KEY'):
        asyncio.run(providers.kie_image('p'))
