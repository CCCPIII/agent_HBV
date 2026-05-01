from datetime import date
from typing import Any, Dict, List

from app.models import CatalystEvent
from sqlalchemy.orm import Session

CATALYST_TYPES = [
    "earnings",
    "dividend",
    "stock_split",
    "investor_day",
    "company_event",
    "ipo",
    "regulatory",
    "other",
]


class CatalystService:
    """Manage catalyst events and support demo/placeholder sources."""

    def get_upcoming_catalysts(self, session: Session) -> List[CatalystEvent]:
        return session.query(CatalystEvent).order_by(CatalystEvent.event_date).all()

    def normalize(self, event: CatalystEvent) -> Dict[str, Any]:
        return {
            "id": event.id,
            "ticker": event.ticker,
            "title": event.title,
            "catalyst_type": event.catalyst_type,
            "event_date": event.event_date.isoformat(),
            "source_url": event.source_url,
            "confidence": event.confidence,
        }

    def seed_demo_catalysts(self, session: Session) -> None:
        if session.query(CatalystEvent).count() > 0:
            return
        demo = [
            CatalystEvent(
                ticker="AAPL",
                title="Apple earnings call",
                catalyst_type="earnings",
                event_date=date.today(),
                source_url="https://www.apple.com/investor/",
                confidence=0.9,
            ),
            CatalystEvent(
                ticker="005930.KS",
                title="Samsung investor day",
                catalyst_type="investor_day",
                event_date=date.today(),
                source_url="https://www.samsung.com/",
                confidence=0.8,
            ),
        ]
        session.add_all(demo)
        session.commit()
