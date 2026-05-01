import os
import re
from typing import Dict, Optional

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None

from app.config import settings


class ImpactAgent:
    """Analyze event impact using OpenAI or fallback rules."""

    def analyze(self, item: Dict[str, object]) -> Dict[str, object]:
        if settings.openai_api_key and openai:
            return self._openai_analysis(item)
        return self._fallback_analysis(item)

    def _openai_analysis(self, item: Dict[str, object]) -> Dict[str, object]:
        openai.api_key = settings.openai_api_key
        prompt = self._build_prompt(item)
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
            text = response.choices[0].message.content.strip()
            return self._parse_openai_response(text, item)
        except Exception:
            return self._fallback_analysis(item)

    def _build_prompt(self, item: Dict[str, object]) -> str:
        return (
            "Analyze the following investment intelligence signal and provide a structured analysis. "
            f"Item: {item}\n"
            "Answer with impact_direction, impact_level, summary, reasoning, confidence."
        )

    def _parse_openai_response(self, text: str, item: Dict[str, object]) -> Dict[str, object]:
        return {
            "related_alert_id": item.get("related_alert_id"),
            "related_news_id": item.get("related_news_id"),
            "ticker": item.get("ticker"),
            "impact_direction": self._extract_field(text, "impact_direction") or "unknown",
            "impact_level": self._extract_field(text, "impact_level") or "medium",
            "summary": self._extract_field(text, "summary") or text,
            "reasoning": self._extract_field(text, "reasoning") or "Generated from OpenAI.",
            "confidence": float(self._extract_field(text, "confidence") or 0.7),
        }

    def _extract_field(self, text: str, field: str) -> Optional[str]:
        match = re.search(rf"{field}\s*[:=]\s*(.+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _fallback_analysis(self, item: Dict[str, object]) -> Dict[str, object]:
        direction = "unknown"
        level = "low"
        reason = "Using rule-based fallback analysis."
        summary = "No strong signal detected."
        confidence = 0.6

        value = item.get("value")
        event_type = item.get("event_type") or item.get("alert_type")
        title = str(item.get("title", "")).lower()

        if event_type == "price_move" and value is not None:
            if value >= 5:
                direction = "positive"
                level = "high"
                summary = "Positive momentum from a strong upward move."
                reason = "Price moved upward above the alert threshold."
                confidence = 0.8
            elif value <= -5:
                direction = "negative"
                level = "high"
                summary = "Negative momentum from a strong downward move."
                reason = "Price moved downward below the alert threshold."
                confidence = 0.8
            else:
                direction = "neutral"
                level = "low"
                summary = "Price move is within threshold boundaries."

        elif event_type in {"earnings", "dividend", "stock_split", "investor_day", "company_event", "ipo", "regulatory"}:
            if "beat" in title or "strong" in title or "upgrade" in title:
                direction = "positive"
                level = "medium"
                summary = "Catalyst appears positive based on event type and wording."
                confidence = 0.7
            elif "miss" in title or "weak" in title or "downgrade" in title:
                direction = "negative"
                level = "medium"
                summary = "Catalyst appears negative based on event type and wording."
                confidence = 0.7
            else:
                direction = "neutral"
                level = "medium"
                summary = "Catalyst is not clearly directional from the current data."

        elif "ipo" in title or "hkex" in title:
            direction = "unknown"
            level = "medium"
            summary = "IPO and market events require follow-up analysis."
            confidence = 0.5

        return {
            "related_alert_id": item.get("related_alert_id"),
            "related_news_id": item.get("related_news_id"),
            "ticker": item.get("ticker"),
            "impact_direction": direction,
            "impact_level": level,
            "summary": summary,
            "reasoning": reason,
            "confidence": confidence,
        }
