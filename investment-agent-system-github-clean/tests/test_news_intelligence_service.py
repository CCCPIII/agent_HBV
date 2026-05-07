from agents.impact_agent import ImpactAgent
from services.news_intelligence_service import NewsIntelligenceService


def test_news_intelligence_clusters_duplicate_company_news():
    service = NewsIntelligenceService()
    news_items = [
        {
            "id": 1,
            "ticker": "AAPL",
            "sector": "Technology",
            "title": "Apple launches AI device roadmap",
            "summary": "Apple unveils a device roadmap tied to AI features.",
            "source": "Source A",
            "source_url": "https://example.com/a",
            "published_at": "2026-05-05T09:00:00",
            "scope": "company",
        },
        {
            "id": 2,
            "ticker": "AAPL",
            "sector": "Technology",
            "title": "Apple unveils AI hardware roadmap",
            "summary": "Analysts expect the hardware launch cycle to accelerate upgrades.",
            "source": "Source B",
            "source_url": "https://example.com/b",
            "published_at": "2026-05-05T08:30:00",
            "scope": "company",
        },
    ]

    events = service.build_events(news_items)

    assert len(events) == 1
    assert events[0]["event_type"] == "product"
    assert events[0]["article_count"] == 2
    assert events[0]["source_count"] == 2
    assert events[0]["impact_direction"] == "positive"


def test_impact_agent_event_fallback_uses_cluster_context():
    analysis = ImpactAgent().analyze({
        "ticker": "AAPL",
        "event_type": "product",
        "title": "Apple launches AI device roadmap",
        "summary": "Strong launch commentary and accelerating upgrade cycle.",
        "article_count": 3,
        "source_count": 2,
        "source_url": "https://example.com/a",
    })

    assert analysis["impact_direction"] == "positive"
    assert analysis["impact_level"] == "medium"
    assert analysis["confidence"] >= 0.65
    assert "3 article" in analysis["summary"]
