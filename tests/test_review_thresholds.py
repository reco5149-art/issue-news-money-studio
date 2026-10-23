import pytest
from app.quality import CardScore, passed


@pytest.mark.parametrize('changes,expected', [
    ({}, True),
    ({'hook': 9}, False),
    ({'hook': 19}, True),
    ({'sync': 24, 'hook': 25}, False),
    ({'grounding': 19, 'hook': 25}, False),
    ({'critical': True}, False),
    ({'hook': 25, 'sync': 35, 'grounding': 25}, True),
])
def test_review_threshold_boundaries(changes, expected):
    # The selected practical policy accepts 65 total; factual/image floors remain.
    score = dict(card=1, hook=10, sync=25, grounding=20, cta=10,
                 critical=False, reason='test', fix='test')
    score.update(changes)
    assert passed(CardScore(**score)) is expected
