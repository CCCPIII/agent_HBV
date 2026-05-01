from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class WatchlistItemBase(BaseModel):
    ticker: str
    company_name: str
    exchange: Optional[str] = None
    sector: Optional[str] = None
    alert_threshold_percent: Optional[float] = 5.0
    active: Optional[bool] = True


class WatchlistItemCreate(WatchlistItemBase):
    pass


class WatchlistItemRead(WatchlistItemBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


class PortfolioPositionBase(BaseModel):
    ticker: str
    company_name: str
    quantity: float
    average_cost: float
    currency: Optional[str] = "USD"
    purchase_date: Optional[date] = None
    active: Optional[bool] = True


class PortfolioPositionCreate(PortfolioPositionBase):
    pass


class PortfolioPositionRead(PortfolioPositionBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


class PriceSnapshotRead(BaseModel):
    ticker: str
    price: float
    previous_close: float
    percent_change: float
    currency: Optional[str]
    captured_at: datetime

    class Config:
        orm_mode = True


class CatalystEventRead(BaseModel):
    id: int
    ticker: str
    title: str
    catalyst_type: str
    event_date: date
    source_url: Optional[str]
    confidence: float
    created_at: datetime

    class Config:
        orm_mode = True


class NewsItemRead(BaseModel):
    id: int
    ticker: Optional[str]
    sector: Optional[str]
    title: str
    summary: str
    source: str
    source_url: str
    published_at: datetime
    created_at: datetime

    class Config:
        orm_mode = True


class AlertRead(BaseModel):
    id: int
    ticker: Optional[str]
    alert_type: str
    severity: str
    title: str
    message: str
    source_url: Optional[str]
    created_at: datetime
    sent: bool

    class Config:
        orm_mode = True


class AgentAnalysisRead(BaseModel):
    id: int
    related_alert_id: Optional[int]
    related_news_id: Optional[int]
    ticker: Optional[str]
    impact_direction: str
    impact_level: str
    summary: str
    reasoning: str
    confidence: float
    created_at: datetime

    class Config:
        orm_mode = True
