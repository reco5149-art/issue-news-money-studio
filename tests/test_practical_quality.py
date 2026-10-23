from app.quality import CardScore,passed

def card(**kw):
    data=dict(card=1,hook=15,sync=25,grounding=20,cta=5,critical=False,reason='검증',fix='')
    return CardScore(**(data|kw))

def test_practical_quality_accepts_65_without_critical_errors():
    assert passed(card())
    assert not passed(card(hook=14))

def test_practical_quality_keeps_factual_and_image_guards():
    assert not passed(card(critical=True))
    assert not passed(card(sync=24,hook=25))
    assert not passed(card(grounding=19,hook=25))
