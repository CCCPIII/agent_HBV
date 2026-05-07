"""
Runtime monitor graph with resilient news/catalyst analysis and alert creation.
"""

from datetime import datetime
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph

from app.db import SessionLocal
from app.models import CatalystEvent, NewsItem, PortfolioPosition, PriceSnapshot, WatchlistItem
from agents.catalyst_agent import CatalystAgent
from agents.impact_agent import ImpactAgent
from agents.ipo_agent import IPOAgent
from agents.news_agent import NewsAgent
from agents.verification_agent import VerificationAgent
from services.alert_service import AlertService
from services.catalyst_service import CatalystService
from services.ipo_service import IPOService
from services.market_data_service import MarketDataService
from services.news_intelligence_service import NewsIntelligenceService
from services.news_service import NewsService
from services.notification_service import NotificationService
from services.portfolio_service import PortfolioService


class MonitorState(TypedDict):
    watchlist: List[Any]
    price_snapshots: List[Any]
    alerts: List[Any]
    catalysts: List[Any]
    news: List[Any]
    news_events: List[Any]
    analyses: List[Any]
    errors: List[str]
    summary: Dict[str, Any]


def _fetch_watchlist(
    market_data_service, catalyst_service, news_service,
    ipo_service, alert_service, notification_service,
    impact_agent, verification_agent, catalyst_agent, news_agent, ipo_agent,
):
    def node(state: MonitorState) -> MonitorState:
        with SessionLocal() as session:
            state["watchlist"] = (
                session.query(WatchlistItem)
                .filter(WatchlistItem.active == True)
                .all()
            )
        return state
    return node


def _fetch_market_data(market_data_service):
    def node(state: MonitorState) -> MonitorState:
        snapshots = []
        with SessionLocal() as session:
            for item in state["watchlist"]:
                try:
                    quote = market_data_service.get_quote(item.ticker)
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
                except Exception as exc:
                    state["errors"].append(f"market_data:{item.ticker}: {exc}")
        state["price_snapshots"] = snapshots
        return state
    return node


def _detect_price_alerts(alert_service):
    def node(state: MonitorState) -> MonitorState:
        alerts = []
        with SessionLocal() as session:
            for item in state["watchlist"]:
                snapshot = next(
                    (s for s in state["price_snapshots"] if s.ticker == item.ticker),
                    None,
                )
                if snapshot is None:
                    continue
                alert = alert_service.create_price_alert(session, item, {
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
    return node


def _fetch_catalysts(catalyst_service, catalyst_agent):
    def node(state: MonitorState) -> MonitorState:
        with SessionLocal() as session:
            catalyst_service.sync_watchlist_catalysts(session, state["watchlist"])
            if session.query(CatalystEvent).count() == 0:
                catalyst_service.seed_demo_catalysts(session)
            state["catalysts"] = [
                catalyst_agent.normalize({
                    "ticker": c.ticker,
                    "title": c.title,
                    "catalyst_type": c.catalyst_type,
                    "event_date": c.event_date,
                    "source_url": c.source_url,
                    "confidence": c.confidence,
                    "source": "database",
                })
                for c in catalyst_service.get_upcoming_catalysts(session)
            ]
        return state
    return node


def _fetch_news(news_service, news_intelligence_service, ipo_service, news_agent, ipo_agent):
    def node(state: MonitorState) -> MonitorState:
        with SessionLocal() as session:
            tickers = [item.ticker for item in state["watchlist"]]
            sectors = sorted({
                item.sector for item in state["watchlist"]
                if getattr(item, "sector", None)
            })

            try:
                news_service.ingest_watchlist_news(
                    session=session,
                    watchlist=state["watchlist"],
                    per_item_limit=5,
                )
            except Exception as exc:
                state["errors"].append(f"news_ingestion: {exc}")

            news = [
                news_agent.normalize({
                    "id": n.id,
                    "ticker": n.ticker,
                    "sector": n.sector,
                    "title": n.title,
                    "summary": n.summary,
                    "source": n.source,
                    "source_url": n.source_url,
                    "published_at": n.published_at,
                })
                for n in news_service.get_news(session, tickers=tickers, sectors=sectors)
            ]

            if not news:
                news_service.seed_demo_news(session)
                news = [
                    news_agent.normalize({
                        "id": n.id,
                        "ticker": n.ticker,
                        "sector": n.sector,
                        "title": n.title,
                        "summary": n.summary,
                        "source": n.source,
                        "source_url": n.source_url,
                        "published_at": n.published_at,
                    })
                    for n in news_service.get_news(session, tickers=tickers, sectors=sectors)
                ]

            ipo_service.seed_demo_ipo(session)
            try:
                for event in ipo_service.get_recent_ipo_events(session):
                    normalized = ipo_agent.normalize(event)
                    news.append({
                        "ticker": normalized.get("ticker"),
                        "sector": "IPO",
                        "title": normalized.get("title", ""),
                        "summary": normalized.get("description", ""),
                        "source": "IPO Monitor",
                        "source_url": normalized.get("source_url", ""),
                        "published_at": datetime.utcnow(),
                        "event_type": "ipo",
                    })
            except Exception as exc:
                state["errors"].append(f"ipo_fetch: {exc}")

            state["news"] = news
            state["news_events"] = news_intelligence_service.build_events(news)
        return state
    return node


def _analyze_impact(impact_agent):
    import re as _re

    def node(state: MonitorState) -> MonitorState:
        analyses = []

        for alert in state["alerts"]:
            value = 0.0
            if alert.message:
                match = _re.search(r"(-?\d+(?:\.\d+)?)\s*%", alert.message)
                if match:
                    try:
                        value = float(match.group(1))
                    except ValueError:
                        pass
            analysis = impact_agent.analyze({
                "related_alert_id": alert.id,
                "ticker": alert.ticker,
                "alert_type": alert.alert_type,
                "value": value,
                "title": alert.title,
                "source_url": alert.source_url,
            })
            analysis["_context_type"] = "price_move"
            analysis["_context_title"] = alert.title
            analysis["_source_url"] = alert.source_url
            analyses.append(analysis)

        for catalyst in state["catalysts"][:5]:
            analysis = impact_agent.analyze({
                "related_alert_id": None,
                "related_news_id": None,
                "ticker": catalyst.get("ticker"),
                "alert_type": catalyst.get("catalyst_type", "catalyst"),
                "value": 0.0,
                "title": catalyst.get("title", ""),
                "summary": catalyst.get("title", ""),
                "source_url": catalyst.get("source_url", ""),
            })
            analysis["_context_type"] = "catalyst"
            analysis["_context_title"] = catalyst.get("title", "")
            analysis["_source_url"] = catalyst.get("source_url", "")
            analyses.append(analysis)

        for news_item in state["news_events"][:5]:
            analysis = impact_agent.analyze({
                "related_alert_id": None,
                "related_news_id": (news_item.get("article_ids") or [None])[0],
                "ticker": news_item.get("ticker"),
                "alert_type": news_item.get("event_type", "news"),
                "event_type": news_item.get("event_type", "news"),
                "value": 0.0,
                "title": news_item.get("title", ""),
                "summary": news_item.get("summary", ""),
                "source_url": news_item.get("source_url", ""),
                "article_count": news_item.get("article_count", 1),
                "source_count": news_item.get("source_count", 1),
            })
            analysis["_context_type"] = news_item.get("event_type", "news")
            analysis["_context_title"] = news_item.get("title", "")
            analysis["_source_url"] = news_item.get("source_url", "")
            analyses.append(analysis)

        state["analyses"] = analyses
        return state
    return node


def _verify_analysis(verification_agent):
    def node(state: MonitorState) -> MonitorState:
        verified = []
        alert_by_id = {
            alert.id: alert for alert in state["alerts"]
            if getattr(alert, "id", None) is not None
        }
        news_by_id = {
            item.get("id"): item
            for item in state["news"]
            if isinstance(item, dict) and item.get("id") is not None
        }

        for index, analysis in enumerate(state["analyses"]):
            related_alert_id = analysis.get("related_alert_id")
            related_news_id = analysis.get("related_news_id")
            item = {
                "source_url": analysis.get("_source_url"),
                "event_date": None,
                "title": analysis.get("_context_title") or analysis.get("ticker") or "",
            }

            if related_alert_id in alert_by_id:
                alert = alert_by_id[related_alert_id]
                item = {
                    "source_url": alert.source_url,
                    "event_date": None,
                    "title": alert.title,
                }
            elif related_news_id in news_by_id:
                news_item = news_by_id[related_news_id]
                published_at = news_item.get("published_at")
                item = {
                    "source_url": news_item.get("source_url"),
                    "event_date": published_at.date() if hasattr(published_at, "date") else None,
                    "title": news_item.get("title", ""),
                }
            elif index < len(state["news"]):
                news_item = state["news"][index]
                if isinstance(news_item, dict):
                    published_at = news_item.get("published_at")
                    item = {
                        "source_url": news_item.get("source_url"),
                        "event_date": published_at.date() if hasattr(published_at, "date") else None,
                        "title": news_item.get("title", ""),
                    }

            verified.append(verification_agent.verify(dict(analysis), item))
        state["analyses"] = verified
        return state
    return node


def _create_alerts(alert_service):
    def node(state: MonitorState) -> MonitorState:
        with SessionLocal() as session:
            saved_analyses = []
            generated_alerts = []
            for analysis in state["analyses"]:
                generated = alert_service.create_analysis_alert(session, analysis)
                if generated and all(getattr(existing, "id", None) != generated.id for existing in state["alerts"]):
                    generated_alerts.append(generated)
                saved_analyses.append(alert_service.save_analysis(session, analysis))

            state["alerts"].extend(generated_alerts)
            state["analyses"] = saved_analyses
        return state
    return node


def _send_notifications(notification_service):
    def node(state: MonitorState) -> MonitorState:
        for alert in state["alerts"]:
            notification_service.notify({
                "title": alert.title,
                "message": alert.message,
                "ticker": alert.ticker,
                "alert_type": alert.alert_type,
            })
        return state
    return node


def _persist_results():
    def node(state: MonitorState) -> MonitorState:
        portfolio_summary = {}
        try:
            with SessionLocal() as session:
                positions = (
                    session.query(PortfolioPosition)
                    .filter(PortfolioPosition.active == True)
                    .all()
                )
            portfolio_summary = PortfolioService().summarize(positions)
        except Exception:
            pass

        state["summary"] = {
            "watchlist_count": len(state["watchlist"]),
            "price_snapshots": len(state["price_snapshots"]),
            "alerts": len(state["alerts"]),
            "analyses": len(state["analyses"]),
            "news_events": len(state["news_events"]),
            "portfolio": portfolio_summary,
        }
        return state
    return node


class StockMonitorGraph:
    """LangGraph-based stock monitoring workflow."""

    def __init__(
        self,
        market_data_service: MarketDataService,
        catalyst_service: CatalystService,
        news_service: NewsService,
        ipo_service: IPOService,
        alert_service: AlertService,
        notification_service: NotificationService,
    ):
        self.impact_agent = ImpactAgent()
        self.verification_agent = VerificationAgent()
        self.catalyst_agent = CatalystAgent()
        self.news_agent = NewsAgent()
        self.ipo_agent = IPOAgent()
        self.news_intelligence_service = NewsIntelligenceService()

        builder = StateGraph(MonitorState)
        builder.add_node("fetch_watchlist", _fetch_watchlist(
            market_data_service, catalyst_service, news_service,
            ipo_service, alert_service, notification_service,
            self.impact_agent, self.verification_agent,
            self.catalyst_agent, self.news_agent, self.ipo_agent,
        ))
        builder.add_node("fetch_market_data", _fetch_market_data(market_data_service))
        builder.add_node("detect_price_alerts", _detect_price_alerts(alert_service))
        builder.add_node("fetch_catalysts", _fetch_catalysts(catalyst_service, self.catalyst_agent))
        builder.add_node(
            "fetch_news",
            _fetch_news(
                news_service,
                self.news_intelligence_service,
                ipo_service,
                self.news_agent,
                self.ipo_agent,
            ),
        )
        builder.add_node("analyze_impact", _analyze_impact(self.impact_agent))
        builder.add_node("verify_analysis", _verify_analysis(self.verification_agent))
        builder.add_node("create_alerts", _create_alerts(alert_service))
        builder.add_node("send_notifications", _send_notifications(notification_service))
        builder.add_node("persist_results", _persist_results())

        builder.set_entry_point("fetch_watchlist")
        builder.add_edge("fetch_watchlist", "fetch_market_data")
        builder.add_edge("fetch_market_data", "detect_price_alerts")
        builder.add_edge("detect_price_alerts", "fetch_catalysts")
        builder.add_edge("fetch_catalysts", "fetch_news")
        builder.add_edge("fetch_news", "analyze_impact")
        builder.add_edge("analyze_impact", "verify_analysis")
        builder.add_edge("verify_analysis", "create_alerts")
        builder.add_edge("create_alerts", "send_notifications")
        builder.add_edge("send_notifications", "persist_results")
        builder.add_edge("persist_results", END)

        self._graph = builder.compile()

    def run_once(self) -> Dict[str, Any]:
        initial: MonitorState = {
            "watchlist": [],
            "price_snapshots": [],
            "alerts": [],
            "catalysts": [],
            "news": [],
            "news_events": [],
            "analyses": [],
            "errors": [],
            "summary": {},
        }
        try:
            return dict(self._graph.invoke(initial))
        except Exception as exc:
            initial["errors"].append(str(exc))
            return dict(initial)
