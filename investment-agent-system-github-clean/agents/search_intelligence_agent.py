import json
import re
from hashlib import sha1
from typing import Dict, List, Optional

from app.config import settings
from services.external_api_guard import external_api_guard
from services.network_env import external_network_env

_SEARCH_PROMPT = (
    "You are an investment news analyst. Given a search query and raw search results, "
    "return a JSON array with up to 5 items. Each item must contain: "
    "title, summary, source, source_url, impact_direction, impact_level, confidence. "
    "Keep summaries factual and concise.\n\n"
    "Query: {query}\n"
    "Raw results:\n{results}"
)


class SearchLLMRouter:
    def call(self, query: str, results: List[Dict[str, object]]) -> Optional[str]:
        provider = settings.active_llm_provider
        key = settings.active_api_key()
        if not key:
            return None

        prompt = _SEARCH_PROMPT.format(query=query, results=json.dumps(results, ensure_ascii=False))
        if provider in {"openai", "deepseek", "kimi", "zhipu", "gemini"}:
            return self._call_openai_compat(provider, key, prompt)
        if provider == "claude":
            return self._call_claude(key, prompt)
        return None

    def _call_openai_compat(self, provider: str, api_key: str, prompt: str) -> Optional[str]:
        try:
            from openai import OpenAI
        except ImportError:
            return None

        config = {
            "openai": ("https://api.openai.com/v1", settings.openai_model),
            "deepseek": ("https://api.deepseek.com", settings.deepseek_model),
            "kimi": ("https://api.moonshot.cn/v1", settings.kimi_model),
            "zhipu": ("https://open.bigmodel.cn/api/paas/v4/", settings.zhipu_model),
            "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", settings.gemini_model),
        }[provider]
        client = OpenAI(api_key=api_key, base_url=config[0])
        try:
            cache_key = f"llm:{provider}:{config[1]}:{sha1(prompt.encode('utf-8')).hexdigest()}"
            with external_network_env():
                response = external_api_guard.call(
                    "llm",
                    lambda: client.chat.completions.create(
                        model=config[1],
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2,
                        max_tokens=700,
                    ),
                    cache_key=cache_key,
                    cache_ttl_seconds=300,
                )
            return response.choices[0].message.content.strip()
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
                        max_tokens=700,
                        messages=[{"role": "user", "content": prompt}],
                    ),
                    cache_key=cache_key,
                    cache_ttl_seconds=300,
                )
            return msg.content[0].text.strip()
        except Exception:
            return None


class SearchIntelligenceAgent:
    def __init__(self):
        self._router = SearchLLMRouter()

    def analyze_results(self, query: str, results: List[Dict[str, object]]) -> List[Dict[str, object]]:
        text = self._router.call(query, results)
        if text:
            parsed = self._parse_json_array(text)
            if parsed:
                return parsed
        return self._fallback_results(results)

    def _parse_json_array(self, text: str) -> List[Dict[str, object]]:
        match = re.search(r"(\[\s*{.*}\s*\])", text, re.DOTALL)
        candidate = match.group(1) if match else text
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return []
        normalized = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            normalized.append({
                "title": str(item.get("title", "")).strip(),
                "summary": str(item.get("summary", "")).strip(),
                "source": str(item.get("source", "Search Intelligence")).strip(),
                "source_url": str(item.get("source_url", "")).strip(),
                "impact_direction": str(item.get("impact_direction", "neutral")).strip().lower(),
                "impact_level": str(item.get("impact_level", "medium")).strip().lower(),
                "confidence": float(item.get("confidence", 0.65) or 0.65),
            })
        return normalized

    def _fallback_results(self, results: List[Dict[str, object]]) -> List[Dict[str, object]]:
        normalized = []
        for item in results[:5]:
            text = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
            positive = sum(word in text for word in ("strong", "launch", "grow", "beat", "approval", "partnership"))
            negative = sum(word in text for word in ("weak", "drop", "probe", "lawsuit", "delay", "ban"))
            direction = "positive" if positive > negative else "negative" if negative > positive else "neutral"
            normalized.append({
                "title": str(item.get("title", "")).strip(),
                "summary": str(item.get("snippet", "")).strip()[:400],
                "source": str(item.get("source", "Search Intelligence")).strip(),
                "source_url": str(item.get("url", "")).strip(),
                "impact_direction": direction,
                "impact_level": "medium" if item.get("snippet") else "low",
                "confidence": 0.6,
            })
        return normalized
