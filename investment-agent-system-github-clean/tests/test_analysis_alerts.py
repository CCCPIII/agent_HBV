from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from services.alert_service import AlertService


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_analysis_alert_created_for_catalyst_signal():
    session = make_session()
    service = AlertService()

    alert = service.create_analysis_alert(session, {
        "ticker": "AAPL",
        "impact_direction": "neutral",
        "impact_level": "medium",
        "summary": "Catalyst direction is unclear from available data.",
        "reasoning": "Rule-based fallback.",
        "confidence": 0.55,
        "_context_type": "catalyst",
        "_context_title": "Apple earnings call",
        "_source_url": "https://example.com/apple-earnings",
    })

    assert alert is not None
    assert alert.alert_type == "catalyst"
    assert alert.title == "Apple earnings call"
    assert "confidence 55%" in alert.message


def test_analysis_alert_deduplicates_same_signal():
    session = make_session()
    service = AlertService()
    payload = {
        "ticker": "AAPL",
        "impact_direction": "positive",
        "impact_level": "high",
        "summary": "Strong signal.",
        "reasoning": "Test reasoning.",
        "confidence": 0.8,
        "_context_type": "news",
        "_context_title": "Apple launches new product",
        "_source_url": "https://example.com/apple-product",
    }

    first = service.create_analysis_alert(session, payload)
    second = service.create_analysis_alert(session, payload)

    assert first is not None
    assert second is not None
    assert first.id == second.id
