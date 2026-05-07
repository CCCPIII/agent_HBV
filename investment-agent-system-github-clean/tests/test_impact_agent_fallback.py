from agents.impact_agent import ImpactAgent


def test_impact_agent_fallback_positive_price_move():
    agent = ImpactAgent()
    item = {"alert_type": "price_move", "value": 5.2, "title": "AAPL moved up"}
    result = agent.analyze(item)
    assert result["impact_direction"] == "positive"
    assert result["impact_level"] == "high"
    assert result["confidence"] >= 0.7


def test_impact_agent_fallback_earnings_neutral():
    agent = ImpactAgent()
    item = {"alert_type": "earnings", "title": "Apple earnings call"}
    result = agent.analyze(item)
    assert result["impact_direction"] in {"neutral", "unknown"}
    assert result["impact_level"] == "medium"
