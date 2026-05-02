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
from services.market_data_service import MarketDataService
from services.news_service import NewsService
from services.portfolio_service import PortfolioService
from services.ipo_service import IPOService
from services.notification_service import NotificationService

app = FastAPI(title="investment-agent-system")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/config/models")
def config_models() -> dict:
    """Return the status of all LLM providers and which one is active."""
    return {
        "active_provider": settings.active_llm_provider,
        "providers": settings.providers_status(),
    }


@app.get("/config/settings")
def get_settings() -> dict:
    """Return all .env settings grouped by category. API keys are masked."""
    return settings.get_all_for_ui()


@app.post("/config/settings")
def update_settings(updates: dict) -> dict:
    """Write updates to .env file and reload settings in memory."""
    updated = settings.update_env(updates)
    return {"updated": updated, "active_provider": settings.active_llm_provider}


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
    """Return portfolio positions enriched with current price and P&L."""
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


@app.get("/prices/{ticker}")
def get_price(ticker: str) -> dict:
    service = MarketDataService()
    quote = service.get_quote(ticker)
    return quote


@app.post("/monitor/run-once")
def run_monitor_once() -> dict:
    graph = StockMonitorGraph(
        market_data_service=MarketDataService(),
        catalyst_service=CatalystService(),
        news_service=NewsService(),
        ipo_service=IPOService(),
        alert_service=AlertService(),
        notification_service=NotificationService(),
    )
    result = graph.run_once()
    return {"status": "completed", "summary": result}


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
    }
