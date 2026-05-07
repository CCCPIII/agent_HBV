from datetime import datetime, date
from typing import Dict, List

from app.models import NewsItem
from sqlalchemy.orm import Session
from services.external_api_guard import external_api_guard
from services.yfinance_env import yfinance_network_env

# Keywords that indicate IPO / new listing content
_IPO_KEYWORDS = {"ipo", "listing", "new share", "initial public", "打新", "新股", "上市招股", "招股"}


class IPOService:
    """Monitor IPO and Hong Kong market event data."""

    def get_recent_ipo_events(self, session: Session) -> List[Dict[str, object]]:
        today = date.today()
        return [
            {
                "title": "HKEX IPO subscription update",
                "event_type": "ipo",
                "description": "A new Hong Kong IPO subscription window is open.",
                "event_date": today,
                "source_url": "",
            }
        ]

    def get_market_news(self, limit: int = 30) -> List[Dict[str, object]]:
        """
        Fetch IPO and market event news from Yahoo Finance.
        Probes several HK-market proxies and filters by IPO keywords.
        Returns a list of dicts (does not touch the DB).
        """
        try:
            import yfinance as yf
        except ImportError:
            return []

        # Proxy tickers that tend to surface HK market / IPO news
        probe_tickers = ["^HSI", "0388.HK", "9988.HK", "0700.HK"]
        seen: set = set()
        results: List[Dict] = []

        for symbol in probe_tickers:
            if len(results) >= limit:
                break
            try:
                with yfinance_network_env():
                    raw = external_api_guard.call(
                        "yfinance_market_news",
                        lambda: yf.Ticker(symbol).news or [],
                        cache_key=f"yfinance_market_news:{symbol}:{limit}",
                    )
            except Exception:
                continue

            for item in raw[:15]:
                content = item.get("content", {})
                title = content.get("title") or item.get("title", "")
                if not title or title in seen:
                    continue

                title_lower = title.lower()
                summary_raw = (
                    content.get("summary")
                    or content.get("description")
                    or item.get("summary", "")
                    or ""
                )
                summary_lower = summary_raw.lower()

                # Keep only IPO-related items
                if not any(kw in title_lower or kw in summary_lower for kw in _IPO_KEYWORDS):
                    continue

                seen.add(title)
                pub = content.get("pubDate") or item.get("providerPublishTime", "")
                results.append({
                    "ticker": symbol,
                    "title": title,
                    "summary": summary_raw[:400],
                    "source": (
                        (content.get("provider") or {}).get("displayName", "")
                        or item.get("publisher", "Yahoo Finance")
                    ),
                    "source_url": (
                        (content.get("canonicalUrl") or {}).get("url", "")
                        or item.get("link", "")
                    ),
                    "published_at": str(pub) if pub else "",
                    "event_type": "ipo",
                })

        return results[:limit]

    def seed_demo_ipo(self, session: Session) -> None:
        if session.query(NewsItem).filter(NewsItem.title.contains("IPO")).count() > 0:
            return
        session.add(
            NewsItem(
                ticker=None,
                sector="IPO",
                title="Hong Kong IPO watch: new listings ahead",
                summary="A new Hong Kong IPO is tracking industry interest ahead of listing.",
                source="Demo IPO News",
                source_url="",
                published_at=datetime.utcnow(),
            )
        )
        session.commit()
