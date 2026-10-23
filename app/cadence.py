"""KST publishing windows and reservations; no network calls or fabricated reviews."""
from collections import Counter
from datetime import datetime, timedelta
from . import storage as st
from .models import PostingCadence

KEY = 'posting_cadence'
ACTIVE = {'scheduled', 'published', 'publishing', 'needs_check'}

def config():
    return {**PostingCadence().model_dump(), **st.setting(KEY, {})}

def daily_limit():
    c = config()
    return c['daily_limit'] if c['enabled'] else 10

def parse(value):
    dt = datetime.fromisoformat(value)
    return (dt if dt.tzinfo else dt.replace(tzinfo=st.KST)).astimezone(st.KST)

def quiet(at):
    return 1 <= at.astimezone(st.KST).hour < 6

def event_time(post):
    value = post.get('published_at') if post['status'] == 'published' else post.get('scheduled_at')
    return parse(value) if value else None

def slots(day, c):
    result = []
    midnight = datetime.combine(day, datetime.min.time(), st.KST)
    for start in range(c['start_hour'] * 60, 1440, c['batch_interval']):
        for i in range(c['batch_size']):
            minute = start + i * c['item_interval']
            if minute >= 1440:
                continue
            at = midnight + timedelta(minutes=minute)
            if not quiet(at):
                result.append(at)
    return result[:c['daily_limit']]

def plan(posts, existing, now, c):
    """Preserve supplied order, skip occupied slots, and roll excess into later days."""
    if not posts:
        return []
    now = now.astimezone(st.KST)
    ids = {p['id'] for p in posts}
    occupied = [event_time(p) for p in existing if p['id'] not in ids and p['status'] in ACTIVE]
    occupied = [at for at in occupied if at]
    counts = Counter(at.date() for at in occupied)
    result = []
    gap = timedelta(minutes=c['item_interval'])
    for offset in range(366):
        day = now.date() + timedelta(days=offset)
        for at in slots(day, c):
            if at <= now or counts[day] >= c['daily_limit']:
                continue
            if any(abs(at - taken) < gap for taken in occupied):
                continue
            result.append({'id': posts[len(result)]['id'], 'at': at.isoformat()})
            occupied.append(at)
            counts[day] += 1
            if len(result) == len(posts):
                return result
    raise ValueError('예약 가능한 시간대를 찾지 못했습니다.')

def save_reservations(posts, reservations):
    mapping = {p['id']:p for p in posts}
    # All validation is completed by caller, and all writes commit together.
    with st.db() as conn:
        import json
        for row in reservations:
            post = mapping[row['id']]
            post.update(status='scheduled', scheduled_at=row['at'], error='', cadence_managed=True)
            conn.execute('UPDATE posts SET body=?,status=?,scheduled_at=? WHERE id=?',
                         (json.dumps(post, ensure_ascii=False), 'scheduled', row['at'], post['id']))

def ready_new_posts(posts, c, ensure_passed):
    if not c.get('enabled') or not c.get('enabled_at'):
        return []
    result = []
    for post in posts:
        if post['status'] != 'draft' or post.get('trashed_at') or post.get('auto_schedule_excluded'):
            continue
        if not post.get('facts_checked') or not post.get('rights_checked') or post.get('ratio') == '9:16':
            continue
        if parse(post['created_at']) < parse(c['enabled_at']):
            continue  # Enabling never publishes the pre-existing library.
        try:
            ensure_passed(post)
        except ValueError:
            continue
        result.append(post)
    return sorted(result, key=lambda p:p['created_at'])
