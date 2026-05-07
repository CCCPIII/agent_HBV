import logging
import os
from typing import Dict, Optional

import requests

from app.config import settings
from services.external_api_guard import external_api_guard
from services.network_env import external_network_env


class NotificationService:
    """Send alerts to console and optionally to Telegram."""

    def send_console(self, alert: Dict[str, object]) -> None:
        logging.info("[ALERT] %s: %s", alert.get("title"), alert.get("message"))
        print(f"[ALERT] {alert.get('title')} - {alert.get('message')}")

    def send_telegram(self, alert: Dict[str, object]) -> None:
        token = settings.telegram_bot_token
        chat_id = settings.telegram_chat_id
        if not token or not chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            text = f"{alert.get('title')}\n{alert.get('message')}"
            with external_network_env():
                response = external_api_guard.call(
                    "telegram",
                    lambda: requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15),
                    cache_key=None,
                    cache_ttl_seconds=0,
                )
            response.raise_for_status()
        except Exception as exc:
            logging.warning("Telegram notification failed: %s", exc)

    def notify(self, alert: Dict[str, object]) -> None:
        self.send_console(alert)
        try:
            self.send_telegram(alert)
        except Exception:
            pass
