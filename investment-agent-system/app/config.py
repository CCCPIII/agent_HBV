import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.getenv("ENV_FILE", ".env"))


class Settings:
    database_url: str
    openai_api_key: Optional[str]
    telegram_bot_token: Optional[str]
    telegram_chat_id: Optional[str]
    price_alert_default_threshold: float

    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./investment_agent.db")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.price_alert_default_threshold = float(os.getenv("PRICE_ALERT_DEFAULT_THRESHOLD", "5.0"))


settings = Settings()
