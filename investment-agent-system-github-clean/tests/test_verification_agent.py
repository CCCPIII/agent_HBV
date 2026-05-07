from agents.verification_agent import VerificationAgent


def test_verification_agent_lowers_confidence_without_source():
    agent = VerificationAgent()
    analysis = {"confidence": 0.8, "reasoning": "Initial reasoning."}
    item = {"title": "Market update", "source_url": None, "event_date": None}
    verified = agent.verify(analysis, item)
    assert verified["confidence"] <= 0.8
    assert "Source is missing" in verified["reasoning"]
