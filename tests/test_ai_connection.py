import pytest
from app import providers as p

def test_personal_defaults(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','openai')
    monkeypatch.setenv('OPENAI_API_KEY','personal-test')
    assert p.ai_headers()=={'Authorization':'Bearer personal-test'}
    assert p.ai_url('responses')=='https://api.openai.com/v1/responses'

def test_school_isolation(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','semyung')
    monkeypatch.setenv('SEMYUNG_API_BASE_URL',p.SCHOOL_BASE)
    monkeypatch.setenv('OPENAI_API_KEY','personal-test')
    monkeypatch.delenv('SEMYUNG_API_KEY',raising=False)
    with pytest.raises(p.ProviderError):p.ai_headers()
    monkeypatch.setenv('SEMYUNG_API_KEY','school-test')
    assert p.ai_headers()=={'Authorization':'Bearer school-test'}
    assert p.ai_url('responses')==p.SCHOOL_BASE+'/responses/'
    monkeypatch.setenv('SEMYUNG_TEXT_MODEL','gpt-5.4-mini')
    assert p.ai_model()=='gpt-5.4-mini'
    assert 'school-test' not in str(p.ai_settings())
    for path in ('audio/transcriptions','images/generations'):
        with pytest.raises(p.ProviderError):p.ai_url(path)

def test_wrong_host_blocked(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','semyung')
    monkeypatch.setenv('SEMYUNG_API_BASE_URL','https://example.com')
    with pytest.raises(p.ProviderError):p.ai_url('responses')
