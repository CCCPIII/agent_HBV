from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text

from app.db import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(16), unique=True, nullable=False, index=True)
    company_name = Column(String(256), nullable=False)
    exchange = Column(String(64), nullable=True)
    sector = Column(String(128), nullable=True)
    alert_threshold_percent = Column(Float, default=5.0, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    company_name = Column(String(256), nullable=False)
    quantity = Column(Float, default=0.0, nullable=False)
    average_cost = Column(Float, default=0.0, nullable=False)
    currency = Column(String(16), default="USD", nullable=False)
    purchase_date = Column(Date, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    price = Column(Float, nullable=False)
    previous_close = Column(Float, nullable=False)
    percent_change = Column(Float, nullable=False)
    currency = Column(String(16), nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CatalystEvent(Base):
    __tablename__ = "catalyst_events"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    catalyst_type = Column(String(64), nullable=False)
    event_date = Column(Date, nullable=False)
    source_url = Column(String(1024), nullable=True)
    confidence = Column(Float, default=0.8, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NewsItem(Base):
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(16), nullable=True, index=True)
    sector = Column(String(128), nullable=True, index=True)
    title = Column(String(512), nullable=False)
    summary = Column(Text, nullable=False)
    source = Column(String(128), nullable=False)
    source_url = Column(String(1024), nullable=False)
    published_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(16), nullable=True, index=True)
    alert_type = Column(String(64), nullable=False)
    severity = Column(String(32), nullable=False)
    title = Column(String(512), nullable=False)
    message = Column(Text, nullable=False)
    source_url = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent = Column(Boolean, default=False, nullable=False)


class AgentAnalysis(Base):
    __tablename__ = "agent_analyses"

    id = Column(Integer, primary_key=True, index=True)
    related_alert_id = Column(Integer, nullable=True)
    related_news_id = Column(Integer, nullable=True)
    ticker = Column(String(16), nullable=True, index=True)
    impact_direction = Column(String(32), nullable=False)
    impact_level = Column(String(32), nullable=False)
    summary = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
