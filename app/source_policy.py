"""One current YouTube freshness rule for discovery, production and publishing."""
import os
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
from . import storage as st, providers as p

VERSION = 'youtube-12h-100k-v1'
MAX_AGE_HOURS = 12
MIN_VIEWS = 100_000


def config():
    return {'version': VERSION, 'max_age_hours': MAX_AGE_HOURS, 'min_views': MIN_VIEWS,
            'check_before_generation': True, 'check_before_publish': True}


def assess(video, *, now=None, at=None):
    now = now or datetime.now(st.KST)
    at = at or now
    snippet = video.get('snippet') or {}
    result = {**config(), 'checked_at': now.isoformat(), 'evaluated_at': at.isoformat(),
              'video_id': video.get('id'), 'published_at': snippet.get('publishedAt'),
              'view_count': None, 'passed': False}
    try:
        published = datetime.fromisoformat(snippet['publishedAt'].replace('Z', '+00:00'))
        if published.tzinfo is None: raise ValueError()
        views = int(video['statistics']['viewCount'])
        age = at - published
    except (KeyError, TypeError, ValueError, AttributeError):
        result['reason'] = '유튜브 게시 시각 또는 조회수를 확인하지 못했습니다.'
        return result
    result.update(view_count=views, age_hours=round(age.total_seconds()/3600, 3),
                  expires_at=(published+timedelta(hours=MAX_AGE_HOURS)).isoformat())
    if (video.get('status') or {}).get('privacyStatus') != 'public':
        result['reason'] = '공개된 유튜브 영상인지 확인하지 못했습니다.'
    elif published > now or not timedelta(0) <= age <= timedelta(hours=MAX_AGE_HOURS):
        result['reason'] = f'유튜브 업로드 후 {MAX_AGE_HOURS}시간 이내 조건을 충족하지 않습니다.'
    elif views < MIN_VIEWS:
        result['reason'] = '유튜브 조회수 10만 회 조건을 충족하지 않습니다.'
    else:
        result.update(passed=True, reason='업로드 후 12시간 이내 · 조회수 10만 회 이상 확인')
    return result


def require_eligible(video, *, at=None):
    result = assess(video, at=at)
    if not result['passed']:
        raise p.ProviderError(result['reason'], code='source_ineligible')
    return result


async def fetch_video(video_id):
    p.require('YOUTUBE_API_KEY')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id or ''):
        raise p.ProviderError('원본 유튜브 영상 주소를 확인하지 못했습니다.', code='source_ineligible')
    result = await p.api('GET', 'https://www.googleapis.com/youtube/v3/videos', params={
        'key': os.environ['YOUTUBE_API_KEY'], 'part': 'snippet,statistics,status', 'id': video_id})
    return next((x for x in result.get('items', []) if x.get('id') == video_id), {'id': video_id})


async def refresh(video):
    fresh = await fetch_video(video['id'])
    evidence = require_eligible(fresh)
    video.clear()
    video.update(fresh, selection_evidence=evidence)
    return video


def applies(post):
    return bool(post.get('automation_day') or post.get('cadence_managed') or post.get('source_policy_required'))


def video_id(url):
    parsed = urlparse(url or '')
    host = (parsed.hostname or '').lower()
    if host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        return (parse_qs(parsed.query).get('v') or [parsed.path.split('/')[-1]])[0]
    if host == 'youtu.be': return parsed.path.strip('/')
    return ''


async def ensure_publishable(post):
    if not applies(post): return None
    try:
        video = await fetch_video(video_id(post.get('source_url')))
        result = assess(video)
    except (p.ProviderError, OSError) as exc:
        post['source_eligibility'] = {**config(), 'passed': False, 'checked_at': st.now(),
                                     'reason': '게시 직전 원본 시각·조회수 조회 실패'}
        st.save(post)
        raise
    post['source_eligibility'] = result
    st.save(post)
    if not result['passed']:
        raise p.ProviderError(result['reason'], code='source_ineligible')
    return video


def ensure_still_current(post, video):
    """Container preparation can cross the age boundary; check before sending."""
    result = assess(video)
    post['source_eligibility'] = result
    st.save(post)
    if not result['passed']:
        raise p.ProviderError(result['reason'], code='source_ineligible')
