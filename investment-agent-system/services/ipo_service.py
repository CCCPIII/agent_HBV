from datetime import datetime, date
from typing import Dict, List

from app.models import NewsItem
from sqlalchemy.orm import Session


class IPOService:
    """Monitor IPO and Hong Kong market event data."""

    def get_recent_ipo_events(self, session: Session) -> List[Dict[str, object]]:
        today = date.today()
        return [
            {
                "title": "HKEX IPO subscription update",
                "event_type": "ipo",
                "description": "A new Hong Kong IPO subscription window is open.",
                "event_date": today,
                "source_url": "https://example.com/hkipo",
            }
        ]

    def seed_demo_ipo(self, session: Session) -> None:
        if session.query(NewsItem).filter(NewsItem.title.contains("IPO")).count() > 0:
            return
        session.add(
            NewsItem(
                ticker=None,
                sector="Financials",
                title="Hong Kong IPO watch: new listings ahead",
                summary="A new Hong Kong IPO is tracking industry interest ahead of listing.",
                source="Demo IPO News",
                source_url="https://example.com/hkipo-dashboard",
                published_at=datetime.utcnow(),
            )
        )
        session.commit()
