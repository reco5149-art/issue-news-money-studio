"""User publication consent is separate from copyright/licence evidence."""
from . import storage as st, quality
from .hook_policy import HOOK_VERSION
from .copy_prompts import STORY_VERSION
from . import overlay_guard
from .cadence import parse

KEY='automatic_publication_policy'

def config():
    return {**{'enabled':False,'acknowledge_unverified_rights':False},**st.setting(KEY,{}),
            'hook_policy_version':HOOK_VERSION,'story_policy_version':STORY_VERSION}

def automatic_eligible(post):
    c=config()
    try:
        return bool(c['enabled'] and c['acknowledge_unverified_rights'] and c.get('requested_by')=='user'
                    and c.get('approval_id') and c.get('approved_at')
                    and parse(post['created_at'])>=parse(c['approved_at'])
                    and post.get('automation_day') and post.get('image_mode')=='video'
                    and post.get('hook_policy_version')==HOOK_VERSION
                    and post.get('story_policy_version')==STORY_VERSION
                    and post.get('facts_checked')
                    and ((post.get('source_verification') or {}).get('review') or {}).get('passed') is True
                    and post.get('slides') and all(s.get('asset_id') and (st.ASSETS/(s['asset_id']+'.jpg')).is_file() for s in post['slides']))
    except (KeyError,ValueError,TypeError):return False

def record_automatic(post):
    if not automatic_eligible(post):return False
    quality.ensure_passed(post)
    # Automation cannot inherit a manual quality-score override.
    if not all(quality.passed(c) for c in quality.Review.model_validate({'cards':post['quality']['cards']}).cards):return False
    overlay=post.get('overlay_review') or {}
    if not (overlay.get('status')=='passed' and overlay.get('version')==overlay_guard.VERSION
            and overlay.get('fingerprint')==overlay_guard.digest(overlay_guard.files(post))):return False
    post['automatic_publication_consent']={'at':st.now(),'approval_id':config()['approval_id'],
                                          'fingerprint':quality.fingerprint(post),'rights_verified':bool(post.get('rights_checked'))}
    return True

def authorized(post):
    try:
        digest=quality.fingerprint(post)
        manual=post.get('manual_publication_consent') or {}
        if manual.get('at') and manual.get('fingerprint')==digest:return True
        consent=post.get('automatic_publication_consent') or {}
        return bool(automatic_eligible(post) and consent.get('at')
                    and consent.get('approval_id')==config().get('approval_id')
                    and consent.get('fingerprint')==digest)
    except (KeyError,ValueError,TypeError,OSError):return False
