from datetime import date
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import CatalystEvent
from services.catalyst_service import CatalystService
from services.external_api_guard import ExternalAPIGuard


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_sync_watchlist_catalysts_ingests_finnhub_earnings_and_dividends(monkeypatch):
    session = make_session()
    service = CatalystService()
    monkeypatch.setattr("services.catalyst_service.external_api_guard", ExternalAPIGuard())

    monkeypatch.setattr("services.catalyst_service.settings.catalyst_provider", "finnhub")
    monkeypatch.setattr("services.catalyst_service.settings.finnhub_api_key", "demo-key")
    monkeypatch.setattr("services.catalyst_service.settings.catalyst_lookahead_days", 30)

    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, params=None, timeout=None):
        if "calendar/earnings" in url:
            return DummyResponse({
                "earningsCalendar": [
                    {"date": "2026-05-20"}
                ]
            })
        if "stock/dividend" in url:
            return DummyResponse([
                {"date": "2026-05-22", "amount": 0.24}
            ])
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("services.catalyst_service.requests.get", fake_get)
    monkeypatch.setattr(CatalystService, "_ingest_yfinance", lambda self, session, item, start_date, end_date: None)

    watchlist = [SimpleNamespace(ticker="AAPL")]
    events = service.sync_watchlist_catalysts(session, watchlist)

    assert len(events) == 2
    assert {event.catalyst_type for event in events} == {"earnings", "dividend"}
    assert session.query(CatalystEvent).count() == 2


def test_sync_watchlist_catalysts_deduplicates_existing_records(monkeypatch):
    session = make_session()
    monkeypatch.setattr("services.catalyst_service.external_api_guard", ExternalAPIGuard())
    session.add(
        CatalystEvent(
            ticker="AAPL",
            title="AAPL earnings report",
            catalyst_type="earnings",
            event_date=date(2026, 5, 20),
            source_url="https://example.com",
            confidence=0.8,
        )
    )
    session.commit()

    service = CatalystService()
    monkeypatch.setattr("services.catalyst_service.settings.catalyst_provider", "finnhub")
    monkeypatch.setattr("services.catalyst_service.settings.finnhub_api_key", "demo-key")
    monkeypatch.setattr("services.catalyst_service.settings.catalyst_lookahead_days", 30)

    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, params=None, timeout=None):
        if "calendar/earnings" in url:
            return DummyResponse({
                "earningsCalendar": [
                    {"date": "2026-05-20"}
                ]
            })
        return DummyResponse([])

    monkeypatch.setattr("services.catalyst_service.requests.get", fake_get)
    monkeypatch.setattr(CatalystService, "_ingest_yfinance", lambda self, session, item, start_date, end_date: None)

    watchlist = [SimpleNamespace(ticker="AAPL")]
    events = service.sync_watchlist_catalysts(session, watchlist)

    assert len(events) == 1
    assert session.query(CatalystEvent).count() == 1
    assert events[0].confidence == 0.95


def test_build_calendar_returns_urgent_summary_and_enriched_items(monkeypatch):
    session = make_session()
    service = CatalystService()
    monkeypatch.setattr("services.catalyst_service.external_api_guard", ExternalAPIGuard())

    monkeypatch.setattr("services.catalyst_service.settings.catalyst_provider", "finnhub")
    monkeypatch.setattr("services.catalyst_service.settings.finnhub_api_key", "demo-key")
    monkeypatch.setattr("services.catalyst_service.settings.catalyst_lookahead_days", 30)

    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, params=None, timeout=None):
        if "calendar/earnings" in url:
            return DummyResponse({
                "earningsCalendar": [
                    {
                        "date": date.today().isoformat(),
                        "epsEstimate": 0.4619,
                        "revenueEstimate": 186495992,
                    }
                ]
            })
        if "stock/dividend" in url:
            return DummyResponse([])
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("services.catalyst_service.requests.get", fake_get)
    monkeypatch.setattr(CatalystService, "_ingest_yfinance", lambda self, session, item, start_date, end_date: None)

    payload = service.build_calendar(
        session=session,
        watchlist=[SimpleNamespace(ticker="BL")],
        ticker="all",
        catalyst_type="all",
        window_days=7,
        refresh=True,
    )

    assert payload["summary"]["urgent_this_week_count"] == 1
    assert "BL" in payload["summary"]["headline"]
    item = payload["items"][0]
    assert item["source"] == "finnhub"
    assert "EPS est" in item["notes"]
    assert item["days_until"] == 0


def test_sync_watchlist_catalysts_resolves_hk_alias(monkeypatch):
    session = make_session()
    service = CatalystService()
    monkeypatch.setattr("services.catalyst_service.external_api_guard", ExternalAPIGuard())

    monkeypatch.setattr("services.catalyst_service.settings.catalyst_provider", "finnhub")
    monkeypatch.setattr("services.catalyst_service.settings.finnhub_api_key", "demo-key")
    monkeypatch.setattr("services.catalyst_service.settings.catalyst_lookahead_days", 30)

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
        if "calendar/earnings" in url and params["symbol"] in {"0700.HK", "700.HK"}:
            return DummyResponse({"error": "forbidden"})
        if "calendar/earnings" in url and params["symbol"] == "TCEHY":
            return DummyResponse({
                "earningsCalendar": [
                    {"date": "2026-05-13", "epsEstimate": 7.3947, "revenueEstimate": 200721091903}
                ]
            })
        if "stock/dividend" in url:
            return DummyResponse([])
        raise AssertionError(f"Unexpected URL: {url} params={params}")

    monkeypatch.setattr("services.catalyst_service.requests.get", fake_get)
    monkeypatch.setattr(CatalystService, "_ingest_yfinance", lambda self, session, item, start_date, end_date: None)

    watchlist = [SimpleNamespace(ticker="0700.HK", company_name="Tencent Holdings")]
    events = service.sync_watchlist_catalysts(session, watchlist)

    assert len(events) == 1
    assert events[0].ticker == "0700.HK"
    assert events[0].event_date.isoformat() == "2026-05-13"
