from datetime import date, datetime

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import CatalystEvent, NewsItem, PortfolioPosition, WatchlistItem
from services.catalyst_service import CatalystService
from services.news_service import NewsService
from services.ipo_service import IPOService


def seed_data() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        if session.query(WatchlistItem).count() == 0:
            session.add_all([
                WatchlistItem(
                    ticker="AAPL",
                    company_name="Apple Inc.",
                    exchange="NASDAQ",
                    sector="Technology",
                    alert_threshold_percent=settings.price_alert_default_threshold,
                ),
                WatchlistItem(
                    ticker="0700.HK",
                    company_name="Tencent Holdings",
                    exchange="HKEX",
                    sector="Technology",
                    alert_threshold_percent=settings.price_alert_default_threshold,
                ),
            ])

        if session.query(PortfolioPosition).count() == 0:
            session.add_all([
                PortfolioPosition(
                    ticker="AAPL",
                    company_name="Apple Inc.",
                    quantity=10,
                    average_cost=150.0,
                    currency="USD",
                    purchase_date=date(2024, 1, 10),
                ),
                PortfolioPosition(
                    ticker="0700.HK",
                    company_name="Tencent Holdings",
                    quantity=5,
                    average_cost=300.0,
                    currency="HKD",
                    purchase_date=date(2024, 3, 20),
                ),
            ])

        catalyst_service = CatalystService()
        catalyst_service.seed_demo_catalysts(session)

        news_service = NewsService()
        news_service.seed_demo_news(session)

        ipo_service = IPOService()
        ipo_service.seed_demo_ipo(session)

        session.commit()

    print("Demo data seeded.")


if __name__ == "__main__":
    seed_data()
