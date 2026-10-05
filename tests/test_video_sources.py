import asyncio
import json
import pytest
from app import video_sources as v


@pytest.mark.parametrize('url', [
    'https://youtu.be/abcdefghijk?t=3',
    'https://youtube.com/shorts/abcdefghijk',
    'https://www.instagram.com/reel/abc123/?igsh=x',
    'https://www.tiktok.com/@user/video/1234567',
    'https://vm.tiktok.com/abc123/',
])
def test_supported_video_links(url):
    assert v.is_video_url(url)
    assert v.normalize_url(url).startswith('https://')


@pytest.mark.parametrize('url', [
    'http://127.0.0.1/', 'https://youtube.com.evil.com/watch?v=abcdefghijk',
    'https://user:secret@youtube.com/watch?v=abcdefghijk',
    'https://youtube.com:8080/watch?v=abcdefghijk',
    'https://instagram.com/accounts/login/', 'https://tiktok.com/@user',
    'https://youtube.com/playlist?list=123',
])
def test_rejects_non_video_and_unsafe_links(url):
    with pytest.raises(ValueError): v.normalize_url(url)


def test_vtt_rolling_captions_not_repeated():
    raw = 'WEBVTT\n\n00:00.000 --> 00:01.000\n안녕하세요\n\n00:01.000 --> 00:02.000\n안녕하세요 여러분\n\n00:02.000 --> 00:03.000\n<b>다음</b> &amp; 마지막'
    assert v.subtitle_text(raw, 'vtt') == '안녕하세요 여러분\n다음 & 마지막'


def test_json3_empty_events():
    raw = json.dumps({'events': [{}, {'segs': [{'utf8': '내용입니다'}]}, {'segs': [{'utf8': '내용입니다'}]}]})
    assert v.subtitle_text(raw, 'json3') == '내용입니다'


def test_subtitles_prevent_paid_transcription(tmp_path, monkeypatch):
    monkeypatch.setattr(v, 'metadata', lambda *a: {'title': '제목', 'uploader': '출처', 'subtitles': {'ko': [{'ext': 'vtt', 'url': 'https://example.com/sub'}]}})
    async def fetch(*a, **kw):
        return 'WEBVTT\n\n00:00.000 --> 00:03.000\n실제로 영상에서 발언한 내용을 자막에서 읽었습니다.'.encode(), '', ''
    monkeypatch.setattr(v.p, 'fetch_public', fetch)
    monkeypatch.setattr(v, 'audio_file', lambda *a: pytest.fail('subtitle path must not download audio'))
    result = asyncio.run(v.extract_video('https://youtu.be/abcdefghijk', tmp_path))
    assert result['transcript_method'] == '제공 자막'
    assert '실제로 영상' in result['text']
    assert not list(tmp_path.iterdir())


def test_audio_fallback_and_missing_speech(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    monkeypatch.setattr(v, 'metadata', lambda *a: {'title': '메타데이터 제목'})
    def audio(url, root):
        path = root / 'speech.mp3'; path.write_bytes(b'test'); return path
    monkeypatch.setattr(v, 'audio_file', audio)
    async def transcribe(method, url, **kw):
        assert url.endswith('/audio/transcriptions')
        assert kw['files']['file'][0] == 'speech.mp3'
        return {'text': '영상에서 발표자가 실제로 설명한 발언을 여기 기록합니다.'}
    monkeypatch.setattr(v.p, 'api', transcribe)
    result = asyncio.run(v.extract_video('https://instagram.com/reel/abc/', tmp_path))
    assert result['transcript_method'] == 'AI 음성 전사'
    async def silent(*a, **kw): return {'text': ''}
    monkeypatch.setattr(v.p, 'api', silent)
    with pytest.raises(ValueError, match='발언을 확보하지'):
        asyncio.run(v.extract_video('https://instagram.com/reel/abc/', tmp_path))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('duration', [None, 0, 1201, float('nan')])
def test_unknown_or_long_duration_rejected(tmp_path, monkeypatch, duration):
    (tmp_path / 'source.info.json').write_text(json.dumps({'duration': duration}))
    monkeypatch.setattr(v, 'run', lambda *a: None)
    with pytest.raises(ValueError, match='20분 이하'):
        v.metadata('https://youtu.be/abcdefghijk', tmp_path)


def test_import_route_selects_transcript_not_metadata(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setattr(main.st, 'DATA', tmp_path)
    async def extract(url, folder): return {'text': '영상 발언', 'transcript_method': '제공 자막'}
    async def wrong(url): pytest.fail('video import must not use title and description')
    monkeypatch.setattr(main, 'extract_video', extract)
    monkeypatch.setattr(main.p, 'extract', wrong)
    client = TestClient(main.app)
    response = client.post('/api/import', json={'url': 'https://youtu.be/abcdefghijk'})
    assert response.status_code == 200
    assert response.json()['transcript_method'] == '제공 자막'
