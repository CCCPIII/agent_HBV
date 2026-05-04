from datetime import datetime
from typing import Any, Dict, Optional

import yfinance as yf


class MarketDataError(Exception):
    pass


class MarketDataService:
    """Fetch quote data for a ticker using a free data source."""

    def get_quote(self, ticker: str) -> Dict[str, Any]:
        try:
            ticker_object = yf.Ticker(ticker)
            history = ticker_object.history(period="2d", interval="1d")
            if history.empty or len(history) < 1:
                raise MarketDataError(f"No price data for {ticker}")

            latest = history.iloc[-1]
            previous_close = float(latest["Close"])
            if len(history) > 1:
                previous_close = float(history.iloc[-2]["Close"])
            current_price = float(latest["Close"])
            percent_change = 0.0
            if previous_close:
                percent_change = ((current_price - previous_close) / previous_close) * 100.0
            # fast_info is much faster than .info (no extra HTTP call)
            try:
                currency = getattr(ticker_object.fast_info, "currency", None) or "USD"
            except Exception:
                currency = "USD"
            return {
                "ticker": ticker.upper(),
                "price": current_price,
                "previous_close": previous_close,
                "percent_change": percent_change,
                "currency": currency or "USD",
                "captured_at": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            raise MarketDataError(f"Failed to fetch quote for {ticker}: {exc}") from exc

    def set_quote_provider(self, provider: Any) -> None:
        self.provider = provider
