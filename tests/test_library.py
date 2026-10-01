import pytest
from fastapi import HTTPException
from app import storage as st
from app.library import move


@pytest.fixture
def records(tmp_path, monkeypatch):
    monkeypatch.setattr(st, 'DATA', tmp_path)
    monkeypatch.setattr(st, 'MEDIA', tmp_path/'media')
    monkeypatch.setattr(st, 'ASSETS', tmp_path/'assets')
    st.init()
    for status in ['draft','scheduled','published','publishing','needs_check']:
        st.save(dict(id=status,status=status,created_at=st.now(),scheduled_at=st.now() if status=='scheduled' else None))
    return tmp_path


def test_trash_restore_cancels_schedule_without_rescheduling(records):
    move(['draft','scheduled'])
    assert st.get('draft')['trashed_at']
    assert st.get('scheduled')['status']=='draft'
    assert st.get('scheduled')['scheduled_at'] is None
    move(['draft','scheduled'],restore=True)
    assert not st.get('draft').get('trashed_at')
    assert st.get('scheduled')['status']=='draft'


def test_published_history_and_files_preserved(records):
    media=st.MEDIA/'image.jpg';media.write_bytes(b'preserved')
    move(['published'])
    assert st.get('published')['status']=='published'
    assert media.read_bytes()==b'preserved'


@pytest.mark.parametrize('blocked',['publishing','needs_check','missing'])
def test_batch_validation_is_atomic(records,blocked):
    with pytest.raises(HTTPException):move(['draft',blocked])
    assert not st.get('draft').get('trashed_at')


def test_repeated_delete_and_restore_are_idempotent(records):
    assert move(['draft','draft'])['count']==1
    when=st.get('draft')['trashed_at']
    move(['draft']);assert st.get('draft')['trashed_at']==when
    move(['draft'],restore=True);move(['draft'],restore=True)
    assert not st.get('draft').get('trashed_at')
