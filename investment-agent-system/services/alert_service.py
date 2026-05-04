from typing import Any, Dict, List, Optional

from app.models import Alert, AgentAnalysis, PriceSnapshot, WatchlistItem
from sqlalchemy.orm import Session


class AlertService:
    """Handle alert creation and storage for price moves and analyses."""

    def __init__(self, default_threshold: float = 5.0):
        self.default_threshold = default_threshold

    def create_price_alert(self, session: Session, item: WatchlistItem, snapshot: Dict[str, Any]) -> Optional[Alert]:
        threshold = item.alert_threshold_percent or self.default_threshold
        pct = abs(snapshot["percent_change"])
        if pct >= threshold:
            title = f"{item.ticker} moved {snapshot['percent_change']:+.1f}%"
            message = f"{item.ticker} moved {snapshot['percent_change']:+.1f}% today, above your {threshold:.1f}% threshold."
            severity = "high" if pct >= threshold * 2 else "medium"
            alert = Alert(
                ticker=item.ticker,
                alert_type="price_move",
                severity=severity,
                title=title,
                message=message,
                source_url=None,
                sent=False,
            )
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return alert
        return None

    def save_analysis(self, session: Session, analysis: Dict[str, Any]) -> AgentAnalysis:
        analysis_record = AgentAnalysis(**analysis)
        session.add(analysis_record)
        session.commit()
        session.refresh(analysis_record)
        return analysis_record

    def list_alerts(self, session: Session) -> List[Alert]:
        return session.query(Alert).order_by(Alert.created_at.desc()).limit(100).all()
