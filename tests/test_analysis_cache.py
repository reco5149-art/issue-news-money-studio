from app import analysis_cache as c

def test_reuse_expiration_and_changed_input(tmp_path,monkeypatch):
    monkeypatch.setattr(c.st,'DATA',tmp_path)
    monkeypatch.setattr(c.time,'time',lambda:10000)
    k=c.key(['source','model','instructions'])
    c.put(k,{'fact':'value'})
    assert c.get(k)=={'fact':'value'}
    assert c.get(c.key(['updated source','model','instructions'])) is None
    monkeypatch.setattr(c.time,'time',lambda:10000+c.TTL)
    assert c.get(k) is None
