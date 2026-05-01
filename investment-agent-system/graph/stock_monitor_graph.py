from datetime import datetime
from typing import Any, Dict, List

from app.db import SessionLocal
from app.models import AgentAnalysis, Alert, CatalystEvent, NewsItem, PriceSnapshot, WatchlistItem
from agents.catalyst_agent import CatalystAgent
from agents.impact_agent import ImpactAgent
from agents.ipo_agent import IPOAgent
from agents.news_agent import NewsAgent
from agents.verification_agent import VerificationAgent
from services.alert_service import AlertService
from services.catalyst_service import CatalystService
from services.ipo_service import IPOService
from services.market_data_service import MarketDataService
from services.news_service import NewsService
from services.notification_service import NotificationService


class Graph:
    def __init__(self):
        self.nodes = []

    def add_node(self, name: str, func):
        self.nodes.append((name, func))

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        for name, func in self.nodes:
            state = func(state)
        return state


class StockMonitorGraph:
    def __init__(
        self,
        market_data_service: MarketDataService,
        catalyst_service: CatalystService,
        news_service: NewsService,
        ipo_service: IPOService,
        alert_service: AlertService,
        notification_service: NotificationService,
    ):
        self.market_data_service = market_data_service
        self.catalyst_service = catalyst_service
        self.news_service = news_service
        self.ipo_service = ipo_service
        self.alert_service = alert_service
        self.notification_service = notification_service
        self.impact_agent = ImpactAgent()
        self.verification_agent = VerificationAgent()
        self.catalyst_agent = CatalystAgent()
        self.news_agent = NewsAgent()
        self.ipo_agent = IPOAgent()
        self.graph = Graph()
        self.graph.add_node("fetch_watchlist", self.fetch_watchlist)
        self.graph.add_node("fetch_market_data", self.fetch_market_data)
        self.graph.add_node("detect_price_alerts", self.detect_price_alerts)
        self.graph.add_node("fetch_catalysts", self.fetch_catalysts)
        self.graph.add_node("fetch_news", self.fetch_news)
        self.graph.add_node("analyze_impact", self.analyze_impact)
        self.graph.add_node("verify_analysis", self.verify_analysis)
        self.graph.add_node("create_alerts", self.create_alerts)
        self.graph.add_node("send_notifications", self.send_notifications)
        self.graph.add_node("persist_results", self.persist_results)

    def run_once(self) -> Dict[str, Any]:
        state = {
            "watchlist": [],
            "price_snapshots": [],
            "alerts": [],
            "catalysts": [],
            "news": [],
            "analyses": [],
            "errors": [],
        }
        try:
            state = self.graph.run(state)
        except Exception as exc:
            state["errors"].append(str(exc))
        return state

    def fetch_watchlist(self, state: Dict[str, Any]) -> Dict[str, Any]:
        with SessionLocal() as session:
            state["watchlist"] = session.query(WatchlistItem).filter(WatchlistItem.active == True).all()
        return state

    def fetch_market_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        snapshots = []
        with SessionLocal() as session:
            for item in state["watchlist"]:
                quote = self.market_data_service.get_quote(item.ticker)
                snapshot = PriceSnapshot(
                    ticker=item.ticker,
                    price=quote["price"],
                    previous_close=quote["previous_close"],
                    percent_change=quote["percent_change"],
                    currency=quote.get("currency", "USD"),
                    captured_at=datetime.utcnow(),
                )
                session.add(snapshot)
                session.commit()
                session.refresh(snapshot)
                snapshots.append(snapshot)
        state["price_snapshots"] = snapshots
        return state

    def detect_price_alerts(self, state: Dict[str, Any]) -> Dict[str, Any]:
        alerts = []
        with SessionLocal() as session:
            for item in state["watchlist"]:
                snapshot = next((s for s in state["price_snapshots"] if s.ticker == item.ticker), None)
                if snapshot is None:
                    continue
                alert = self.alert_service.create_price_alert(session, item, {
                    "percent_change": snapshot.percent_change,
                    "ticker": item.ticker,
                    "alert_type": "price_move",
                    "value": snapshot.percent_change,
                    "title": f"{item.ticker} price move",
                })
                if alert:
                    alerts.append(alert)
        state["alerts"] = alerts
        return state

    def fetch_catalysts(self, state: Dict[str, Any]) -> Dict[str, Any]:
        with SessionLocal() as session:
            state["catalysts"] = [
                self.catalyst_agent.normalize({
                    "ticker": c.ticker,
                    "title": c.title,
                    "catalyst_type": c.catalyst_type,
                    "event_date": c.event_date,
                    "source_url": c.source_url,
                    "confidence": c.confidence,
                    "source": "database",
                })
                for c in self.catalyst_service.get_upcoming_catalysts(session)
            ]
        return state

    def fetch_news(self, state: Dict[str, Any]) -> Dict[str, Any]:
        with SessionLocal() as session:
            tickers = [item.ticker for item in state["watchlist"]]
            state["news"] = [
                self.news_agent.normalize({
                    "ticker": n.ticker,
                    "sector": n.sector,
                    "title": n.title,
                    "summary": n.summary,
                    "source": n.source,
                    "source_url": n.source_url,
                    "published_at": n.published_at,
                })
                for n in self.news_service.get_news(session, tickers=tickers)
            ]
            self.ipo_service.seed_demo_ipo(session)
        return state

    def analyze_impact(self, state: Dict[str, Any]) -> Dict[str, Any]:
        analyses = []
        for alert in state["alerts"]:
            payload = {
                "related_alert_id": alert.id,
                "ticker": alert.ticker,
                "alert_type": alert.alert_type,
                "value": alert.message and float(alert.message.split()[2].replace("%", "")) if "%" in alert.message else 0.0,
                "title": alert.title,
                "source_url": alert.source_url,
            }
            analysis = self.impact_agent.analyze(payload)
            analyses.append(analysis)
        state["analyses"] = analyses
        return state

    def verify_analysis(self, state: Dict[str, Any]) -> Dict[str, Any]:
        verified = []
        for analysis, alert in zip(state["analyses"], state["alerts"]):
            item = {
                "source_url": alert.source_url,
                "event_date": None,
                "title": alert.title,
            }
            verified.append(self.verification_agent.verify(analysis, item))
        state["analyses"] = verified
        return state

    def create_alerts(self, state: Dict[str, Any]) -> Dict[str, Any]:
        with SessionLocal() as session:
            saved = []
            for analysis in state["analyses"]:
                saved.append(self.alert_service.save_analysis(session, analysis))
        state["analyses"] = saved
        return state

    def send_notifications(self, state: Dict[str, Any]) -> Dict[str, Any]:
        for alert in state["alerts"]:
            self.notification_service.notify({
                "title": alert.title,
                "message": alert.message,
                "ticker": alert.ticker,
                "alert_type": alert.alert_type,
            })
        return state

    def persist_results(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["summary"] = {
            "watchlist_count": len(state["watchlist"]),
            "price_snapshots": len(state["price_snapshots"]),
            "alerts": len(state["alerts"]),
            "analyses": len(state["analyses"]),
        }
        return state
