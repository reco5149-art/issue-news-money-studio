"""Read-only checks for the existing media tunnel; never generate or publish."""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def restart_safe(status, posts, now):
    journal = status.get("autopilot") or {}
    if journal.get("status") not in ("idle", "waiting", "complete", "stopped", "failed", "blocked", "needs_action"):
        return False
    if any(p.get("status") in ("publishing", "needs_check") for p in posts):
        return False
    times = [journal.get("next_retry_at")]
    times += [p.get("scheduled_at") for p in posts if p.get("status") == "scheduled"]
    for value in filter(None, times):
        if datetime.fromisoformat(value) <= now + timedelta(minutes=2):
            return False
    return True


def verify_bytes(raw, content_type, expected):
    return content_type.lower().startswith("image/") and hashlib.sha256(raw).digest() == hashlib.sha256(expected).digest()


def check(base):
    from app import storage as st
    if not re.fullmatch(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com", base):
        raise ValueError("Unsupported managed media URL")
    post = next((p for p in st.posts() if p.get("slides") and (st.MEDIA/p["id"]/"01.jpg").is_file()), None)
    if not post:
        raise ValueError("No rendered image available for a byte check")
    expected = (st.MEDIA/post["id"]/"01.jpg").read_bytes()
    with urlopen(f'{base}/{post["id"]}/01.jpg', timeout=10) as response:
        if not verify_bytes(response.read(15_000_001), response.headers.get("Content-Type", ""), expected):
            raise ValueError("Public image differs from the local file")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--can-restart", action="store_true")
    args = parser.parse_args()
    try:
        if args.can_restart:
            from app import storage as st
            with urlopen("http://127.0.0.1:8765/api/status", timeout=10) as response:
                status = json.load(response)
            if not restart_safe(status, st.posts(), datetime.now(st.KST)):
                return 2
        else:
            from dotenv import dotenv_values
            base = args.base_url or dotenv_values(ROOT/".env").get("PUBLIC_MEDIA_BASE_URL", "")
            check(base.rstrip("/"))
        print("OK")
        return 0
    except Exception as exc:
        # Never log request headers, environment or credentials.
        print("Media check failed: " + type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
