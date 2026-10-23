import asyncio
from unittest.mock import AsyncMock

import pytest
from app import providers


@pytest.mark.parametrize('mode,host,header', [
    ('hub', 'https://naverapihub.apigw.ntruss.com/search/v1/news', 'X-NCP-APIGW-API-KEY'),
    ('legacy', 'https://openapi.naver.com/v1/search/news.json', 'X-Naver-Client-Secret'),
])
def test_news_discovery_credentials_and_result(monkeypatch, mode, host, header):
    monkeypatch.setenv('NAVER_CLIENT_ID', 'test-id')
    monkeypatch.setenv('NAVER_CLIENT_SECRET', 'test-secret')
    monkeypatch.setenv('NAVER_API_MODE', mode)
    monkeypatch.delenv('YOUTUBE_API_KEY', raising=False)
    call = AsyncMock(return_value={'items': [{
        'title': '<b>AI</b> 발표', 'description': '새로운 &amp; 정보',
        'originallink': 'https://example.com/news', 'link': 'https://news.naver.com/test',
        'pubDate': 'Wed, 30 Sep 2026 09:00:00 +0900',
    }]})
    monkeypatch.setattr(providers, 'api', call)
    result = asyncio.run(providers.discover('AI'))
    assert call.call_args.args == ('GET', host)
    assert call.call_args.kwargs['headers'][header] == 'test-secret'
    assert 'test-secret' not in str(call.call_args.kwargs['params'])
    assert result['warnings'] == []
    item = result['items'][0]
    assert item['title'] == 'AI 발표'
    assert item['url'] == 'https://example.com/news'
    assert item['source'] == '뉴스' and item['views'] is None


def test_unknown_mode_makes_no_external_request(monkeypatch):
    monkeypatch.setenv('NAVER_CLIENT_ID', 'test-id')
    monkeypatch.setenv('NAVER_CLIENT_SECRET', 'test-secret')
    monkeypatch.setenv('NAVER_API_MODE', 'typo')
    monkeypatch.delenv('YOUTUBE_API_KEY', raising=False)
    call = AsyncMock()
    monkeypatch.setattr(providers, 'api', call)
    result = asyncio.run(providers.discover('AI'))
    call.assert_not_called()
    assert result['items'] == [] and 'NAVER_API_MODE' in result['warnings'][0]

def test_freeform_news_query_does_not_use_category_lookup(monkeypatch):
    monkeypatch.setenv('NAVER_CLIENT_ID','test-id')
    monkeypatch.setenv('NAVER_CLIENT_SECRET','test-secret')
    monkeypatch.setenv('NAVER_API_MODE','hub')
    monkeypatch.setenv('YOUTUBE_API_KEY','test-youtube')
    call=AsyncMock(return_value={'items':[]})
    monkeypatch.setattr(providers,'api',call)
    result=asyncio.run(providers.discover('AG 병역특례'))
    assert result['items']==[] and call.call_count==1
    assert call.call_args.kwargs['params']['query']=='AG 병역특례'

def test_naver_article_div_without_paragraph_tags_is_extracted(monkeypatch):
    body='도서관 운영 시간이 바뀝니다. 조건과 시행 날짜를 확인하세요. '*8
    async def fetch(url):return ('<html><nav>메뉴</nav><div id="dic_area">'+body+'</div></html>').encode(),'text/html',url
    monkeypatch.setattr(providers,'fetch_public',fetch)
    result=asyncio.run(providers.extract('https://n.news.naver.com/article/001/0001'))
    assert body.strip() in result['text'] and '메뉴' not in result['text']
