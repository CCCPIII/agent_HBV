from graph.stock_monitor_graph import StockMonitorGraph
from services.alert_service import AlertService
from services.catalyst_service import CatalystService
from services.ipo_service import IPOService
from services.market_data_service import MarketDataService
from services.news_service import NewsService
from services.notification_service import NotificationService


def main() -> None:
    graph = StockMonitorGraph(
        market_data_service=MarketDataService(),
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
