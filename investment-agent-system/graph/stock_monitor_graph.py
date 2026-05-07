"""
Stock monitor workflow using LangGraph StateGraph.

The pipeline runs sequentially through these nodes:
  fetch_watchlist → fetch_market_data → detect_price_alerts
  → fetch_catalysts → fetch_news → analyze_impact
  → verify_analysis → create_alerts → send_notifications → persist_results
"""

from datetime import datetime
from typing import Any, Dict, List, TypedDict

from langgraph.graph import StateGraph, END

from app.db import SessionLocal
from app.models import (
    AgentAnalysis, Alert, CatalystEvent, NewsItem,
    PortfolioPosition, PriceSnapshot, WatchlistItem,
)
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
from services.portfolio_service import PortfolioService


# ── State schema ─────────────────────────────────────────────────────────────

class MonitorState(TypedDict):
    watchlist: List[Any]
    price_snapshots: List[Any]
    alerts: List[Any]
    catalysts: List[Any]
    news: List[Any]
    analyses: List[Any]
    errors: List[str]
    summary: Dict[str, Any]


# ── Node functions ────────────────────────────────────────────────────────────

def _fetch_watchlist(
    market_data_service, catalyst_service, news_service,
    ipo_service, alert_service, notification_service,
    impact_agent, verification_agent, catalyst_agent, news_agent, ipo_agent,
):
    def node(state: MonitorState) -> MonitorState:
        with SessionLocal() as session:
            state["watchlist"] = session.query(WatchlistItem).filter(
                WatchlistItem.active == True
            ).all()
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
                try:
                    alert = alert_service.create_price_alert(session, item, {
                        "percent_change": snapshot.percent_change,
                        "ticker": item.ticker,
                        "alert_type": "price_move",
                        "value": snapshot.percent_change,
                        "title": f"{item.ticker} price move",
                    })
                    if alert:
                        alerts.append(alert)
                except Exception as exc:
                    state["errors"].append(f"price_alert:{item.ticker}: {exc}")
        state["alerts"] = alerts
        return state
    return node


def _fetch_catalysts(catalyst_service, catalyst_agent):
    def node(state: MonitorState) -> MonitorState:
        with SessionLocal() as session:
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


def _parse_yf_news_item(raw: dict, ticker: str) -> dict:
    """Normalise a single yfinance news dict into a flat dict regardless of API version."""
    content = raw.get("content") or {}

    # title: new API has content.title, old API has top-level title
    title = (content.get("title") or raw.get("title") or "").strip()

    # summary: new API → content.summary / content.description; old API has no summary
    summary = (
        content.get("summary") or content.get("description") or ""
    ).strip()[:500]

    # source name
    source = (
        (content.get("provider") or {}).get("displayName")
        or raw.get("publisher")
        or "Yahoo Finance"
    ).strip()[:128]

    # url
    url = (
        (content.get("canonicalUrl") or {}).get("url")
        or raw.get("link")
        or ""
    ).strip()

    # published timestamp
    pub_raw = content.get("pubDate") or raw.get("providerPublishTime")
    try:
        if isinstance(pub_raw, str):
            pub_dt = datetime.fromisoformat(pub_raw.replace("Z", "+00:00")).replace(tzinfo=None)
        elif pub_raw:
            pub_dt = datetime.utcfromtimestamp(int(pub_raw))
        else:
            pub_dt = datetime.utcnow()
    except Exception:
        pub_dt = datetime.utcnow()

    return {
        "ticker": ticker,
        "title": title,
        "summary": summary or title[:200],   # fallback so NOT NULL is satisfied
        "source": source,
        "source_url": url,
        "published_at": pub_dt,
    }


def _fetch_news(news_service, ipo_service, news_agent, ipo_agent):
    def node(state: MonitorState) -> MonitorState:
        import time as _time

        with SessionLocal() as session:
            tickers = [item.ticker for item in state["watchlist"]]

            # ── Pull live news from yfinance and persist new items ──────────
            try:
                import yfinance as yf
                seen_titles = {
                    r[0] for r in session.query(NewsItem.title).all()
                }
                for idx, ticker in enumerate(tickers[:5]):   # cap to 5 tickers
                    if idx > 0:
                        _time.sleep(1.5)                     # respect rate limits
                    try:
                        raw_list = yf.Ticker(ticker).news or []
                        added = 0
                        for raw in raw_list[:10]:
                            parsed = _parse_yf_news_item(raw, ticker)
                            if not parsed["title"] or parsed["title"] in seen_titles:
                                continue
                            seen_titles.add(parsed["title"])
                            session.add(NewsItem(
                                ticker=parsed["ticker"],
                                sector=None,
                                title=parsed["title"],
                                summary=parsed["summary"],
                                source=parsed["source"],
                                source_url=parsed["source_url"],
                                published_at=parsed["published_at"],
                            ))
                            added += 1
                        if added:
                            session.commit()
                    except Exception:
                        pass
            except Exception as exc:
                state["errors"].append(f"live_news_fetch: {exc}")

            # ── Build news state from DB (includes freshly saved items) ─────
            news = [
                news_agent.normalize({
                    "ticker": n.ticker,
                    "sector": n.sector,
                    "title": n.title,
                    "summary": n.summary,
                    "source": n.source,
                    "source_url": n.source_url,
                    "published_at": n.published_at,
                })
                for n in news_service.get_news(session, tickers=tickers)
            ]

            # ── Add IPO events ───────────────────────────────────────────────
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
        return state
    return node


def _analyze_impact(impact_agent):
    import re as _re

    def node(state: MonitorState) -> MonitorState:
        analyses = []

        # ── Analyze price alerts ─────────────────────────────────────────────
        for alert in state["alerts"]:
            value = 0.0
            if alert.message:
                match = _re.search(r"(-?\d+(?:\.\d+)?)\s*%", alert.message)
                if match:
                    try:
                        value = float(match.group(1))
                    except ValueError:
                        pass
            result = impact_agent.analyze({
                "related_alert_id": alert.id,
                "ticker": alert.ticker,
                "alert_type": alert.alert_type,
                "value": value,
                "title": alert.title,
                "source_url": alert.source_url,
            })
            # Carry context for _verify_analysis (stripped before DB save)
            result["_ctx_source_url"] = alert.source_url or ""
            result["_ctx_title"] = alert.title or ""
            analyses.append(result)

        # ── Analyze recent news when no price alerts fired ───────────────────
        if not state["alerts"]:
            for news_item in state["news"][:5]:
                result = impact_agent.analyze({
                    "related_alert_id": None,
                    "ticker": news_item.get("ticker"),
                    "alert_type": news_item.get("event_type", "news"),
                    "value": 0.0,
                    "title": news_item.get("title", ""),
                    "summary": news_item.get("summary", ""),
                    "source_url": news_item.get("source_url", ""),
                })
                result["_ctx_source_url"] = news_item.get("source_url", "")
                result["_ctx_title"] = news_item.get("title", "")
                analyses.append(result)

        state["analyses"] = analyses
        return state
    return node


def _verify_analysis(verification_agent):
    def node(state: MonitorState) -> MonitorState:
        verified = []
        for analysis in state["analyses"]:
            # Pop context keys so they don't reach the DB
            item = {
                "source_url": analysis.pop("_ctx_source_url", ""),
                "event_date": None,
                "title": analysis.pop("_ctx_title", ""),
            }
            try:
                verified.append(verification_agent.verify(analysis, item))
            except Exception as exc:
                analysis["reasoning"] = analysis.get("reasoning", "") + f" [verify error: {exc}]"
                verified.append(analysis)
        state["analyses"] = verified
        return state
    return node


def _create_alerts(alert_service):
    def node(state: MonitorState) -> MonitorState:
        saved = []
        with SessionLocal() as session:
            for a in state["analyses"]:
                try:
                    saved.append(alert_service.save_analysis(session, a))
                except Exception as exc:
                    state["errors"].append(f"save_analysis:{a.get('ticker','?')}: {exc}")
        state["analyses"] = saved
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
        # Enrich summary with portfolio P&L
        portfolio_summary = {}
        try:
            with SessionLocal() as session:
                positions = session.query(PortfolioPosition).filter(
                    PortfolioPosition.active == True
                ).all()
            portfolio_summary = PortfolioService().summarize(positions)
        except Exception:
            pass

        state["summary"] = {
            "watchlist_count": len(state["watchlist"]),
            "price_snapshots": len(state["price_snapshots"]),
            "alerts": len(state["alerts"]),
            "analyses": len(state["analyses"]),
            "portfolio": portfolio_summary,
        }
        return state
    return node


# ── Graph builder ─────────────────────────────────────────────────────────────

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
        self.market_data_service = market_data_service
        self.impact_agent = ImpactAgent()
        self.verification_agent = VerificationAgent()
        self.catalyst_agent = CatalystAgent()
        self.news_agent = NewsAgent()
        self.ipo_agent = IPOAgent()

        builder = StateGraph(MonitorState)

        builder.add_node("fetch_watchlist",     _fetch_watchlist(
            market_data_service, catalyst_service, news_service,
            ipo_service, alert_service, notification_service,
            self.impact_agent, self.verification_agent,
            self.catalyst_agent, self.news_agent, self.ipo_agent,
        ))
        builder.add_node("fetch_market_data",   _fetch_market_data(market_data_service))
        builder.add_node("detect_price_alerts", _detect_price_alerts(alert_service))
        builder.add_node("fetch_catalysts",     _fetch_catalysts(catalyst_service, self.catalyst_agent))
        builder.add_node("fetch_news",          _fetch_news(news_service, ipo_service, self.news_agent, self.ipo_agent))
        builder.add_node("analyze_impact",      _analyze_impact(self.impact_agent))
        builder.add_node("verify_analysis",     _verify_analysis(self.verification_agent))
        builder.add_node("create_alerts",       _create_alerts(alert_service))
        builder.add_node("send_notifications",  _send_notifications(notification_service))
        builder.add_node("persist_results",     _persist_results())

        builder.set_entry_point("fetch_watchlist")
        builder.add_edge("fetch_watchlist",     "fetch_market_data")
        builder.add_edge("fetch_market_data",   "detect_price_alerts")
        builder.add_edge("detect_price_alerts", "fetch_catalysts")
        builder.add_edge("fetch_catalysts",     "fetch_news")
        builder.add_edge("fetch_news",          "analyze_impact")
        builder.add_edge("analyze_impact",      "verify_analysis")
        builder.add_edge("verify_analysis",     "create_alerts")
        builder.add_edge("create_alerts",       "send_notifications")
        builder.add_edge("send_notifications",  "persist_results")
        builder.add_edge("persist_results",     END)

        self._graph = builder.compile()

    def run_once(self) -> Dict[str, Any]:
        initial: MonitorState = {
            "watchlist": [],
            "price_snapshots": [],
            "alerts": [],
            "catalysts": [],
            "news": [],
            "analyses": [],
            "errors": [],
            "summary": {},
        }
        try:
            return dict(self._graph.invoke(initial))
        except Exception as exc:
            initial["errors"].append(str(exc))
            return dict(initial)
