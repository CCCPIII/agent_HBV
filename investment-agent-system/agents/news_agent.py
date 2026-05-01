from typing import Dict


class NewsAgent:
    """Normalize news items and classify the scope of the item."""

    def normalize(self, news: Dict[str, object]) -> Dict[str, object]:
        scope = "company"
        if news.get("ticker") is None and news.get("sector"):
            scope = "sector"
        if news.get("ticker") is None and news.get("sector") is None:
            scope = "market"
        if "ipo" in news.get("title", "").lower():
            scope = "ipo"

        return {
            "ticker": news.get("ticker"),
            "sector": news.get("sector"),
            "title": news.get("title"),
            "summary": news.get("summary"),
            "source": news.get("source"),
            "source_url": news.get("source_url"),
            "published_at": news.get("published_at"),
            "scope": scope,
        }
