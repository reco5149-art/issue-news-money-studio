import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('ISSUE_DATA_DIR', ROOT / 'data'))
MEDIA = DATA / 'media'
ASSETS = DATA / 'assets'
KST = timezone(timedelta(hours=9))

def now():
    return datetime.now(KST).isoformat()

def db():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA / 'studio.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init():
    MEDIA.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, body TEXT NOT NULL,
            status TEXT NOT NULL, scheduled_at TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at TEXT, message TEXT);
        CREATE TABLE IF NOT EXISTS runs (day TEXT PRIMARY KEY, status TEXT, message TEXT);
        ''')

def save(post):
    with db() as c:
        c.execute('INSERT OR REPLACE INTO posts VALUES (?,?,?,?,?)',
                  (post['id'], json.dumps(post, ensure_ascii=False), post['status'], post.get('scheduled_at'), post['created_at']))
    return post

def get(pid):
    with db() as c:
        row = c.execute('SELECT body FROM posts WHERE id=?', (pid,)).fetchone()
    return json.loads(row['body']) if row else None

def posts():
    with db() as c:
        rows = c.execute('SELECT body FROM posts ORDER BY created_at DESC').fetchall()
    return [json.loads(r['body']) for r in rows]

def setting(key, default=None):
    with db() as c:
        row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return json.loads(row['value']) if row else default

def set_setting(key, value):
    with db() as c:
        c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))

def log(message):
    with db() as c:
        c.execute('INSERT INTO events(at,message) VALUES (?,?)', (now(), message))

DEFAULT_SCHEDULE = {'enabled': False, 'hour': 8, 'daily_target': 10,
                    'categories': ['뉴스', '이슈', '연예', '경제', 'AI']}
