from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import PortfolioPosition
from services.market_data_service import MarketDataService
from services.portfolio_service import PortfolioService


class FakeMarketDataService(MarketDataService):
    def __init__(self, price_map):
        self.price_map = price_map

    def get_quote(self, ticker: str):
        return {
            "ticker": ticker,
            "price": self.price_map.get(ticker, 0.0),
            "previous_close": 0.0,
            "percent_change": 0.0,
            "currency": "USD",
        }


def test_portfolio_unrealized_pnl_calculation():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    position = PortfolioPosition(
        ticker="AAPL",
        company_name="Apple Inc.",
        quantity=10,
        average_cost=100.0,
        currency="USD",
    )
    session.add(position)
    session.commit()
    service = PortfolioService(market_data_service=FakeMarketDataService({"AAPL": 120.0}))
    summary = service.summarize([position])
    assert summary["total_market_value"] == 1200.0
    assert summary["total_cost_basis"] == 1000.0
    assert summary["total_unrealized_pnl"] == 200.0
