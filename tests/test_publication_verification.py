import asyncio
import pytest
from app import publishing, storage as st
from test_studio import client, generate, configure_instagram

@pytest.mark.parametrize('case',['verified','missing_child','lookup_failed'])
def test_live_readback_never_republishes_or_changes_published_state(client,monkeypatch,case):
    configure_instagram(monkeypatch)
    post=generate(client,count=3)
    post.update(status='published',instagram_id='confirmed-media',published_at=st.now())
    st.save(post)
    calls=[]
    async def remote(method,url,**kwargs):
        calls.append((method,url))
        if case=='lookup_failed':raise RuntimeError('temporary lookup failure')
        return {'id':'confirmed-media','permalink':'https://www.instagram.com/p/example/',
                'media_type':'CAROUSEL_ALBUM','timestamp':'2026-10-15T09:00:00+0000',
                'children':{'data':[{'id':str(i)} for i in range(2 if case=='missing_child' else 3)]}}
    monkeypatch.setattr(publishing,'api',remote)
    result=asyncio.run(publishing.verify_published(post))
    assert result['status']==('verified' if case=='verified' else 'needs_check')
    assert st.get(post['id'])['status']=='published'
    assert len(calls)==1 and calls[0][0]=='GET'
