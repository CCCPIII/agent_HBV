from datetime import datetime

from agents.verification_agent import VerificationAgent
from graph.monitor_graph_runtime import _verify_analysis


def test_verify_analysis_preserves_news_only_analyses():
    node = _verify_analysis(VerificationAgent())
    state = {
        "watchlist": [],
        "price_snapshots": [],
        "alerts": [],
        "catalysts": [],
        "news": [{
            "id": 101,
            "ticker": "AAPL",
            "title": "Apple launches new AI feature",
            "source_url": "https://example.com/apple-ai",
            "published_at": datetime.utcnow(),
        }],
        "analyses": [{
            "related_alert_id": None,
            "related_news_id": 101,
            "ticker": "AAPL",
            "impact_direction": "positive",
            "impact_level": "medium",
            "summary": "Product launch may support sentiment.",
            "reasoning": "Initial analysis.",
            "confidence": 0.8,
        }],
        "errors": [],
        "summary": {},
    }

    updated = node(state)

    assert len(updated["analyses"]) == 1
    assert updated["analyses"][0]["ticker"] == "AAPL"
    assert updated["analyses"][0]["confidence"] == 0.8
