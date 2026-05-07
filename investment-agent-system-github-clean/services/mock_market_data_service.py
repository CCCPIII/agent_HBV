"""
Mock data service for testing and fallback when real APIs are unavailable.
Provides realistic but simulated market data.
"""

import random
from datetime import datetime, timedelta
from typing import Any, Dict, List

class MockMarketDataService:
    """Provides simulated market data for testing and development."""
    
    # Simulated baseline prices for common tickers
    BASELINE_PRICES = {
        "AAPL": 150.00,
        "MSFT": 380.00,
        "GOOGL": 140.00,
        "AMZN": 170.00,
        "TSLA": 240.00,
        "NVDA": 880.00,
        "META": 480.00,
        "0700.HK": 140.00,  # Tencent
        "9988.HK": 90.00,   # Alibaba
        "BRK.A": 620000.00, # Berkshire Hathaway
    }
    
    def __init__(self, seed: int = None):
        """Initialize with optional random seed for reproducibility."""
        if seed is not None:
            random.seed(seed)
    
    def get_quote(self, ticker: str) -> Dict[str, Any]:
        """
        Get simulated quote data for a ticker.
        
        Returns realistic random price movements around baseline prices.
        """
        ticker = ticker.upper()
        
        # Get baseline price, or generate a random one
        baseline = self.BASELINE_PRICES.get(ticker, random.uniform(50, 500))
        
        # Simulate daily change (-5% to +5%)
        change_percent = random.uniform(-5, 5)
        current_price = baseline * (1 + change_percent / 100)
        previous_close = baseline
        
        # Determine currency based on ticker
        if ".HK" in ticker:
            currency = "HKD"
        else:
            currency = "USD"
        
        return {
            "ticker": ticker,
            "price": round(current_price, 2),
            "previous_close": round(previous_close, 2),
            "percent_change": round(change_percent, 2),
            "currency": currency,
            "captured_at": datetime.utcnow().isoformat(),
            "source": "MOCK",  # Mark as mock data
        }
    
    def get_history(self, ticker: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get simulated historical data for a ticker.
        
        Generates a realistic price path using random walk.
        """
        ticker = ticker.upper()
        baseline = self.BASELINE_PRICES.get(ticker, random.uniform(50, 500))
        
        history = []
        current_price = baseline
        
        for i in range(days, 0, -1):
            # Random walk: -2% to +2% daily movement
            daily_change = random.uniform(-2, 2)
            current_price = current_price * (1 + daily_change / 100)
            
            date = datetime.utcnow() - timedelta(days=i)
            history.append({
                "date": date.isoformat(),
                "ticker": ticker,
                "close": round(current_price, 2),
                "volume": random.randint(1000000, 100000000),
            })
        
        return history
    
    @staticmethod
    def get_supported_tickers() -> List[str]:
        """Get list of tickers with predefined prices."""
        return list(MockMarketDataService.BASELINE_PRICES.keys())


# Monkey-patch helper to use mock data in place of real service
def enable_mock_data_mode():
    """Replace real MarketDataService with mock version globally."""
    from services.market_data_service import MarketDataService
    
    # Store original get_quote method
    original_get_quote = MarketDataService.get_quote
    
    # Create a wrapper that falls back to mock on error
    def fallback_get_quote(self, ticker: str) -> Dict[str, Any]:
        try:
            return original_get_quote(self, ticker)
        except Exception as e:
            print(f"[FALLBACK] Real API failed, using mock data: {e}")
            mock_service = MockMarketDataService()
            return mock_service.get_quote(ticker)
    
    # Replace the method
    MarketDataService.get_quote = fallback_get_quote
    print("[INFO] Mock data fallback enabled for MarketDataService")


if __name__ == "__main__":
    # Test the mock service
    mock = MockMarketDataService(seed=42)
    
    print("Mock Market Data Service - Test")
    print("=" * 50)
    
    for ticker in ["AAPL", "MSFT", "0700.HK"]:
        quote = mock.get_quote(ticker)
        print(f"\n{ticker}:")
        print(f"  Price: {quote['currency']} {quote['price']}")
        print(f"  Change: {quote['percent_change']:+.2f}%")
        print(f"  Source: {quote.get('source', 'REAL')}")
    
    print("\n" + "=" * 50)
    print("✓ Mock service working correctly")
