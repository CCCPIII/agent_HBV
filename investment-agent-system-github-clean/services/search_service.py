from typing import Any, Dict, List

import requests

from app.config import settings
from services.external_api_guard import external_api_guard
from services.network_env import external_network_env


class SearchService:
    """Pluggable external search adapters for news intelligence."""

    def is_enabled(self) -> bool:
        return settings.search_provider != "disabled" and bool(
            settings.search_api_key or settings.search_provider in {"gnews"}
        )

    def search(self, query: str, top_k: int | None = None) -> List[Dict[str, Any]]:
        top_k = top_k or settings.search_top_k
        provider = settings.search_provider

        if provider == "tavily":
            return self._search_tavily(query, top_k)
        if provider == "serpapi":
            return self._search_serpapi(query, top_k)
        if provider == "gnews":
            return self._search_gnews(query, top_k)
        if provider == "custom":
            return self._search_custom(query, top_k)
        return []

    def _search_tavily(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        with external_network_env():
            response = external_api_guard.call(
                "search",
                lambda: requests.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.search_api_key,
                        "query": query,
                        "max_results": top_k,
                        "include_raw_content": False,
                    },
                    timeout=20,
                ),
                cache_key=f"tavily:{query}:{top_k}",
            )
        response.raise_for_status()
        payload = response.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "source": "Tavily",
                "published_at": item.get("published_date"),
            }
            for item in (payload.get("results") or [])[:top_k]
        ]

    def _search_serpapi(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        with external_network_env():
            response = external_api_guard.call(
                "search",
                lambda: requests.get(
                    "https://serpapi.com/search.json",
                    params={
                        "q": query,
                        "api_key": settings.search_api_key,
                        "engine": "google",
                        "num": top_k,
                    },
                    timeout=20,
                ),
                cache_key=f"serpapi:{query}:{top_k}",
            )
        response.raise_for_status()
        payload = response.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": "SerpAPI",
                "published_at": None,
            }
            for item in (payload.get("organic_results") or [])[:top_k]
        ]

    def _search_gnews(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        with external_network_env():
            response = external_api_guard.call(
                "search",
                lambda: requests.get(
                    "https://gnews.io/api/v4/search",
                    params={
                        "q": query,
                        "token": settings.search_api_key,
                        "lang": settings.news_language,
                        "max": top_k,
                    },
                    timeout=20,
                ),
                cache_key=f"gnews:{query}:{top_k}:{settings.news_language}",
            )
        response.raise_for_status()
        payload = response.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
                "source": (item.get("source") or {}).get("name", "GNews"),
                "published_at": item.get("publishedAt"),
            }
            for item in (payload.get("articles") or [])[:top_k]
        ]

    def _search_custom(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        if not settings.search_api_url:
            return []

        headers = {}
        if settings.search_api_key:
            headers[settings.search_api_key_header] = f"{settings.search_api_key_prefix}{settings.search_api_key}"

        if settings.search_http_method == "GET":
            with external_network_env():
                response = external_api_guard.call(
                    "search",
                    lambda: requests.get(
                        settings.search_api_url,
                        params={
                            settings.search_query_param: query,
                            "top_k": top_k,
                        },
                        headers=headers,
                        timeout=20,
                    ),
                    cache_key=f"custom-get:{settings.search_api_url}:{query}:{top_k}",
                )
        else:
            with external_network_env():
                response = external_api_guard.call(
                    "search",
                    lambda: requests.post(
                        settings.search_api_url,
                        json={
                            settings.search_query_param: query,
                            "top_k": top_k,
                        },
                        headers=headers,
                        timeout=20,
                    ),
                    cache_key=f"custom-post:{settings.search_api_url}:{query}:{top_k}",
                )

        response.raise_for_status()
        payload = response.json()
        results = self._dig(payload, settings.search_results_path)
        normalized = []
        for item in (results or [])[:top_k]:
            if not isinstance(item, dict):
                continue
            normalized.append({
                "title": item.get(settings.search_title_field, ""),
                "url": item.get(settings.search_url_field, ""),
                "snippet": item.get(settings.search_snippet_field, ""),
                "source": "Custom Search",
                "published_at": item.get("published_at") or item.get("publishedAt"),
            })
        return normalized

    @staticmethod
    def _dig(payload: Dict[str, Any], path: str) -> Any:
        value: Any = payload
        for part in (path or "").split("."):
            if not part:
                continue
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value
