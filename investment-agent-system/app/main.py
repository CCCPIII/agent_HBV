import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine, get_session
from app.models import Alert, CatalystEvent, NewsItem, PortfolioPosition, WatchlistItem
from app.schemas import (
    AgentAnalysisRead,
    AlertRead,
    CatalystEventRead,
    NewsItemRead,
    PortfolioPositionCreate,
    PortfolioPositionRead,
    WatchlistItemCreate,
    WatchlistItemRead,
)
from graph.stock_monitor_graph import StockMonitorGraph
from services.alert_service import AlertService
from services.catalyst_service import CatalystService
from services.ipo_service import IPOService
from services.market_data_service import MarketDataService
from services.news_service import NewsService
from services.notification_service import NotificationService
from services.portfolio_service import PortfolioService

# ── Scheduler state ──────────────────────────────────────────────────────────

_scheduler: dict = {
    "enabled": True,
    "interval_minutes": 30,
    "last_run_at": None,
    "next_run_at": None,
    "running": False,
}


def _build_graph() -> StockMonitorGraph:
    return StockMonitorGraph(
        market_data_service=MarketDataService(),
        catalyst_service=CatalystService(),
        news_service=NewsService(),
        ipo_service=IPOService(),
        alert_service=AlertService(),
        notification_service=NotificationService(),
    )


def _do_monitor_run() -> None:
    _scheduler["running"] = True
    try:
        _build_graph().run_once()
        _scheduler["last_run_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    finally:
        _scheduler["running"] = False


async def _scheduler_loop() -> None:
    # Brief delay so the server is fully up before first auto-run
    await asyncio.sleep(15)
    while True:
        interval = _scheduler["interval_minutes"]
        if not _scheduler["enabled"] or interval <= 0:
            await asyncio.sleep(60)
            continue
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, _do_monitor_run)
        except Exception:
            pass
        next_run = datetime.utcnow() + timedelta(minutes=interval)
        _scheduler["next_run_at"] = next_run.strftime("%Y-%m-%dT%H:%M:%SZ")
        await asyncio.sleep(interval * 60)


# ── App with lifespan ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    Base.metadata.create_all(bind=engine)
    _scheduler["interval_minutes"] = settings.monitor_interval_minutes
    _scheduler["enabled"] = settings.monitor_interval_minutes > 0
    task = asyncio.create_task(_scheduler_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="investment-agent-system", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ── Scheduler ─────────────────────────────────────────────────────────────────

@app.get("/monitor/scheduler")
def get_scheduler_status() -> dict:
    return {
        "enabled": _scheduler["enabled"],
        "interval_minutes": _scheduler["interval_minutes"],
        "running": _scheduler["running"],
        "last_run_at": _scheduler["last_run_at"],
        "next_run_at": _scheduler["next_run_at"],
    }


@app.post("/monitor/scheduler")
def update_scheduler(body: dict) -> dict:
    """Update scheduler. Pass {interval_minutes: N} (0 to disable)."""
    if "interval_minutes" in body:
        minutes = int(body["interval_minutes"])
        _scheduler["interval_minutes"] = minutes
        _scheduler["enabled"] = minutes > 0
        # Write to .env so it persists across restarts
        settings.update_env({"MONITOR_INTERVAL_MINUTES": str(minutes)})
        if _scheduler["enabled"]:
            next_run = datetime.utcnow() + timedelta(minutes=minutes)
            _scheduler["next_run_at"] = next_run.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            _scheduler["next_run_at"] = None
    return get_scheduler_status()


# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/config/models")
def config_models() -> dict:
    return {
        "active_provider": settings.active_llm_provider,
        "providers": settings.providers_status(),
    }


@app.get("/config/settings")
def get_settings() -> dict:
    return settings.get_all_for_ui()


@app.post("/config/settings")
def update_settings(updates: dict) -> dict:
    updated = settings.update_env(updates)
    # If interval changed, sync scheduler
    if "MONITOR_INTERVAL_MINUTES" in [k.upper() for k in updates]:
        _scheduler["interval_minutes"] = settings.monitor_interval_minutes
        _scheduler["enabled"] = settings.monitor_interval_minutes > 0
    return {"updated": updated, "active_provider": settings.active_llm_provider}


# ── News ──────────────────────────────────────────────────────────────────────

@app.get("/news/live/{ticker}")
def live_news(ticker: str) -> List[dict]:
    """Fetch recent news for a ticker from Yahoo Finance (no API key required)."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker.upper())
        raw = t.news or []
        result = []
        for item in raw[:20]:
            content = item.get("content", {})
            result.append({
                "ticker": ticker.upper(),
                "title": content.get("title") or item.get("title", ""),
                "summary": (content.get("summary") or content.get("description") or "")[:300],
                "source": (content.get("provider", {}) or {}).get("displayName", "") or item.get("publisher", ""),
                "source_url": (content.get("canonicalUrl", {}) or {}).get("url", "") or item.get("link", ""),
                "published_at": content.get("pubDate") or item.get("providerPublishTime", ""),
            })
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/news/market")
def market_news() -> List[dict]:
    """Fetch IPO and market event news (HK focus) from Yahoo Finance + stored DB items."""
    ipo_svc = IPOService()
    try:
        live = ipo_svc.get_market_news()
    except Exception:
        live = []

    # Also include stored IPO-related news from DB
    from app.db import SessionLocal
    stored = []
    try:
        with SessionLocal() as session:
            rows = (
                session.query(NewsItem)
                .filter(
                    (NewsItem.sector == "IPO")
                    | NewsItem.title.ilike("%IPO%")
                    | NewsItem.title.ilike("%listing%")
                    | NewsItem.title.ilike("%新股%")
                )
                .order_by(NewsItem.published_at.desc())
                .limit(20)
                .all()
            )
            for n in rows:
                stored.append({
                    "ticker": n.ticker,
                    "title": n.title,
                    "summary": n.summary,
                    "source": n.source,
                    "source_url": n.source_url,
                    "published_at": n.published_at.isoformat() if n.published_at else None,
                    "event_type": "ipo",
                })
    except Exception:
        pass

    # Merge, deduplicate by title
    seen = set()
    merged = []
    for item in live + stored:
        t = item.get("title", "")
        if t and t not in seen:
            seen.add(t)
            merged.append(item)

    return merged[:30]


# ── Watchlist ─────────────────────────────────────────────────────────────────

@app.get("/watchlist", response_model=List[WatchlistItemRead])
def list_watchlist(session: Session = Depends(get_session)) -> List[WatchlistItemRead]:
    return session.query(WatchlistItem).filter(WatchlistItem.active == True).all()


@app.post("/watchlist", response_model=WatchlistItemRead)
def create_watchlist(item: WatchlistItemCreate, session: Session = Depends(get_session)) -> WatchlistItemRead:
    db_item = WatchlistItem(**item.model_dump())
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.delete("/watchlist/{item_id}")
def delete_watchlist(item_id: int, session: Session = Depends(get_session)) -> dict:
    item = session.get(WatchlistItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    item.active = False
    session.commit()
    return {"deleted": item_id}


# ── Portfolio ─────────────────────────────────────────────────────────────────

@app.get("/portfolio", response_model=List[PortfolioPositionRead])
def list_portfolio(session: Session = Depends(get_session)) -> List[PortfolioPositionRead]:
    return session.query(PortfolioPosition).filter(PortfolioPosition.active == True).all()


@app.post("/portfolio", response_model=PortfolioPositionRead)
def create_portfolio(position: PortfolioPositionCreate, session: Session = Depends(get_session)) -> PortfolioPositionRead:
    db_position = PortfolioPosition(**position.model_dump())
    session.add(db_position)
    session.commit()
    session.refresh(db_position)
    return db_position


@app.delete("/portfolio/{position_id}")
def delete_portfolio(position_id: int, session: Session = Depends(get_session)) -> dict:
    position = session.get(PortfolioPosition, position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Portfolio position not found")
    position.active = False
    session.commit()
    return {"deleted": position_id}


@app.get("/portfolio/summary")
def portfolio_summary(session: Session = Depends(get_session)) -> List[dict]:
    positions = session.query(PortfolioPosition).filter(PortfolioPosition.active == True).all()
    market = MarketDataService()
    result = []
    for pos in positions:
        try:
            quote = market.get_quote(pos.ticker)
            current_price = quote["price"]
            percent_change = quote["percent_change"]
        except Exception:
            current_price = None
            percent_change = None

        cost_basis = pos.quantity * pos.average_cost
        current_value = pos.quantity * current_price if current_price is not None else None
        pnl = current_value - cost_basis if current_value is not None else None
        pnl_pct = (pnl / cost_basis * 100) if (pnl is not None and cost_basis) else None

        result.append({
            "id": pos.id,
            "ticker": pos.ticker,
            "company_name": pos.company_name,
            "quantity": pos.quantity,
            "average_cost": pos.average_cost,
            "currency": pos.currency,
            "purchase_date": pos.purchase_date.isoformat() if pos.purchase_date else None,
            "current_price": current_price,
            "current_value": round(current_value, 2) if current_value is not None else None,
            "cost_basis": round(cost_basis, 2),
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "day_change_pct": percent_change,
        })
    return result


# ── Market data ───────────────────────────────────────────────────────────────

@app.get("/prices/{ticker}")
def get_price(ticker: str) -> dict:
    service = MarketDataService()
    return service.get_quote(ticker)


# ── Monitor ───────────────────────────────────────────────────────────────────

@app.post("/monitor/run-once")
def run_monitor_once() -> dict:
    result = _build_graph().run_once()
    _scheduler["last_run_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"status": "completed", "summary": result}


# ── Alerts / catalysts / news / analyses ──────────────────────────────────────

@app.get("/alerts", response_model=List[AlertRead])
def list_alerts(session: Session = Depends(get_session)) -> List[AlertRead]:
    return session.query(Alert).order_by(Alert.created_at.desc()).limit(100).all()


@app.get("/catalysts", response_model=List[CatalystEventRead])
def list_catalysts(session: Session = Depends(get_session)) -> List[CatalystEventRead]:
    return session.query(CatalystEvent).order_by(CatalystEvent.event_date).all()


@app.get("/news", response_model=List[NewsItemRead])
def list_news(session: Session = Depends(get_session)) -> List[NewsItemRead]:
    return session.query(NewsItem).order_by(NewsItem.published_at.desc()).limit(100).all()


@app.get("/analyses", response_model=List[AgentAnalysisRead])
def list_analyses(session: Session = Depends(get_session)) -> List[AgentAnalysisRead]:
    from app.models import AgentAnalysis as AgentAnalysisModel
    return (
        session.query(AgentAnalysisModel)
        .order_by(AgentAnalysisModel.created_at.desc())
        .limit(100)
        .all()
    )


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/dashboard/summary")
def dashboard_summary(session: Session = Depends(get_session)) -> dict:
    from app.models import AgentAnalysis

    watchlist_count = session.query(WatchlistItem).filter(WatchlistItem.active == True).count()
    portfolio_count = session.query(PortfolioPosition).filter(PortfolioPosition.active == True).count()
    alerts_count = session.query(Alert).count()
    unread_alerts = session.query(Alert).filter(Alert.sent == False).count()
    analyses_count = session.query(AgentAnalysis).count()
    news_count = session.query(NewsItem).count()
    catalysts_count = session.query(CatalystEvent).count()
    return {
        "watchlist_count": watchlist_count,
        "portfolio_count": portfolio_count,
        "alerts_count": alerts_count,
        "unread_alerts": unread_alerts,
        "analyses_count": analyses_count,
        "news_count": news_count,
        "catalysts_count": catalysts_count,
        "scheduler": {
            "enabled": _scheduler["enabled"],
            "interval_minutes": _scheduler["interval_minutes"],
            "last_run_at": _scheduler["last_run_at"],
            "next_run_at": _scheduler["next_run_at"],
        },
    }
