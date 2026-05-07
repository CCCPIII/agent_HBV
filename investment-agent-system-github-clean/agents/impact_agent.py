"""
ImpactAgent — multi-provider LLM analysis with rule-based fallback.

Supported providers (set ACTIVE_LLM_PROVIDER in .env):
  openai    → OpenAI API           (gpt-4o-mini)
  deepseek  → DeepSeek API         (deepseek-chat)
  kimi      → Moonshot/KIMI API    (moonshot-v1-8k)
  zhipu     → Zhipu GLM API        (glm-4-flash)
  gemini    → Google Gemini API    (gemini-2.0-flash)
  claude    → Anthropic Claude API (claude-haiku-4-5-20251001)

DeepSeek, KIMI, Zhipu, and Gemini all expose an OpenAI-compatible interface,
so the openai SDK is reused with a custom base_url. Claude uses the anthropic SDK.
"""

import re
from hashlib import sha1
from typing import Dict, Optional

from app.config import settings
from services.external_api_guard import external_api_guard
from services.network_env import external_network_env

# ── OpenAI-compatible providers ─────────────────────────────────────────────
_OPENAI_COMPAT = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model_key": "openai_model",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model_key": "deepseek_model",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model_key": "kimi_model",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "model_key": "zhipu_model",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model_key": "gemini_model",
    },
}

_ANALYSIS_PROMPT = (
    "You are an investment analyst. Analyze the following signal and reply with "
    "exactly these fields on separate lines:\n"
    "impact_direction: <positive|negative|neutral|unknown>\n"
    "impact_level: <high|medium|low>\n"
    "summary: <one concise sentence>\n"
    "reasoning: <one concise sentence>\n"
    "confidence: <float 0.0-1.0>\n\n"
    "Signal data:\n{item}"
)


class LLMRouter:
    """Route LLM calls to the active provider."""

    def call(self, item: Dict) -> Optional[str]:
        provider = settings.active_llm_provider
        key = settings.active_api_key()
        if not key:
            return None

        prompt = _ANALYSIS_PROMPT.format(item=item)

        if provider in _OPENAI_COMPAT:
            return self._call_openai_compat(provider, key, prompt)
        if provider == "claude":
            return self._call_claude(key, prompt)
        return None

    def _call_openai_compat(self, provider: str, api_key: str, prompt: str) -> Optional[str]:
        try:
            from openai import OpenAI
        except ImportError:
            return None

        cfg = _OPENAI_COMPAT[provider]
        model = getattr(settings, cfg["model_key"])
        client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
        try:
            cache_key = f"llm:{provider}:{model}:{sha1(prompt.encode('utf-8')).hexdigest()}"
            with external_network_env():
                resp = external_api_guard.call(
                    "llm",
                    lambda: client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=300,
                        temperature=0.3,
                    ),
                    cache_key=cache_key,
                    cache_ttl_seconds=180,
                )
            return resp.choices[0].message.content.strip()
        except Exception:
            return None

    def _call_claude(self, api_key: str, prompt: str) -> Optional[str]:
        try:
            import anthropic
        except ImportError:
            return None

        client = anthropic.Anthropic(api_key=api_key)
        try:
            cache_key = f"llm:claude:{settings.claude_model}:{sha1(prompt.encode('utf-8')).hexdigest()}"
            with external_network_env():
                msg = external_api_guard.call(
                    "llm",
                    lambda: client.messages.create(
                        model=settings.claude_model,
                        max_tokens=300,
                        messages=[{"role": "user", "content": prompt}],
                    ),
                    cache_key=cache_key,
                    cache_ttl_seconds=180,
                )
            return msg.content[0].text.strip()
        except Exception:
            return None


class ImpactAgent:
    """Analyze event impact using the configured LLM provider, or fallback rules."""

    def __init__(self):
        self._router = LLMRouter()

    def analyze(self, item: Dict) -> Dict:
        text = self._router.call(item)
        if text:
            return self._parse_response(text, item)
        return self._fallback_analysis(item)

    # ── Response parsing ─────────────────────────────────────────────────────

    def _parse_response(self, text: str, item: Dict) -> Dict:
        def get(field):
            m = re.search(rf"^{field}\s*[:=]\s*(.+)", text, re.IGNORECASE | re.MULTILINE)
            return m.group(1).strip() if m else None

        return {
            "related_alert_id": item.get("related_alert_id"),
            "related_news_id": item.get("related_news_id"),
            "ticker": item.get("ticker"),
            "impact_direction": get("impact_direction") or "unknown",
            "impact_level": get("impact_level") or "medium",
            "summary": get("summary") or text[:200],
            "reasoning": get("reasoning") or f"Analysis by {settings.active_llm_provider}.",
            "confidence": self._parse_float(get("confidence"), 0.7),
        }

    @staticmethod
    def _parse_float(value: Optional[str], default: float) -> float:
        try:
            return min(1.0, max(0.0, float(value or default)))
        except (TypeError, ValueError):
            return default

    # ── Rule-based fallback ──────────────────────────────────────────────────

    def _fallback_analysis(self, item: Dict) -> Dict:
        direction, level, confidence = "unknown", "low", 0.6
        summary = "No strong signal detected."
        reason = "Rule-based fallback (no LLM provider configured)."

        value = item.get("value")
        event_type = item.get("event_type") or item.get("alert_type")
        title = str(item.get("title", "")).lower()
        summary_text = str(item.get("summary", "")).lower()
        text = f"{title} {summary_text}"
        article_count = int(item.get("article_count") or 1)
        source_count = int(item.get("source_count") or 1)

        if event_type == "price_move" and value is not None:
            if value >= 5:
                direction, level, confidence = "positive", "high", 0.8
                summary = "Positive momentum from a strong upward move."
                reason = "Price moved above the alert threshold."
            elif value <= -5:
                direction, level, confidence = "negative", "high", 0.8
                summary = "Negative momentum from a strong downward move."
                reason = "Price moved below the alert threshold."
            else:
                direction, level = "neutral", "low"
                summary = "Price move is within threshold boundaries."

        elif event_type in {"earnings", "dividend", "stock_split", "investor_day",
                            "company_event", "ipo", "regulatory"}:
            if any(w in text for w in ("beat", "strong", "upgrade", "surge", "approval", "launch")):
                direction, level, confidence = "positive", "medium", 0.7
                summary = "Catalyst appears positive based on the event details."
            elif any(w in text for w in ("miss", "weak", "downgrade", "drop", "probe", "fine", "ban")):
                direction, level, confidence = "negative", "medium", 0.7
                summary = "Catalyst appears negative based on the event details."
            else:
                direction, level = "neutral", "medium"
                summary = "Catalyst direction is unclear from available data."

        elif event_type in {"product", "demand", "partnership", "ma", "leadership", "macro", "news"}:
            positive_hits = sum(
                1 for word in ("strong", "surge", "grow", "launch", "approval", "partnership", "record", "upgrade")
                if word in text
            )
            negative_hits = sum(
                1 for word in ("weak", "drop", "downgrade", "probe", "fine", "delay", "slump", "lawsuit", "ban")
                if word in text
            )
            if event_type == "regulatory" and negative_hits == 0:
                negative_hits += 1
            if positive_hits > negative_hits:
                direction = "positive"
            elif negative_hits > positive_hits:
                direction = "negative"
            else:
                direction = "neutral"

            confidence = 0.58 + min(0.12, 0.04 * max(article_count - 1, 0)) + min(0.1, 0.05 * max(source_count - 1, 0))
            if event_type in {"product", "demand", "partnership", "ma"}:
                level = "medium" if article_count >= 1 else "low"
            elif event_type in {"macro", "leadership"}:
                level = "medium"
            else:
                level = "low"

            label = {
                "product": "product cycle",
                "demand": "demand trend",
                "partnership": "commercial partnership",
                "ma": "corporate transaction",
                "leadership": "management change",
                "macro": "macro driver",
                "news": "news flow",
            }.get(event_type, "news event")
            summary = f"{label.capitalize()} signal built from {article_count} article(s) across {source_count} source(s)."
            reason = f"Rule-based event clustering inferred a {direction} bias from grouped coverage."

        elif "ipo" in title or "hkex" in title:
            direction, level, confidence = "unknown", "medium", 0.5
            summary = "IPO/market event requires follow-up analysis."

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
