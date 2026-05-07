from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)


from graph.monitor_graph_runtime import StockMonitorGraph
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import WatchlistItem
from services.alert_service import AlertService
from services.catalyst_service import CatalystService
from services.ipo_service import IPOService
from services.market_data_service import MarketDataService
from services.news_service import NewsService
from services.notification_service import NotificationService


def _bootstrap_database() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        if session.query(WatchlistItem).count() == 0:
            from scripts.seed_demo_data import seed_data

            seed_data()


def main() -> None:
    _bootstrap_database()

    if settings.use_mock_data:
        from services.mock_market_data_service import MockMarketDataService

        market_data_service = MockMarketDataService()
    else:
        market_data_service = MarketDataService()

    graph = StockMonitorGraph(
        market_data_service=market_data_service,
        catalyst_service=CatalystService(),
        news_service=NewsService(),
        ipo_service=IPOService(),
        alert_service=AlertService(),
        notification_service=NotificationService(),
    )
    result = graph.run_once()
    print(result)


if __name__ == "__main__":
    main()
