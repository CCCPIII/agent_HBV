import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv, set_key, dotenv_values

ENV_FILE = Path(os.getenv("ENV_FILE", ".env"))

load_dotenv(dotenv_path=ENV_FILE)

SUPPORTED_PROVIDERS = ("openai", "deepseek", "kimi", "zhipu", "gemini", "claude")

# All recognised .env keys and their defaults
_DEFAULTS: dict = {
    "DATABASE_URL": "sqlite:///./investment_agent.db",
    "USE_MOCK_DATA": "false",  # Set to 'true' to use simulated market data
    "NEWS_PROVIDER": "auto",
    "NEWSAPI_KEY": "",
    "NEWS_LANGUAGE": "en",
    "NEWS_LOOKBACK_DAYS": "7",
    "SEARCH_PROVIDER": "disabled",
    "SEARCH_API_KEY": "",
    "SEARCH_API_URL": "",
    "SEARCH_HTTP_METHOD": "POST",
    "SEARCH_QUERY_PARAM": "q",
    "SEARCH_RESULTS_PATH": "results",
    "SEARCH_TITLE_FIELD": "title",
    "SEARCH_URL_FIELD": "url",
    "SEARCH_SNIPPET_FIELD": "snippet",
    "SEARCH_API_KEY_HEADER": "Authorization",
    "SEARCH_API_KEY_PREFIX": "Bearer ",
    "SEARCH_TOP_K": "5",
    "EXTERNAL_API_THROTTLE_MULTIPLIER": "1.0",
    "EXTERNAL_API_WINDOW_SECONDS": "60",
    "EXTERNAL_API_COOLDOWN_SECONDS": "180",
    "EXTERNAL_API_MIN_CACHE_SECONDS": "60",
    "CATALYST_PROVIDER": "auto",
    "FINNHUB_API_KEY": "",
    "CATALYST_LOOKAHEAD_DAYS": "30",
    "ACTIVE_LLM_PROVIDER": "openai",
    "OPENAI_API_KEY": "",
    "OPENAI_MODEL": "gpt-4o-mini",
    "DEEPSEEK_API_KEY": "",
    "DEEPSEEK_MODEL": "deepseek-chat",
    "KIMI_API_KEY": "",
    "KIMI_MODEL": "moonshot-v1-8k",
    "ZHIPU_API_KEY": "",
    "ZHIPU_MODEL": "glm-4-flash",
    "GEMINI_API_KEY": "",
    "GEMINI_MODEL": "gemini-2.0-flash",
    "CLAUDE_API_KEY": "",
    "CLAUDE_MODEL": "claude-haiku-4-5-20251001",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "PRICE_ALERT_DEFAULT_THRESHOLD": "5.0",
    "MONITOR_INTERVAL_MINUTES": "30",
}

_SECRET_KEYS = {
    "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "KIMI_API_KEY",
    "ZHIPU_API_KEY", "GEMINI_API_KEY", "CLAUDE_API_KEY",
    "TELEGRAM_BOT_TOKEN", "NEWSAPI_KEY", "FINNHUB_API_KEY", "SEARCH_API_KEY",
}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


class Settings:
    def __init__(self):
        self._reload()

    def _reload(self):
        load_dotenv(dotenv_path=ENV_FILE, override=True)
        self.database_url = os.getenv("DATABASE_URL", _DEFAULTS["DATABASE_URL"])
        self.use_mock_data = os.getenv("USE_MOCK_DATA", "false").lower() in ("true", "1", "yes")
        self.news_provider = os.getenv("NEWS_PROVIDER", _DEFAULTS["NEWS_PROVIDER"]).lower()
        self.newsapi_key = os.getenv("NEWSAPI_KEY") or None
        self.news_language = os.getenv("NEWS_LANGUAGE", _DEFAULTS["NEWS_LANGUAGE"]).lower()
        self.news_lookback_days = int(os.getenv("NEWS_LOOKBACK_DAYS", _DEFAULTS["NEWS_LOOKBACK_DAYS"]))
        self.search_provider = os.getenv("SEARCH_PROVIDER", _DEFAULTS["SEARCH_PROVIDER"]).lower()
        self.search_api_key = os.getenv("SEARCH_API_KEY") or None
        self.search_api_url = os.getenv("SEARCH_API_URL", _DEFAULTS["SEARCH_API_URL"])
        self.search_http_method = os.getenv("SEARCH_HTTP_METHOD", _DEFAULTS["SEARCH_HTTP_METHOD"]).upper()
        self.search_query_param = os.getenv("SEARCH_QUERY_PARAM", _DEFAULTS["SEARCH_QUERY_PARAM"])
        self.search_results_path = os.getenv("SEARCH_RESULTS_PATH", _DEFAULTS["SEARCH_RESULTS_PATH"])
        self.search_title_field = os.getenv("SEARCH_TITLE_FIELD", _DEFAULTS["SEARCH_TITLE_FIELD"])
        self.search_url_field = os.getenv("SEARCH_URL_FIELD", _DEFAULTS["SEARCH_URL_FIELD"])
        self.search_snippet_field = os.getenv("SEARCH_SNIPPET_FIELD", _DEFAULTS["SEARCH_SNIPPET_FIELD"])
        self.search_api_key_header = os.getenv("SEARCH_API_KEY_HEADER", _DEFAULTS["SEARCH_API_KEY_HEADER"])
        self.search_api_key_prefix = os.getenv("SEARCH_API_KEY_PREFIX", _DEFAULTS["SEARCH_API_KEY_PREFIX"])
        self.search_top_k = int(os.getenv("SEARCH_TOP_K", _DEFAULTS["SEARCH_TOP_K"]))
        self.external_api_throttle_multiplier = float(
            os.getenv("EXTERNAL_API_THROTTLE_MULTIPLIER", _DEFAULTS["EXTERNAL_API_THROTTLE_MULTIPLIER"])
        )
        self.external_api_window_seconds = int(
            os.getenv("EXTERNAL_API_WINDOW_SECONDS", _DEFAULTS["EXTERNAL_API_WINDOW_SECONDS"])
        )
        self.external_api_cooldown_seconds = int(
            os.getenv("EXTERNAL_API_COOLDOWN_SECONDS", _DEFAULTS["EXTERNAL_API_COOLDOWN_SECONDS"])
        )
        self.external_api_min_cache_seconds = int(
            os.getenv("EXTERNAL_API_MIN_CACHE_SECONDS", _DEFAULTS["EXTERNAL_API_MIN_CACHE_SECONDS"])
        )
        self.catalyst_provider = os.getenv("CATALYST_PROVIDER", _DEFAULTS["CATALYST_PROVIDER"]).lower()
        self.finnhub_api_key = os.getenv("FINNHUB_API_KEY") or None
        self.catalyst_lookahead_days = int(os.getenv("CATALYST_LOOKAHEAD_DAYS", _DEFAULTS["CATALYST_LOOKAHEAD_DAYS"]))
        self.active_llm_provider = os.getenv("ACTIVE_LLM_PROVIDER", "openai").lower()
        self.openai_api_key = os.getenv("OPENAI_API_KEY") or None
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY") or None
        self.kimi_api_key = os.getenv("KIMI_API_KEY") or None
        self.zhipu_api_key = os.getenv("ZHIPU_API_KEY") or None
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or None
        self.claude_api_key = os.getenv("CLAUDE_API_KEY") or None
        self.openai_model = os.getenv("OPENAI_MODEL", _DEFAULTS["OPENAI_MODEL"])
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", _DEFAULTS["DEEPSEEK_MODEL"])
        self.kimi_model = os.getenv("KIMI_MODEL", _DEFAULTS["KIMI_MODEL"])
        self.zhipu_model = os.getenv("ZHIPU_MODEL", _DEFAULTS["ZHIPU_MODEL"])
        self.gemini_model = os.getenv("GEMINI_MODEL", _DEFAULTS["GEMINI_MODEL"])
        self.claude_model = os.getenv("CLAUDE_MODEL", _DEFAULTS["CLAUDE_MODEL"])
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or None
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID") or None
        self.price_alert_default_threshold = float(
            os.getenv("PRICE_ALERT_DEFAULT_THRESHOLD", "5.0")
        )
        self.monitor_interval_minutes = int(
            os.getenv("MONITOR_INTERVAL_MINUTES", "30")
        )

    # ── Provider helpers ────────────────────────────────────────────────────

    def active_api_key(self) -> Optional[str]:
        return {
            "openai": self.openai_api_key,
            "deepseek": self.deepseek_api_key,
            "kimi": self.kimi_api_key,
            "zhipu": self.zhipu_api_key,
            "gemini": self.gemini_api_key,
            "claude": self.claude_api_key,
        }.get(self.active_llm_provider)

    def providers_status(self) -> dict:
        keys = {
            "openai": self.openai_api_key,
            "deepseek": self.deepseek_api_key,
            "kimi": self.kimi_api_key,
            "zhipu": self.zhipu_api_key,
            "gemini": self.gemini_api_key,
            "claude": self.claude_api_key,
        }
        models = {
            "openai": self.openai_model,
            "deepseek": self.deepseek_model,
            "kimi": self.kimi_model,
            "zhipu": self.zhipu_model,
            "gemini": self.gemini_model,
            "claude": self.claude_model,
        }
        return {
            p: {"configured": bool(k), "model": models[p], "active": p == self.active_llm_provider}
            for p, k in keys.items()
        }

    # ── .env read/write ─────────────────────────────────────────────────────

    def get_all_for_ui(self) -> dict:
        """Return all settings grouped by category. API keys are masked."""
        raw = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}

        def val(key):
            return raw.get(key, _DEFAULTS.get(key, ""))

        def masked(key):
            v = raw.get(key, "")
            return _mask(v) if v else ""

        return {
            "database": {
                "DATABASE_URL": val("DATABASE_URL"),
            },
            "news": {
                "NEWS_PROVIDER": val("NEWS_PROVIDER") or _DEFAULTS["NEWS_PROVIDER"],
                "NEWSAPI_KEY": {"masked": masked("NEWSAPI_KEY"), "set": bool(raw.get("NEWSAPI_KEY"))},
                "NEWS_LANGUAGE": val("NEWS_LANGUAGE") or _DEFAULTS["NEWS_LANGUAGE"],
                "NEWS_LOOKBACK_DAYS": val("NEWS_LOOKBACK_DAYS") or _DEFAULTS["NEWS_LOOKBACK_DAYS"],
            },
            "search": {
                "SEARCH_PROVIDER": val("SEARCH_PROVIDER") or _DEFAULTS["SEARCH_PROVIDER"],
                "SEARCH_API_KEY": {"masked": masked("SEARCH_API_KEY"), "set": bool(raw.get("SEARCH_API_KEY"))},
                "SEARCH_API_URL": val("SEARCH_API_URL") or _DEFAULTS["SEARCH_API_URL"],
                "SEARCH_HTTP_METHOD": val("SEARCH_HTTP_METHOD") or _DEFAULTS["SEARCH_HTTP_METHOD"],
                "SEARCH_QUERY_PARAM": val("SEARCH_QUERY_PARAM") or _DEFAULTS["SEARCH_QUERY_PARAM"],
                "SEARCH_RESULTS_PATH": val("SEARCH_RESULTS_PATH") or _DEFAULTS["SEARCH_RESULTS_PATH"],
                "SEARCH_TITLE_FIELD": val("SEARCH_TITLE_FIELD") or _DEFAULTS["SEARCH_TITLE_FIELD"],
                "SEARCH_URL_FIELD": val("SEARCH_URL_FIELD") or _DEFAULTS["SEARCH_URL_FIELD"],
                "SEARCH_SNIPPET_FIELD": val("SEARCH_SNIPPET_FIELD") or _DEFAULTS["SEARCH_SNIPPET_FIELD"],
                "SEARCH_API_KEY_HEADER": val("SEARCH_API_KEY_HEADER") or _DEFAULTS["SEARCH_API_KEY_HEADER"],
                "SEARCH_API_KEY_PREFIX": val("SEARCH_API_KEY_PREFIX") or _DEFAULTS["SEARCH_API_KEY_PREFIX"],
                "SEARCH_TOP_K": val("SEARCH_TOP_K") or _DEFAULTS["SEARCH_TOP_K"],
            },
            "external_api": {
                "EXTERNAL_API_THROTTLE_MULTIPLIER": val("EXTERNAL_API_THROTTLE_MULTIPLIER") or _DEFAULTS["EXTERNAL_API_THROTTLE_MULTIPLIER"],
                "EXTERNAL_API_WINDOW_SECONDS": val("EXTERNAL_API_WINDOW_SECONDS") or _DEFAULTS["EXTERNAL_API_WINDOW_SECONDS"],
                "EXTERNAL_API_COOLDOWN_SECONDS": val("EXTERNAL_API_COOLDOWN_SECONDS") or _DEFAULTS["EXTERNAL_API_COOLDOWN_SECONDS"],
                "EXTERNAL_API_MIN_CACHE_SECONDS": val("EXTERNAL_API_MIN_CACHE_SECONDS") or _DEFAULTS["EXTERNAL_API_MIN_CACHE_SECONDS"],
            },
            "catalysts": {
                "CATALYST_PROVIDER": val("CATALYST_PROVIDER") or _DEFAULTS["CATALYST_PROVIDER"],
                "FINNHUB_API_KEY": {"masked": masked("FINNHUB_API_KEY"), "set": bool(raw.get("FINNHUB_API_KEY"))},
                "CATALYST_LOOKAHEAD_DAYS": val("CATALYST_LOOKAHEAD_DAYS") or _DEFAULTS["CATALYST_LOOKAHEAD_DAYS"],
            },
            "llm": {
                "ACTIVE_LLM_PROVIDER": val("ACTIVE_LLM_PROVIDER") or "openai",
                "OPENAI_API_KEY":    {"masked": masked("OPENAI_API_KEY"),    "set": bool(raw.get("OPENAI_API_KEY"))},
                "OPENAI_MODEL":      val("OPENAI_MODEL")      or _DEFAULTS["OPENAI_MODEL"],
                "DEEPSEEK_API_KEY":  {"masked": masked("DEEPSEEK_API_KEY"),  "set": bool(raw.get("DEEPSEEK_API_KEY"))},
                "DEEPSEEK_MODEL":    val("DEEPSEEK_MODEL")    or _DEFAULTS["DEEPSEEK_MODEL"],
                "KIMI_API_KEY":      {"masked": masked("KIMI_API_KEY"),      "set": bool(raw.get("KIMI_API_KEY"))},
                "KIMI_MODEL":        val("KIMI_MODEL")        or _DEFAULTS["KIMI_MODEL"],
                "ZHIPU_API_KEY":     {"masked": masked("ZHIPU_API_KEY"),     "set": bool(raw.get("ZHIPU_API_KEY"))},
                "ZHIPU_MODEL":       val("ZHIPU_MODEL")       or _DEFAULTS["ZHIPU_MODEL"],
                "GEMINI_API_KEY":    {"masked": masked("GEMINI_API_KEY"),    "set": bool(raw.get("GEMINI_API_KEY"))},
                "GEMINI_MODEL":      val("GEMINI_MODEL")      or _DEFAULTS["GEMINI_MODEL"],
                "CLAUDE_API_KEY":    {"masked": masked("CLAUDE_API_KEY"),    "set": bool(raw.get("CLAUDE_API_KEY"))},
                "CLAUDE_MODEL":      val("CLAUDE_MODEL")      or _DEFAULTS["CLAUDE_MODEL"],
            },
            "notifications": {
                "TELEGRAM_BOT_TOKEN": {"masked": masked("TELEGRAM_BOT_TOKEN"), "set": bool(raw.get("TELEGRAM_BOT_TOKEN"))},
                "TELEGRAM_CHAT_ID":   val("TELEGRAM_CHAT_ID"),
            },
            "alerts": {
                "PRICE_ALERT_DEFAULT_THRESHOLD": val("PRICE_ALERT_DEFAULT_THRESHOLD") or "5.0",
                "MONITOR_INTERVAL_MINUTES": val("MONITOR_INTERVAL_MINUTES") or "30",
            },
        }

    def update_env(self, updates: dict) -> list:
        """Write key=value pairs to .env and reload. Returns list of updated keys."""
        ENV_FILE.touch(exist_ok=True)
        updated = []
        for key, value in updates.items():
            key = key.upper()
            if key not in _DEFAULTS:
                continue
            set_key(str(ENV_FILE), key, str(value))
            updated.append(key)
        self._reload()
        return updated


settings = Settings()
