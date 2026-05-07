from typing import Dict, List

from app.models import PortfolioPosition
from services.market_data_service import MarketDataService


class PortfolioService:
    """Calculate simple portfolio value and unrealized PnL."""

    def __init__(self, market_data_service: MarketDataService | None = None):
        self.market_data_service = market_data_service or MarketDataService()

    def summarize(self, positions: List[PortfolioPosition]) -> Dict[str, float]:
        total_value = 0.0
        total_cost = 0.0
        details = []
        for position in positions:
            quote = self.market_data_service.get_quote(position.ticker)
            current_value = quote["price"] * position.quantity
            cost_value = position.average_cost * position.quantity
            total_value += current_value
            total_cost += cost_value
            details.append(
                {
                    "ticker": position.ticker,
                    "quantity": position.quantity,
                    "current_price": quote["price"],
                    "market_value": current_value,
                    "cost_basis": cost_value,
                    "unrealized_pnl": current_value - cost_value,
                }
            )
        return {
            "total_market_value": total_value,
            "total_cost_basis": total_cost,
            "total_unrealized_pnl": total_value - total_cost,
            "positions": details,
        }
