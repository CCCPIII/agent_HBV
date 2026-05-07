from datetime import datetime
from types import SimpleNamespace

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import NewsItem
from services.news_service import NewsService


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_fetch_live_news_uses_newsapi_and_persists(monkeypatch):
    session = make_session()
    service = NewsService()

    monkeypatch.setattr("services.news_service.settings.news_provider", "newsapi")
    monkeypatch.setattr("services.news_service.settings.newsapi_key", "demo-key")
    monkeypatch.setattr("services.news_service.settings.news_language", "en")
    monkeypatch.setattr("services.news_service.settings.news_lookback_days", 7)

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "articles": [
                    {
                        "title": "Apple unveils a new device roadmap",
                        "description": "A fresh product roadmap may accelerate services revenue.",
                        "url": "https://example.com/apple-roadmap",
                        "publishedAt": "2026-05-05T08:00:00Z",
                        "source": {"name": "Example Wire"},
                    }
                ]
            }

    def fake_get(url, params=None, headers=None, timeout=None):
        assert url == "https://newsapi.org/v2/everything"
        assert headers == {"X-Api-Key": "demo-key"}
        assert "Apple" in params["q"]
        return DummyResponse()

    monkeypatch.setattr("services.news_service.requests.get", fake_get)

    result = service.fetch_live_news(
        session=session,
        ticker="AAPL",
        company_name="Apple",
        sector="Technology",
        limit=5,
    )

    assert len(result) == 1
    assert result[0]["source"] == "Example Wire"
    stored = session.query(NewsItem).filter(NewsItem.ticker == "AAPL").all()
    assert len(stored) == 1
    assert stored[0].title == "Apple unveils a new device roadmap"


def test_ingest_watchlist_news_returns_sector_fallback():
    session = make_session()
    session.add(
        NewsItem(
            ticker=None,
            sector="Technology",
            title="Chip demand stays resilient",
            summary="Sector fallback story",
            source="Demo",
            source_url="https://example.com/chips",
            published_at=datetime.utcnow(),
        )
    )
    session.commit()

    watchlist = [
        SimpleNamespace(ticker="0700.HK", company_name="Tencent", sector="Technology")
    ]

    service = NewsService()
    service._should_use_search = lambda: False
    service._should_use_newsapi = lambda: False
    service._should_use_finnhub = lambda: False
    service._ingest_yfinance = lambda *args, **kwargs: []

    items = service.ingest_watchlist_news(session, watchlist, per_item_limit=3)

    assert len(items) == 1
    assert items[0].title == "Chip demand stays resilient"


def test_fetch_live_news_uses_finnhub_and_persists(monkeypatch):
    session = make_session()
    service = NewsService()

    monkeypatch.setattr("services.news_service.settings.news_provider", "finnhub")
    monkeypatch.setattr("services.news_service.settings.finnhub_api_key", "demo-key")
    monkeypatch.setattr("services.news_service.settings.news_lookback_days", 7)

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "headline": "Apple supplier commentary lifts expectations",
                    "summary": "Supply chain checks point to stronger near-term demand.",
                    "url": "https://example.com/apple-supplier",
                    "datetime": 1778035200,
                    "source": "Finnhub Wire",
                }
            ]

    def fake_get(url, params=None, timeout=None):
        assert url == "https://finnhub.io/api/v1/company-news"
        assert params["symbol"] == "AAPL"
        assert params["token"] == "demo-key"
        return DummyResponse()

    monkeypatch.setattr("services.news_service.requests.get", fake_get)

    result = service.fetch_live_news(
        session=session,
        ticker="AAPL",
        company_name="Apple",
        sector="Technology",
        limit=5,
    )

    assert len(result) == 1
    assert result[0]["source"] == "Finnhub Wire"
    stored = session.query(NewsItem).filter(NewsItem.ticker == "AAPL").all()
    assert len(stored) == 1
    assert stored[0].title == "Apple supplier commentary lifts expectations"


def test_fetch_live_news_resolves_hk_alias_for_finnhub(monkeypatch):
    session = make_session()
    service = NewsService()

    monkeypatch.setattr("services.news_service.settings.news_provider", "finnhub")
    monkeypatch.setattr("services.news_service.settings.finnhub_api_key", "demo-key")
    monkeypatch.setattr("services.news_service.settings.news_lookback_days", 7)

    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params=None, timeout=None):
        if "search" in url:
            return DummyResponse({"result": [{"symbol": "700.HK"}]})
        if "company-news" in url and params["symbol"] == "0700.HK":
            raise requests.HTTPError("403 forbidden")
        if "company-news" in url and params["symbol"] == "700.HK":
            raise requests.HTTPError("403 forbidden")
        if "company-news" in url and params["symbol"] == "TCEHY":
            return DummyResponse([
                {
                    "headline": "Tencent ADR gains on summit hopes",
                    "summary": "Cross-market alias returned actual news.",
                    "url": "https://example.com/tencent-adr",
                    "datetime": 1778035200,
                    "source": "Finnhub Wire",
                }
            ])
        raise AssertionError(f"Unexpected URL/params: {url} {params}")

    monkeypatch.setattr("services.news_service.requests.get", fake_get)

    result = service.fetch_live_news(
        session=session,
        ticker="0700.HK",
        company_name="Tencent Holdings",
        sector="Technology",
        limit=5,
    )

    assert len(result) == 1
    assert result[0]["title"] == "Tencent ADR gains on summit hopes"
    stored = session.query(NewsItem).filter(NewsItem.ticker == "0700.HK").all()
    assert len(stored) == 1
    assert stored[0].source == "Finnhub Wire"
