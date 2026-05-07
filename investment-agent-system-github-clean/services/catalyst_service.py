from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

import requests
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CatalystEvent
from services.external_api_guard import external_api_guard
from services.network_env import external_network_env
from services.symbol_mapper import build_finnhub_symbol_candidates
from services.yfinance_env import yfinance_network_env

CATALYST_TYPES = [
    "earnings",
    "dividend",
    "stock_split",
    "investor_day",
    "company_event",
    "ipo",
    "regulatory",
    "other",
]


class CatalystService:
    """Manage catalyst events from structured providers plus demo fallbacks."""

    def __init__(self) -> None:
        self._runtime_metadata: Dict[str, Dict[str, Any]] = {}

    def get_upcoming_catalysts(self, session: Session) -> List[CatalystEvent]:
        return session.query(CatalystEvent).order_by(CatalystEvent.event_date).all()

    def normalize(self, event: CatalystEvent) -> Dict[str, Any]:
        metadata = self._runtime_metadata.get(self._event_key(
            event.ticker,
            event.title,
            event.catalyst_type,
            event.event_date,
        ), {})
        days_until = (event.event_date - date.today()).days
        return {
            "id": event.id,
            "ticker": event.ticker,
            "title": event.title,
            "catalyst_type": event.catalyst_type,
            "event_date": event.event_date.isoformat(),
            "source_url": event.source_url,
            "confidence": event.confidence,
            "days_until": days_until,
            "confirmed": event.confidence >= 0.85,
            "manual": bool(metadata.get("manual", False)),
            "source": metadata.get("source") or self._infer_source(event),
            "notes": metadata.get("notes") or self._fallback_notes(event),
            "urgency": self._urgency_bucket(days_until),
        }

    def build_calendar(
        self,
        session: Session,
        watchlist: Iterable[object],
        ticker: str = "all",
        catalyst_type: str = "all",
        window_days: Optional[int] = None,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        watchlist = [item for item in watchlist if getattr(item, "ticker", None)]
        if refresh:
            self.sync_watchlist_catalysts(session, watchlist)

        today = date.today()
        effective_window = max(1, int(window_days or settings.catalyst_lookahead_days))
        end_date = today + timedelta(days=effective_window)
        ticker_filter = (ticker or "all").upper()
        type_filter = (catalyst_type or "all").lower()

        query = session.query(CatalystEvent).filter(CatalystEvent.event_date >= today)
        query = query.filter(CatalystEvent.event_date <= end_date)
        if ticker_filter != "ALL":
            query = query.filter(CatalystEvent.ticker == ticker_filter)
        if type_filter != "all":
            query = query.filter(CatalystEvent.catalyst_type == type_filter)

        events = query.order_by(CatalystEvent.event_date, CatalystEvent.ticker).all()
        if not events:
            self._seed_watchlist_fallbacks(session, watchlist, today)
            query = session.query(CatalystEvent).filter(CatalystEvent.event_date >= today)
            query = query.filter(CatalystEvent.event_date <= end_date)
            if ticker_filter != "ALL":
                query = query.filter(CatalystEvent.ticker == ticker_filter)
            if type_filter != "all":
                query = query.filter(CatalystEvent.catalyst_type == type_filter)
            events = query.order_by(CatalystEvent.event_date, CatalystEvent.ticker).all()
        items = [self.normalize(event) for event in events]
        urgent_this_week = [item for item in items if 0 <= item["days_until"] <= 7]

        return {
            "items": items,
            "summary": {
                "count": len(items),
                "urgent_this_week_count": len(urgent_this_week),
                "urgent_this_week": urgent_this_week[:8],
                "next_catalyst": items[0] if items else None,
                "headline": self._build_headline(urgent_this_week, items),
            },
            "filters": {
                "tickers": sorted({getattr(item, "ticker", "").upper() for item in watchlist if getattr(item, "ticker", None)}),
                "types": CATALYST_TYPES,
                "window_days": effective_window,
            },
        }

    def sync_watchlist_catalysts(self, session: Session, watchlist: Iterable[object]) -> List[CatalystEvent]:
        watchlist = [item for item in watchlist if getattr(item, "ticker", None)]
        if not watchlist:
            return self.get_upcoming_catalysts(session)

        start_date = date.today()
        end_date = start_date + timedelta(days=settings.catalyst_lookahead_days)

        if self._should_use_finnhub():
            for item in watchlist[:10]:
                self._ingest_finnhub(session, item, start_date, end_date)

        for item in watchlist[:10]:
            self._ingest_yfinance(session, item, start_date, end_date)

        if session.query(CatalystEvent).count() == 0:
            self.seed_demo_catalysts(session)
        return self.get_upcoming_catalysts(session)

    def seed_demo_catalysts(self, session: Session) -> None:
        if session.query(CatalystEvent).count() > 0:
            return
        demo = [
            CatalystEvent(
                ticker="AAPL",
                title="Apple earnings call",
                catalyst_type="earnings",
                event_date=date.today(),
                source_url="https://www.apple.com/investor/",
                confidence=0.9,
            ),
            CatalystEvent(
                ticker="005930.KS",
                title="Samsung investor day",
                catalyst_type="investor_day",
                event_date=date.today(),
                source_url="https://www.samsung.com/",
                confidence=0.8,
            ),
        ]
        session.add_all(demo)
        session.commit()

    def _seed_watchlist_fallbacks(self, session: Session, watchlist: Iterable[object], start_date: date) -> None:
        for index, item in enumerate(list(watchlist)[:6]):
            ticker = getattr(item, "ticker", "").upper()
            if not ticker:
                continue
            event_date = start_date + timedelta(days=min(index + 2, 10))
            self._upsert_event(
                session=session,
                ticker=ticker,
                title=f"{ticker} earnings watch",
                catalyst_type="earnings",
                event_date=event_date,
                source_url="",
                confidence=0.65,
                metadata={
                    "source": "watchlist_fallback",
                    "notes": "Needs provider sync for exact schedule",
                },
            )

    def _should_use_finnhub(self) -> bool:
        return settings.catalyst_provider in {"auto", "finnhub"} and bool(settings.finnhub_api_key)

    def _ingest_finnhub(self, session: Session, item: object, start_date: date, end_date: date) -> None:
        ticker = getattr(item, "ticker", "").upper()
        company_name = getattr(item, "company_name", None)
        if not ticker:
            return

        token = settings.finnhub_api_key
        discovered = self._discover_finnhub_symbols(ticker, company_name)
        candidates = build_finnhub_symbol_candidates(ticker, company_name, discovered)
        for symbol in candidates:
            params = {
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "symbol": symbol,
                "token": token,
            }

            try:
                with external_network_env():
                    earnings = external_api_guard.call(
                        "finnhub",
                        lambda: requests.get(
                            "https://finnhub.io/api/v1/calendar/earnings",
                            params=params,
                            timeout=15,
                        ).json(),
                        cache_key=f"finnhub_earnings:{symbol}:{start_date.isoformat()}:{end_date.isoformat()}",
                        cache_ttl_seconds=21600,
                    )
                for entry in earnings.get("earningsCalendar") or []:
                    event_date = self._parse_date(entry.get("date"))
                    if not event_date:
                        continue
                    self._upsert_event(
                        session=session,
                        ticker=ticker,
                        title=f"{ticker} earnings report",
                        catalyst_type="earnings",
                        event_date=event_date,
                        source_url=f"https://finnhub.io/api/v1/calendar/earnings?symbol={symbol}",
                        confidence=0.95,
                        metadata={
                            "source": "finnhub",
                            "notes": self._format_earnings_notes(entry),
                        },
                    )
            except Exception:
                pass

            try:
                with external_network_env():
                    dividends = external_api_guard.call(
                        "finnhub",
                        lambda: requests.get(
                            "https://finnhub.io/api/v1/stock/dividend",
                            params=params,
                            timeout=15,
                        ).json(),
                        cache_key=f"finnhub_dividend:{symbol}:{start_date.isoformat()}:{end_date.isoformat()}",
                        cache_ttl_seconds=21600,
                    )
                for entry in dividends or []:
                    event_date = self._parse_date(entry.get("date") or entry.get("exDate") or entry.get("paymentDate"))
                    if not event_date:
                        continue
                    amount = entry.get("amount")
                    title = f"{ticker} dividend event"
                    if amount not in (None, ""):
                        title = f"{ticker} dividend {amount}"
                    self._upsert_event(
                        session=session,
                        ticker=ticker,
                        title=title,
                        catalyst_type="dividend",
                        event_date=event_date,
                        source_url=f"https://finnhub.io/api/v1/stock/dividend?symbol={symbol}",
                        confidence=0.95,
                        metadata={
                            "source": "finnhub",
                            "notes": self._format_dividend_notes(entry),
                        },
                    )
            except Exception:
                pass

    def _ingest_yfinance(self, session: Session, item: object, start_date: date, end_date: date) -> None:
        ticker = getattr(item, "ticker", "").upper()
        if not ticker:
            return
        try:
            import yfinance as yf
        except ImportError:
            return

        try:
            with yfinance_network_env():
                yf_ticker = yf.Ticker(ticker)
        except Exception:
            return

        # Earnings / company calendar
        try:
            with yfinance_network_env():
                calendar = external_api_guard.call(
                    "yfinance_calendar",
                    lambda: yf_ticker.calendar,
                    cache_key=f"yfinance_calendar:{ticker}",
                    cache_ttl_seconds=21600,
                )
            if hasattr(calendar, "to_dict"):
                calendar = calendar.to_dict()
            earnings_date = None
            if isinstance(calendar, dict):
                earnings_date = (
                    calendar.get("Earnings Date")
                    or calendar.get("earningsDate")
                    or calendar.get("Ex-Dividend Date")
                )
            parsed = self._parse_market_date(earnings_date)
            if parsed and start_date <= parsed <= end_date:
                self._upsert_event(
                    session=session,
                    ticker=ticker,
                    title=f"{ticker} earnings date",
                    catalyst_type="earnings",
                    event_date=parsed,
                    source_url=f"https://finance.yahoo.com/quote/{ticker}",
                    confidence=0.85,
                    metadata={
                        "source": "yfinance",
                        "notes": "Yahoo Finance calendar event",
                    },
                )
        except Exception:
            pass

        # Dividends and splits from actions
        try:
            with yfinance_network_env():
                dividends = external_api_guard.call(
                    "yfinance_calendar",
                    lambda: getattr(yf_ticker, "dividends", None),
                    cache_key=f"yfinance_dividends:{ticker}",
                    cache_ttl_seconds=21600,
                )
            if dividends is not None and not dividends.empty:
                for ts, value in dividends.items():
                    event_date = ts.date()
                    if start_date <= event_date <= end_date:
                        self._upsert_event(
                            session=session,
                            ticker=ticker,
                            title=f"{ticker} dividend {float(value):.4g}",
                            catalyst_type="dividend",
                            event_date=event_date,
                            source_url=f"https://finance.yahoo.com/quote/{ticker}/history",
                            confidence=0.8,
                            metadata={
                                "source": "yfinance",
                                "notes": f"Dividend amount {float(value):.4g}",
                            },
                        )
        except Exception:
            pass

        try:
            with yfinance_network_env():
                splits = external_api_guard.call(
                    "yfinance_calendar",
                    lambda: getattr(yf_ticker, "splits", None),
                    cache_key=f"yfinance_splits:{ticker}",
                    cache_ttl_seconds=21600,
                )
            if splits is not None and not splits.empty:
                for ts, value in splits.items():
                    event_date = ts.date()
                    if start_date <= event_date <= end_date:
                        self._upsert_event(
                            session=session,
                            ticker=ticker,
                            title=f"{ticker} stock split {float(value):.4g}:1",
                            catalyst_type="stock_split",
                            event_date=event_date,
                            source_url=f"https://finance.yahoo.com/quote/{ticker}/history",
                            confidence=0.8,
                            metadata={
                                "source": "yfinance",
                                "notes": f"Split ratio {float(value):.4g}:1",
                            },
                        )
        except Exception:
            pass

    def _upsert_event(
        self,
        session: Session,
        ticker: str,
        title: str,
        catalyst_type: str,
        event_date: date,
        source_url: str,
        confidence: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CatalystEvent:
        event_key = self._event_key(ticker, title, catalyst_type, event_date)
        if metadata:
            self._runtime_metadata[event_key] = metadata
        existing = (
            session.query(CatalystEvent)
            .filter(
                CatalystEvent.ticker == ticker,
                CatalystEvent.title == title,
                CatalystEvent.catalyst_type == catalyst_type,
                CatalystEvent.event_date == event_date,
            )
            .first()
        )
        if existing:
            if source_url and not existing.source_url:
                existing.source_url = source_url
            existing.confidence = max(existing.confidence, confidence)
            session.commit()
            return existing

        record = CatalystEvent(
            ticker=ticker,
            title=title,
            catalyst_type=catalyst_type if catalyst_type in CATALYST_TYPES else "other",
            event_date=event_date,
            source_url=source_url,
            confidence=confidence,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record

    def _discover_finnhub_symbols(self, ticker: str, company_name: Optional[str]) -> List[str]:
        queries = [ticker]
        if company_name:
            queries.insert(0, company_name)

        discovered: List[str] = []
        for query in queries:
            query = (query or "").strip()
            if not query:
                continue
            try:
                with external_network_env():
                    response = external_api_guard.call(
                        "finnhub",
                        lambda: requests.get(
                            "https://finnhub.io/api/v1/search",
                            params={"q": query, "token": settings.finnhub_api_key},
                            timeout=15,
                        ),
                        cache_key=f"finnhub_search:{query}",
                        cache_ttl_seconds=21600,
                    )
                response.raise_for_status()
                payload = response.json()
            except Exception:
                continue
            for item in payload.get("result") or []:
                symbol = item.get("symbol") or item.get("displaySymbol")
                if symbol:
                    discovered.append(str(symbol))
        return discovered

    @staticmethod
    def _event_key(ticker: str, title: str, catalyst_type: str, event_date: date) -> str:
        return "|".join([ticker.upper(), title, catalyst_type, event_date.isoformat()])

    @staticmethod
    def _urgency_bucket(days_until: int) -> str:
        if days_until < 0:
            return "past"
        if days_until <= 2:
            return "urgent"
        if days_until <= 7:
            return "this_week"
        if days_until <= 30:
            return "next_30d"
        return "future"

    @staticmethod
    def _format_number(value: Any) -> Optional[str]:
        if value in (None, "", 0):
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if abs(numeric) >= 1_000_000:
            return f"${numeric:,.0f}"
        return f"{numeric:.4g}"

    def _format_earnings_notes(self, entry: Dict[str, Any]) -> str:
        parts: List[str] = []
        eps = self._format_number(entry.get("epsEstimate") or entry.get("eps"))
        revenue = self._format_number(entry.get("revenueEstimate") or entry.get("revenue"))
        if eps:
            parts.append(f"EPS est: {eps}")
        if revenue:
            parts.append(f"Rev est: {revenue}")
        return " | ".join(parts) if parts else "Upcoming earnings event"

    def _format_dividend_notes(self, entry: Dict[str, Any]) -> str:
        amount = self._format_number(entry.get("amount"))
        if amount:
            return f"Dividend amount {amount}"
        return "Dividend event"

    @staticmethod
    def _infer_source(event: CatalystEvent) -> str:
        if event.source_url and "finnhub.io" in event.source_url:
            return "finnhub"
        if event.source_url and "finance.yahoo.com" in event.source_url:
            return "yfinance"
        if event.source_url:
            return "external"
        return "manual"

    @staticmethod
    def _fallback_notes(event: CatalystEvent) -> str:
        title = event.title or ""
        ticker = event.ticker or ""
        notes = title.replace(ticker, "", 1).strip(" -")
        return notes or f"{event.catalyst_type.replace('_', ' ')} event"

    @staticmethod
    def _build_headline(urgent_this_week: List[Dict[str, Any]], items: List[Dict[str, Any]]) -> str:
        if urgent_this_week:
            tickers = ", ".join(item["ticker"] for item in urgent_this_week[:6])
            return f"This week's highest-priority catalysts: {tickers}"
        if items:
            next_item = items[0]
            return f"Next catalyst: {next_item['ticker']} {next_item['catalyst_type']} in {next_item['days_until']} day(s)"
        return "No upcoming catalysts in the selected window"

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            return None

    @staticmethod
    def _parse_market_date(value: object) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (list, tuple)) and value:
            for candidate in value:
                parsed = CatalystService._parse_market_date(candidate)
                if parsed:
                    return parsed
            return None
        if hasattr(value, "to_pydatetime"):
            try:
                return value.to_pydatetime().date()
            except Exception:
                return None
        if isinstance(value, str):
            return CatalystService._parse_date(value)
        return None
