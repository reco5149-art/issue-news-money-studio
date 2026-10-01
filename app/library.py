"""Recoverable library removal; never delete Instagram posts or media files."""
import json
from fastapi import HTTPException
from . import storage as st


def move(ids, restore=False):
    ids = list(dict.fromkeys(ids))
    if not 1 <= len(ids) <= 100:
        raise HTTPException(400, '한 번에 1~100개를 선택하세요.')
    with st.db() as db:
        db.execute('BEGIN IMMEDIATE')
        posts = []
        for pid in ids:
            row = db.execute('SELECT body FROM posts WHERE id=?', (pid,)).fetchone()
            if not row:
                raise HTTPException(404, '선택한 콘텐츠를 찾지 못했습니다. 새로고침하세요.')
            post = json.loads(row['body'])
            if post['status'] in ('publishing', 'needs_check'):
                raise HTTPException(409, '게시 중이거나 게시 결과 확인이 필요한 콘텐츠는 삭제할 수 없습니다.')
            posts.append(post)
        for post in posts:
            if restore:
                post.pop('trashed_at', None)
            elif not post.get('trashed_at'):
                post['trashed_at'] = st.now()
                if post['status'] == 'scheduled':
                    post['status'] = 'draft'
                    post['scheduled_at'] = None
            db.execute('UPDATE posts SET body=?,status=?,scheduled_at=? WHERE id=?',
                       (json.dumps(post, ensure_ascii=False), post['status'], post.get('scheduled_at'), post['id']))
    return {'count': len(posts), 'restored': restore}
