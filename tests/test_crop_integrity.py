import asyncio,json
import pytest
from app import frame_cleanup as f

@pytest.mark.parametrize('verdicts',[
    [{'frame':1,'clean':False,'reason':'newly cut face'},{'frame':2,'clean':True,'reason':'intact'}],
    [{'frame':1,'clean':True,'reason':'intact'}]])
def test_actual_integrity_verdicts_filter_or_fail_closed(monkeypatch,verdicts):
    async def api(*args,**kwargs):
        assert kwargs['json']['text']['format']['name']=='crop_integrity_batch'
        assert len([c for c in kwargs['json']['input'][0]['content'] if c['type']=='input_image'])==4
        return {'output':[{'content':[{'type':'output_text','text':json.dumps({'frames':verdicts})}]}]}
    monkeypatch.setattr(f.p,'api',api);monkeypatch.setenv('OPENAI_API_KEY','test')
    originals=[(10,b'original1'),(20,b'original2')];crops=[(10,b'crop1'),(20,b'crop2')]
    if len(verdicts)==2:assert asyncio.run(f.review_integrity(originals,crops))==[crops[1]]
    else:
        with pytest.raises(f.p.ProviderError):asyncio.run(f.review_integrity(originals,crops))
