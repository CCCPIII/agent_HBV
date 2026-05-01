import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.getenv("ENV_FILE", ".env"))

# Supported provider identifiers
SUPPORTED_PROVIDERS = ("openai", "deepseek", "kimi", "zhipu", "gemini", "claude")


class Settings:
    # Database
    database_url: str

    # Active LLM provider (openai | deepseek | kimi | zhipu | gemini | claude)
    active_llm_provider: str

    # API keys
    openai_api_key: Optional[str]
    deepseek_api_key: Optional[str]
    kimi_api_key: Optional[str]
    zhipu_api_key: Optional[str]
    gemini_api_key: Optional[str]
    claude_api_key: Optional[str]

    # Model names (override via env if desired)
    openai_model: str
    deepseek_model: str
    kimi_model: str
    zhipu_model: str
    gemini_model: str
    claude_model: str

    # Notifications
    telegram_bot_token: Optional[str]
    telegram_chat_id: Optional[str]

    # Alerts
    price_alert_default_threshold: float

    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./investment_agent.db")

        self.active_llm_provider = os.getenv("ACTIVE_LLM_PROVIDER", "openai").lower()

        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        self.kimi_api_key = os.getenv("KIMI_API_KEY")
        self.zhipu_api_key = os.getenv("ZHIPU_API_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.claude_api_key = os.getenv("CLAUDE_API_KEY")

        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.kimi_model = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
        self.zhipu_model = os.getenv("ZHIPU_MODEL", "glm-4-flash")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.price_alert_default_threshold = float(os.getenv("PRICE_ALERT_DEFAULT_THRESHOLD", "5.0"))

    def active_api_key(self) -> Optional[str]:
        """Return the API key for the currently active provider."""
        return {
            "openai": self.openai_api_key,
            "deepseek": self.deepseek_api_key,
            "kimi": self.kimi_api_key,
            "zhipu": self.zhipu_api_key,
            "gemini": self.gemini_api_key,
            "claude": self.claude_api_key,
        }.get(self.active_llm_provider)

    def providers_status(self) -> dict:
        """Return configured/unconfigured status for all providers."""
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
            provider: {
                "configured": bool(key),
                "model": models[provider],
                "active": provider == self.active_llm_provider,
            }
            for provider, key in keys.items()
        }


settings = Settings()
