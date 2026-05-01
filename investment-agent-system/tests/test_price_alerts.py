from datetime import date

from app.models import WatchlistItem
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from services.alert_service import AlertService


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_price_alert_created_when_change_exceeds_threshold():
    session = make_session()
    item = WatchlistItem(
        ticker="AAPL",
        company_name="Apple Inc.",
        alert_threshold_percent=5.0,
        active=True,
    )
    session.add(item)
    session.commit()
    alert_service = AlertService()
    alert = alert_service.create_price_alert(session, item, {"percent_change": 5.1})
    assert alert is not None
    assert "AAPL moved +5.1%" in alert.title


def test_price_alert_not_created_when_change_below_threshold():
    session = make_session()
    item = WatchlistItem(
        ticker="AAPL",
        company_name="Apple Inc.",
        alert_threshold_percent=5.0,
        active=True,
    )
    session.add(item)
    session.commit()
    alert_service = AlertService()
    alert = alert_service.create_price_alert(session, item, {"percent_change": 4.9})
    assert alert is None
