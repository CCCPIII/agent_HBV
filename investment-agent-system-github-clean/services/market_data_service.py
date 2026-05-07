import time
from datetime import datetime
from typing import Any, Dict, Optional

import yfinance as yf
from services.external_api_guard import external_api_guard
from services.yfinance_env import yfinance_network_env


class MarketDataError(Exception):
    pass


class MarketDataService:
    """Fetch quote data for a ticker using a free data source with retry logic."""

    def __init__(self, max_retries: int = 3, retry_delay: float = 2.0):
        """
        Initialize MarketDataService.
        
        Args:
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def get_quote(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch quote with retry logic for rate limiting.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dictionary with quote data
            
        Raises:
            MarketDataError: If unable to fetch quote after retries
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Add delay before each attempt (except the first one)
                if attempt > 0:
                    time.sleep(self.retry_delay)
                
                with yfinance_network_env():
                    ticker_object = yf.Ticker(ticker)
                    history = external_api_guard.call(
                        "yfinance_quote",
                        lambda: ticker_object.history(period="5d", interval="1d"),
                        cache_key=f"yfinance_quote:{ticker.upper()}:5d",
                    )
                
                # Filter out empty rows
                if history is not None and not history.empty:
                    history = history[history['Close'] > 0]
                
                if history is None or history.empty or len(history) < 1:
                    last_error = f"No price data for {ticker}"
                    continue

                latest = history.iloc[-1]
                previous_close = float(latest["Close"])
                
                if len(history) > 1:
                    prev = history.iloc[-2]
                    previous_close = float(prev["Close"])
                
                current_price = float(latest["Close"])
                percent_change = 0.0
                
                if previous_close > 0:
                    percent_change = ((current_price - previous_close) / previous_close) * 100.0
                
                # Try to get currency
                try:
                    with yfinance_network_env():
                        currency = external_api_guard.call(
                            "yfinance_quote",
                            lambda: getattr(ticker_object.fast_info, "currency", None) or "USD",
                            cache_key=f"yfinance_currency:{ticker.upper()}",
                            cache_ttl_seconds=3600,
                        )
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
                last_error = str(exc)
                # If it's a rate limit error and we have retries left, continue
                if "429" in str(exc) or "Too Many Requests" in str(exc) or "rate" in str(exc).lower():
                    if attempt < self.max_retries - 1:
                        continue
                # For other errors, raise immediately
                elif attempt == 0:
                    raise MarketDataError(f"Failed to fetch quote for {ticker}: {exc}") from exc
        
        # All retries exhausted
        raise MarketDataError(f"Failed to fetch quote for {ticker}: {last_error}") from None

    def set_quote_provider(self, provider: Any) -> None:
        self.provider = provider
