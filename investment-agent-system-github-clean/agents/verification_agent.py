from typing import Dict


class VerificationAgent:
    """Verify analysis by checking for source and event freshness."""

    def verify(self, analysis: Dict[str, object], item: Dict[str, object]) -> Dict[str, object]:
        confidence = float(analysis.get("confidence", 0.5))
        reasoning = str(analysis.get("reasoning", ""))

        if not item.get("source_url"):
            confidence -= 0.15
            reasoning += " Source is missing; confidence is reduced."

        if item.get("event_date"):
            from datetime import date

            if item.get("event_date") < date.today():
                confidence -= 0.2
                reasoning += " Event appears stale."

        confidence = max(0.0, min(1.0, confidence))
        analysis["confidence"] = confidence
        analysis["reasoning"] = reasoning.strip() or analysis.get("reasoning")
        return analysis
