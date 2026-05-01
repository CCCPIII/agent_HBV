from typing import List

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine, get_session
from app.models import Alert, CatalystEvent, NewsItem, PortfolioPosition, WatchlistItem
from app.schemas import (
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


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/watchlist", response_model=List[WatchlistItemRead])
def list_watchlist(session: Session = Depends(get_session)) -> List[WatchlistItemRead]:
    items = session.query(WatchlistItem).filter(WatchlistItem.active == True).all()
    return items


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
    positions = session.query(PortfolioPosition).filter(PortfolioPosition.active == True).all()
    return positions


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
    alerts = session.query(Alert).order_by(Alert.created_at.desc()).limit(100).all()
    return alerts


@app.get("/catalysts", response_model=List[CatalystEventRead])
def list_catalysts(session: Session = Depends(get_session)) -> List[CatalystEventRead]:
    catalysts = session.query(CatalystEvent).order_by(CatalystEvent.event_date).all()
    return catalysts


@app.get("/news", response_model=List[NewsItemRead])
def list_news(session: Session = Depends(get_session)) -> List[NewsItemRead]:
    news = session.query(NewsItem).order_by(NewsItem.published_at.desc()).limit(100).all()
    return news


@app.get("/analyses")
def list_analyses(session: Session = Depends(get_session)) -> List[dict]:
    from app.models import AgentAnalysis

    analyses = session.query(AgentAnalysis).order_by(AgentAnalysis.created_at.desc()).limit(100).all()
    return [
        {
            "id": analysis.id,
            "related_alert_id": analysis.related_alert_id,
            "related_news_id": analysis.related_news_id,
            "ticker": analysis.ticker,
            "impact_direction": analysis.impact_direction,
            "impact_level": analysis.impact_level,
            "summary": analysis.summary,
            "reasoning": analysis.reasoning,
            "confidence": analysis.confidence,
            "created_at": analysis.created_at,
        }
        for analysis in analyses
    ]
