from typing import Dict


class IPOAgent:
    """Normalize IPO and market events."""

    def normalize(self, event: Dict[str, object]) -> Dict[str, object]:
        normalized = {
            "title": event.get("title"),
            "event_type": event.get("event_type", "ipo"),
            "description": event.get("description"),
            "event_date": event.get("event_date"),
            "source_url": event.get("source_url"),
            "ticker": event.get("ticker"),
        }
        return normalized
