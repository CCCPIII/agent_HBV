from typing import Dict


class CatalystAgent:
    """Normalize catalyst events and classify source type."""

    def normalize(self, event: Dict[str, object]) -> Dict[str, object]:
        normalized = {
            "ticker": event.get("ticker"),
            "title": event.get("title"),
            "catalyst_type": event.get("catalyst_type", "other"),
            "event_date": event.get("event_date"),
            "source_url": event.get("source_url"),
            "confidence": float(event.get("confidence", 0.7)),
            "source": event.get("source", "manual"),
            "is_ai_discovered": bool(event.get("is_ai_discovered", False)),
        }
        return normalized
