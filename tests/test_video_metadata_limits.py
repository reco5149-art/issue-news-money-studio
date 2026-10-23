import json
import pytest
from app import video_sources as video

@pytest.mark.parametrize('info,code',[
    ({'duration':3000,'is_live':False},'unsupported_duration'),
    ({'duration':0,'is_live':True},'live_video')])
def test_metadata_reports_actual_limit_instead_of_missing_file(tmp_path,monkeypatch,info,code):
    def run(args,*unused):
        assert '--match-filters' not in args
        (tmp_path/'source.info.json').write_text(json.dumps(info),encoding='utf-8')
    monkeypatch.setattr(video,'run',run)
    with pytest.raises(video.p.ProviderError) as caught:video.metadata('https://www.youtube.com/watch?v=abcdefghijk',tmp_path)
    assert caught.value.code==code
