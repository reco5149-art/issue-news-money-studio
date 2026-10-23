"""Shared publication safeguards and evidence-based operational status."""
from collections import Counter
from datetime import datetime, timedelta
from PIL import Image
from . import storage as st, cadence, source_policy, quality, overlay_guard
from .providers import ProviderError
from .bold_render import HEADLINE_COLOR_POLICY
from .frame_cleanup import VERSION as FRAME_POLICY

VERSION = 'publication-guards-20261016-v1'
LOADED_AT = st.now()


def ensure_send_allowed(post):
    current = st.get(post['id']) or post
    if current.get('status') in ('published', 'publishing', 'needs_check') or current.get('instagram_id'):
        raise ProviderError('이미 게시됐거나 게시 결과 확인이 필요한 콘텐츠입니다. 다시 전송하지 않습니다.', code='duplicate_publish')
    now = datetime.now(st.KST)
    gap = timedelta(minutes=cadence.config()['item_interval'])
    for other in st.posts():
        if other['id'] == post['id']: continue
        if other.get('status') in ('publishing', 'needs_check'):
            raise ProviderError('앞선 게시 결과가 확인되지 않았습니다. 실제 게시 여부를 확인한 뒤 진행하세요.', code='publish_uncertain')
        if other.get('status') != 'published' or not other.get('published_at'): continue
        next_at = cadence.parse(other['published_at']) + gap
        if now < next_at:
            raise ProviderError('게시물 사이 최소 '+str(cadence.config()['item_interval'])+
                                '분 간격이 필요합니다. 다음 가능 시각: '+next_at.strftime('%H:%M:%S'), code='publish_spacing')


def ensure_photos(post):
    slides = post.get('slides') or []
    if not slides: raise ProviderError('게시할 카드 이미지가 없습니다.', code='missing_photo')
    paths = [st.MEDIA/post['id']/f'{i+1:02}.jpg' for i in range(len(slides))]
    if post.get('automation_day'):
        if post.get('image_mode') != 'video' or any(not s.get('asset_id') for s in slides):
            raise ProviderError('자동 제작물은 모든 카드에 유튜브 캡처 사진이 필요합니다.', code='missing_photo')
        paths += [st.ASSETS/(s['asset_id']+'.jpg') for s in slides]
    try:
        for path in paths:
            with Image.open(path) as image: image.verify()
    except (OSError, ValueError) as exc:
        raise ProviderError('게시 이미지 또는 원본 사진 파일이 없거나 손상됐습니다.', code='missing_photo') from exc


def record_preflight(post):
    post['publication_preflight'] = {
        'version': VERSION, 'status': 'passed', 'checked_at': st.now(),
        'content_fingerprint': quality.fingerprint(post),
        'overlay_fingerprint': overlay_guard.digest(overlay_guard.files(post)),
        'source_check_required': source_policy.applies(post),
        'source_check': post.get('source_eligibility') if source_policy.applies(post) else None,
        'public_images_matched': True,
    }
    st.save(post)


def hold_overview(journal,posts):
    resolved={p.get('source_url') for p in posts if p.get('source_url') and p.get('status')=='published'
              and (p.get('publication_verification') or {}).get('status')=='verified'}
    excluded={x.get('source_url') for x in journal.get('excluded_candidates',[]) if x.get('source_url')}
    active=[];seen=set();recovered=set()
    for i,item in enumerate(journal.get('held',[])):
        url=item.get('source_url')
        if url and url in resolved:recovered.add(url);continue
        if url and url in excluded:continue
        identity=url or f'record:{i}'
        if identity not in seen:active.append(item);seen.add(identity)
    return {'unresolved_count':len(active),'excluded_count':len(excluded-resolved),
            'recovered_published_count':len(recovered),'historical_record_count':len(journal.get('held',[])),
            'active_holds':active}


def snapshot(journal, posts, *, source_limit, video_attempt_limit):
    counts = journal.get('delivery_counts') or {}
    holds = hold_overview(journal,posts)
    reasons = Counter(x.get('reason') or '사유 미기록' for x in holds['active_holds'])
    delivered = counts.get('published', 0)
    queued = counts.get('scheduled', 0) + counts.get('publishing', 0)
    stalled = holds['unresolved_count'] >= 3 and not delivered and not queued
    attention = bool(journal.get('blocker_code') or journal.get('status') in ('failed','needs_action','blocked') or stalled)
    today = datetime.now(st.KST).date().isoformat()
    today_posts = [p for p in posts if p.get('status') == 'published' and (p.get('published_at') or '')[:10] == today]
    verified = sum((p.get('publication_verification') or {}).get('status') == 'verified' for p in today_posts)
    label = ('제작 진행 확인 필요' if attention else '제작·게시 현황')
    summary = f'{label} · 오늘 자동제작분 실제 게시 {delivered}건 / 예약·전송 {queued}건 · 미해결 보류 {holds["unresolved_count"]}건 · 수집 제외 {holds["excluded_count"]}건 · 복구 후 게시 {holds["recovered_published_count"]}건'
    if reasons and attention: summary += ' · 주요 사유: ' + reasons.most_common(1)[0][0]
    return {
        'version': VERSION, 'loaded_at': LOADED_AT, 'checked_at': st.now(),
        'status': 'needs_attention' if attention else 'observing', 'summary': summary,
        'rules': {'source_policy': source_policy.config(), 'automatic_photos': 'youtube_capture_only',
            'frame_selection': FRAME_POLICY,
            'supported_video_max_seconds': 1200,
                  'headline_colors': {'version': HEADLINE_COLOR_POLICY, 'top': '#ffffff', 'bottom': '#ffe45e'},
                  'final_overlay_check': overlay_guard.VERSION, 'manual_and_auto_same_publish_guards': True,
                  'min_post_interval_minutes': cadence.config()['item_interval'],
                  'source_attempt_limit': source_limit, 'video_attempt_limit': video_attempt_limit,
                  'generation_attempt_limit': cadence.config()['daily_limit'],
                  'quota_error_requires_action': True, 'ambiguous_publish_auto_retry': False},
        'automatic_delivery_counts': counts,
        'today_published': len(today_posts), 'today_live_verified': verified,
        'hold_summary': {k:v for k,v in holds.items() if k!='active_holds'},
        'hold_reasons': [{'reason': reason, 'count': count} for reason,count in reasons.most_common()],
        'next_retry_at': journal.get('next_retry_at'),
    }
