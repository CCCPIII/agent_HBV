from datetime import datetime
from typing import Dict, List, Optional

from app.models import NewsItem
from sqlalchemy.orm import Session


class NewsService:
    """Fetch or generate news summaries for tickers and sectors."""

    def get_news(self, session: Session, tickers: Optional[List[str]] = None, sectors: Optional[List[str]] = None) -> List[NewsItem]:
        query = session.query(NewsItem)
        if tickers:
            query = query.filter(NewsItem.ticker.in_([ticker.upper() for ticker in tickers]))
        if sectors:
            query = query.filter(NewsItem.sector.in_(sectors))
        return query.order_by(NewsItem.published_at.desc()).limit(50).all()

    def seed_demo_news(self, session: Session) -> None:
        if session.query(NewsItem).count() > 0:
            return

        demo = [
            NewsItem(
                ticker="AAPL",
                sector="Technology",
                title="Apple ramps up product event expectations",
                summary="Analysts note that Apple may announce new hardware next quarter.",
                source="Demo News",
                source_url="https://example.com/apple-event",
                published_at=datetime.utcnow(),
            ),
            NewsItem(
                ticker=None,
                sector="Technology",
                title="Semiconductor demand remains strong",
                summary="Market watchers highlight strong chip demand in 2026.",
                source="Demo News",
                source_url="https://example.com/semiconductors",
                published_at=datetime.utcnow(),
            ),
        ]
        session.add_all(demo)
        session.commit()
