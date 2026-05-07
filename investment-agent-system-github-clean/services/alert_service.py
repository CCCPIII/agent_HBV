from typing import Any, Dict, List, Optional

from app.models import Alert, AgentAnalysis, WatchlistItem
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
        allowed_fields = {
            "related_alert_id",
            "related_news_id",
            "ticker",
            "impact_direction",
            "impact_level",
            "summary",
            "reasoning",
            "confidence",
        }
        analysis_record = AgentAnalysis(**{
            key: value for key, value in analysis.items()
            if key in allowed_fields
        })
        session.add(analysis_record)
        session.commit()
        session.refresh(analysis_record)
        return analysis_record

    def create_analysis_alert(self, session: Session, analysis: Dict[str, Any]) -> Optional[Alert]:
        if analysis.get("related_alert_id"):
            return None

        confidence = float(analysis.get("confidence", 0.0) or 0.0)
        if confidence < 0.45:
            return None

        ticker = analysis.get("ticker")
        alert_type = str(analysis.get("_context_type") or analysis.get("alert_type") or "analysis")
        title = str(analysis.get("_context_title") or analysis.get("summary") or "AI analysis signal").strip()
        if not title:
            return None

        existing = (
            session.query(Alert)
            .filter(
                Alert.ticker == ticker,
                Alert.alert_type == alert_type,
                Alert.title == title,
            )
            .first()
        )
        if existing:
            return existing

        severity = str(analysis.get("impact_level") or "medium").lower()
        direction = str(analysis.get("impact_direction") or "unknown").lower()
        summary = str(analysis.get("summary") or "").strip()
        reasoning = str(analysis.get("reasoning") or "").strip()
        confidence_pct = round(confidence * 100)
        message = f"[{direction}] {summary or title} (confidence {confidence_pct}%). {reasoning}".strip()

        alert = Alert(
            ticker=ticker,
            alert_type=alert_type,
            severity=severity if severity in {"high", "medium", "low"} else "medium",
            title=title,
            message=message,
            source_url=analysis.get("_source_url"),
            sent=False,
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        return alert

    def list_alerts(self, session: Session) -> List[Alert]:
        return session.query(Alert).order_by(Alert.created_at.desc()).limit(100).all()
