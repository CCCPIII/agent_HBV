from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests
from sqlalchemy import or_
from sqlalchemy.orm import Session

from agents.search_intelligence_agent import SearchIntelligenceAgent
from app.config import settings
from app.models import NewsItem
from services.external_api_guard import external_api_guard
from services.network_env import external_network_env
from services.search_service import SearchService
from services.symbol_mapper import build_finnhub_symbol_candidates
from services.yfinance_env import yfinance_network_env


class NewsService:
    """Fetch, persist, and query news from external providers and local storage."""

    def __init__(self):
        self._search_service = SearchService()
        self._search_agent = SearchIntelligenceAgent()

    def get_news(
        self,
        session: Session,
        tickers: Optional[List[str]] = None,
        sectors: Optional[List[str]] = None,
    ) -> List[NewsItem]:
        query = session.query(NewsItem)
        filters = []
        if tickers:
            filters.append(NewsItem.ticker.in_([ticker.upper() for ticker in tickers]))
        if sectors:
            filters.append(NewsItem.sector.in_(sectors))
        if filters:
            query = query.filter(or_(*filters))
        return query.order_by(NewsItem.published_at.desc()).limit(50).all()

    def fetch_live_news(
        self,
        session: Session,
        ticker: str,
        company_name: Optional[str] = None,
        sector: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        ticker = ticker.upper()
        recent_cached = self._load_recent_real_news(session, ticker, limit)
        if recent_cached:
            return recent_cached

        if self._should_use_search():
            inserted = self._ingest_search(session, ticker, company_name, sector, limit)
            if inserted:
                return inserted

        if self._should_use_newsapi():
            inserted = self._ingest_newsapi(session, ticker, company_name, sector, limit)
            if inserted:
                return inserted

        if self._should_use_finnhub():
            inserted = self._ingest_finnhub(session, ticker, company_name, sector, limit)
            if inserted:
                return inserted

        inserted = self._ingest_yfinance(session, ticker, limit)
        if inserted:
            return inserted

        return self._load_fallback_news(session, ticker, sector, limit)

    def ingest_watchlist_news(self, session: Session, watchlist: List[object], per_item_limit: int = 5) -> List[NewsItem]:
        for item in watchlist[:5]:
            self.fetch_live_news(
                session=session,
                ticker=getattr(item, "ticker", ""),
                company_name=getattr(item, "company_name", None),
                sector=getattr(item, "sector", None),
                limit=per_item_limit,
            )
        return self.get_news(
            session,
            tickers=[getattr(item, "ticker", "") for item in watchlist if getattr(item, "ticker", None)],
            sectors=[getattr(item, "sector", None) for item in watchlist if getattr(item, "sector", None)],
        )

    def seed_demo_news(self, session: Session) -> None:
        if session.query(NewsItem).count() > 0:
            return

        demo = [
            NewsItem(
                ticker="AAPL",
                sector="Technology",
                title="Apple ramps up product event expectations",
                summary="Analysts note that Apple may announce new hardware next quarter.",
                source="Demo News",
                source_url="https://example.com/apple-event",
                published_at=datetime.utcnow(),
            ),
            NewsItem(
                ticker=None,
                sector="Technology",
                title="Semiconductor demand remains strong",
                summary="Market watchers highlight strong chip demand in 2026.",
                source="Demo News",
                source_url="https://example.com/semiconductors",
                published_at=datetime.utcnow(),
            ),
        ]
        session.add_all(demo)
        session.commit()

    def _should_use_newsapi(self) -> bool:
        return settings.news_provider in {"auto", "newsapi"} and bool(settings.newsapi_key)

    def _should_use_finnhub(self) -> bool:
        return settings.news_provider in {"auto", "finnhub"} and bool(settings.finnhub_api_key)

    def _should_use_search(self) -> bool:
        return settings.news_provider == "search" and self._search_service.is_enabled()

    def _ingest_search(
        self,
        session: Session,
        ticker: str,
        company_name: Optional[str],
        sector: Optional[str],
        limit: int,
    ) -> List[dict]:
        query = self._build_search_query(ticker, company_name, sector)
        if not query:
            return []

        try:
            search_results = self._search_service.search(query, top_k=min(max(limit, 1), settings.search_top_k))
        except Exception:
            return []

        enriched = self._search_agent.analyze_results(query, search_results)
        seen = self._existing_dedupe_keys(session)
        inserted = []
        for item in enriched:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            source_url = (item.get("source_url") or "").strip()
            dedupe_key = self._dedupe_key(title, source_url)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            record = NewsItem(
                ticker=ticker,
                sector=sector,
                title=title,
                summary=str(item.get("summary") or "")[:500],
                source=str(item.get("source") or "Search Intelligence"),
                source_url=source_url,
                published_at=datetime.utcnow(),
            )
            session.add(record)
            inserted.append({
                "ticker": ticker,
                "title": record.title,
                "summary": record.summary,
                "source": record.source,
                "source_url": record.source_url,
                "published_at": record.published_at.isoformat(),
            })
        if inserted:
            session.commit()
        return inserted

    def _ingest_newsapi(
        self,
        session: Session,
        ticker: str,
        company_name: Optional[str],
        sector: Optional[str],
        limit: int,
    ) -> List[dict]:
        query = self._build_newsapi_query(ticker, company_name, sector)
        if not query:
            return []

        from_date = (datetime.now(timezone.utc) - timedelta(days=settings.news_lookback_days)).date().isoformat()
        params = {
            "q": query,
            "language": settings.news_language,
            "sortBy": "publishedAt",
            "pageSize": min(max(limit, 1), 20),
            "from": from_date,
        }
        headers = {"X-Api-Key": settings.newsapi_key}

        try:
            with external_network_env():
                response = external_api_guard.call(
                    "newsapi",
                    lambda: requests.get(
                        "https://newsapi.org/v2/everything",
                        params=params,
                        headers=headers,
                        timeout=15,
                    ),
                    cache_key=f"newsapi:{query}:{from_date}:{limit}:{settings.news_language}",
                )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        articles = payload.get("articles") or []
        inserted = []
        seen = self._existing_dedupe_keys(session)
        for article in articles:
            title = (article.get("title") or "").strip()
            if not title:
                continue
            source_url = (article.get("url") or "").strip()
            dedupe_key = self._dedupe_key(title, source_url)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            record = NewsItem(
                ticker=ticker,
                sector=sector,
                title=title,
                summary=(article.get("description") or article.get("content") or "")[:500],
                source=((article.get("source") or {}).get("name") or "NewsAPI"),
                source_url=source_url,
                published_at=self._parse_datetime(article.get("publishedAt")),
            )
            session.add(record)
            inserted.append({
                "ticker": ticker,
                "title": record.title,
                "summary": record.summary,
                "source": record.source,
                "source_url": record.source_url,
                "published_at": record.published_at.isoformat(),
            })
        if inserted:
            session.commit()
        return inserted

    def _ingest_finnhub(
        self,
        session: Session,
        ticker: str,
        company_name: Optional[str],
        sector: Optional[str],
        limit: int,
    ) -> List[dict]:
        from_date = (datetime.now(timezone.utc) - timedelta(days=settings.news_lookback_days)).date().isoformat()
        to_date = datetime.now(timezone.utc).date().isoformat()
        discovered = self._discover_finnhub_symbols(ticker, company_name)
        candidates = build_finnhub_symbol_candidates(ticker, company_name, discovered)

        payload = []
        for symbol in candidates:
            try:
                with external_network_env():
                    response = external_api_guard.call(
                        "finnhub",
                        lambda: requests.get(
                            "https://finnhub.io/api/v1/company-news",
                            params={
                                "symbol": symbol,
                                "from": from_date,
                                "to": to_date,
                                "token": settings.finnhub_api_key,
                            },
                            timeout=15,
                        ),
                        cache_key=f"finnhub_news:{symbol}:{from_date}:{to_date}:{limit}",
                        cache_ttl_seconds=900,
                    )
                response.raise_for_status()
                payload = response.json()
            except Exception:
                continue
            if isinstance(payload, list) and payload:
                break

        articles = payload if isinstance(payload, list) else []
        inserted = []
        seen = self._existing_dedupe_keys(session)
        for article in articles[:limit]:
            title = (article.get("headline") or article.get("title") or "").strip()
            if not title:
                continue
            source_url = (article.get("url") or "").strip()
            dedupe_key = self._dedupe_key(title, source_url)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            record = NewsItem(
                ticker=ticker,
                sector=sector,
                title=title,
                summary=((article.get("summary") or article.get("text") or "")[:500]),
                source=str(article.get("source") or "Finnhub"),
                source_url=source_url,
                published_at=self._parse_datetime(article.get("datetime")),
            )
            session.add(record)
            inserted.append({
                "ticker": ticker,
                "title": record.title,
                "summary": record.summary,
                "source": record.source,
                "source_url": record.source_url,
                "published_at": record.published_at.isoformat(),
            })
        if inserted:
            session.commit()
        return inserted

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

    def _ingest_yfinance(self, session: Session, ticker: str, limit: int) -> List[dict]:
        try:
            import yfinance as yf
        except ImportError:
            return []

        try:
            with yfinance_network_env():
                raw = external_api_guard.call(
                    "yfinance_news",
                    lambda: yf.Ticker(ticker).news or [],
                    cache_key=f"yfinance_news:{ticker}:{limit}",
                )
        except Exception:
            return []

        inserted = []
        seen = self._existing_dedupe_keys(session)
        for item in raw[:limit]:
            content = item.get("content", {})
            title = (content.get("title") or item.get("title", "")).strip()
            if not title:
                continue
            source_url = (
                (content.get("canonicalUrl") or {}).get("url", "")
                or item.get("link", "")
            ).strip()
            dedupe_key = self._dedupe_key(title, source_url)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            record = NewsItem(
                ticker=ticker,
                sector=None,
                title=title,
                summary=((content.get("summary") or content.get("description") or "")[:500]),
                source=((content.get("provider") or {}).get("displayName", "") or item.get("publisher", "Yahoo Finance")),
                source_url=source_url,
                published_at=self._parse_datetime(content.get("pubDate") or item.get("providerPublishTime")),
            )
            session.add(record)
            inserted.append({
                "ticker": ticker,
                "title": record.title,
                "summary": record.summary,
                "source": record.source,
                "source_url": record.source_url,
                "published_at": record.published_at.isoformat(),
            })
        if inserted:
            session.commit()
        return inserted

    def _load_recent_real_news(self, session: Session, ticker: str, limit: int) -> List[dict]:
        cutoff = datetime.utcnow() - timedelta(hours=12)
        rows = (
            session.query(NewsItem)
            .filter(
                NewsItem.ticker == ticker,
                NewsItem.published_at >= cutoff,
                NewsItem.source != "Demo News",
                NewsItem.source != "Demo IPO News",
            )
            .order_by(NewsItem.published_at.desc())
            .limit(limit)
            .all()
        )
        return [{
            "ticker": row.ticker or ticker,
            "title": row.title,
            "summary": row.summary,
            "source": row.source,
            "source_url": row.source_url,
            "published_at": row.published_at.isoformat() if row.published_at else None,
        } for row in rows]

    def _load_fallback_news(self, session: Session, ticker: str, sector: Optional[str], limit: int) -> List[dict]:
        rows = (
            session.query(NewsItem)
            .filter(NewsItem.ticker == ticker)
            .order_by(NewsItem.published_at.desc())
            .limit(limit)
            .all()
        )
        if not rows and sector:
            rows = (
                session.query(NewsItem)
                .filter(NewsItem.sector == sector)
                .order_by(NewsItem.published_at.desc())
                .limit(limit)
                .all()
            )
        if not rows:
            rows = (
                session.query(NewsItem)
                .order_by(NewsItem.published_at.desc())
                .limit(limit)
                .all()
            )
        return [{
            "ticker": row.ticker or ticker,
            "title": row.title,
            "summary": row.summary,
            "source": row.source,
            "source_url": row.source_url,
            "published_at": row.published_at.isoformat() if row.published_at else None,
        } for row in rows]

    def _existing_dedupe_keys(self, session: Session) -> set[str]:
        rows = session.query(NewsItem.title, NewsItem.source_url).all()
        return {self._dedupe_key(title or "", source_url or "") for title, source_url in rows}

    def _build_newsapi_query(self, ticker: str, company_name: Optional[str], sector: Optional[str]) -> str:
        parts = []
        if company_name:
            parts.append(f'"{company_name}"')
        if ticker and "." not in ticker:
            parts.append(ticker)
        if sector:
            parts.append(f'"{sector}"')
        return " OR ".join(parts[:3])

    def _build_search_query(self, ticker: str, company_name: Optional[str], sector: Optional[str]) -> str:
        parts = []
        if company_name:
            parts.append(company_name)
        if ticker:
            parts.append(ticker)
        if sector:
            parts.append(sector)
        parts.append("latest investment news catalyst")
        return " ".join(part for part in parts if part).strip()

    @staticmethod
    def _dedupe_key(title: str, source_url: str) -> str:
        return f"{title.strip().lower()}|{source_url.strip().lower()}"

    @staticmethod
    def _parse_datetime(value) -> datetime:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        if isinstance(value, (int, float)):
            return datetime.utcfromtimestamp(int(value))
        if isinstance(value, str) and value:
            normalized = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized).replace(tzinfo=None)
            except ValueError:
                pass
        return datetime.utcnow()
