from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import NewsItem
from services.news_service import NewsService


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_fetch_live_news_uses_search_provider(monkeypatch):
    session = make_session()
    service = NewsService()

    monkeypatch.setattr("services.news_service.settings.news_provider", "search")
    monkeypatch.setattr(service._search_service, "is_enabled", lambda: True)
    monkeypatch.setattr(
        service._search_service,
        "search",
        lambda query, top_k=5: [
            {
                "title": "Apple AI roadmap gains traction",
                "url": "https://example.com/apple-search",
                "snippet": "Analysts say Apple's AI roadmap is gaining traction.",
                "source": "Custom Search",
                "published_at": None,
            }
        ],
    )
    monkeypatch.setattr(
        service._search_agent,
        "analyze_results",
        lambda query, results: [
            {
                "title": results[0]["title"],
                "summary": "Search-based summary.",
                "source": results[0]["source"],
                "source_url": results[0]["url"],
                "impact_direction": "positive",
                "impact_level": "medium",
                "confidence": 0.7,
            }
        ],
    )

    items = service.fetch_live_news(
        session=session,
        ticker="AAPL",
        company_name="Apple",
        sector="Technology",
        limit=5,
    )

    assert len(items) == 1
    assert items[0]["source"] == "Custom Search"
    assert session.query(NewsItem).count() == 1
