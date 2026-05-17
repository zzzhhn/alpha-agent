from alpha_agent.news.lm_dictionary import score_text


def test_bullish_text():
    text = "Strong beat on earnings, outstanding revenue growth, profitable expansion"
    assert score_text(text) == "bullish"


def test_bearish_text():
    text = "Severe losses, lawsuit, fraud allegations, bankruptcy risk, downgraded"
    assert score_text(text) == "bearish"


def test_neutral_text():
    text = "The company filed its quarterly report this week"
    assert score_text(text) == "neutral"


def test_empty_returns_neutral():
    assert score_text("") == "neutral"
