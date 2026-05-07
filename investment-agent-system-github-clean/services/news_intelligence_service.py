import re
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional


class NewsIntelligenceService:
    """Cluster raw news into higher-level investment events."""

    _STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
        "into", "is", "it", "of", "on", "or", "that", "the", "to", "with",
        "after", "before", "about", "over", "under", "amid", "says", "say",
        "may", "could", "would", "will", "new", "stock", "shares", "company",
        "corp", "inc", "ltd", "group", "market", "markets", "news", "report",
    }

    _EVENT_KEYWORDS = {
        "product": ("launch", "unveil", "event", "device", "product", "hardware", "software"),
        "earnings": ("earnings", "results", "revenue", "guidance", "profit", "quarter"),
        "demand": ("demand", "orders", "backlog", "shipments", "sales", "growth"),
        "regulatory": ("regulator", "regulatory", "antitrust", "probe", "fine", "ban", "lawsuit", "approval"),
        "partnership": ("partnership", "partner", "deal", "collaboration", "agreement"),
        "ma": ("acquisition", "acquire", "merger", "buyout", "stake", "takeover"),
        "leadership": ("ceo", "cfo", "executive", "board", "chairman", "resign", "appoint"),
        "ipo": ("ipo", "listing", "offering", "debut"),
        "macro": ("inflation", "rates", "fed", "economy", "tariff", "currency"),
    }

    _POSITIVE_KEYWORDS = {
        "beat", "strong", "surge", "grow", "growth", "expand", "launch", "approval",
        "partnership", "wins", "record", "bullish", "upgrade", "accelerate",
    }
    _NEGATIVE_KEYWORDS = {
        "miss", "weak", "drop", "fall", "cuts", "cut", "downgrade", "probe",
        "fine", "ban", "lawsuit", "delay", "slump", "recall", "risk",
    }

    def build_events(self, news_items: List[Dict[str, object]], limit: int = 20) -> List[Dict[str, object]]:
        clusters: List[Dict[str, object]] = []
        sorted_items = sorted(
            news_items,
            key=lambda item: self._published_at(item) or datetime.min,
            reverse=True,
        )

        for item in sorted_items:
            event_type = self._classify_event_type(item)
            tokens = self._keywords(item)
            cluster = self._find_cluster(clusters, item, event_type, tokens)
            if cluster is None:
                cluster = {
                    "event_type": event_type,
                    "ticker": item.get("ticker"),
                    "sector": item.get("sector"),
                    "scope": item.get("scope"),
                    "tokens": tokens,
                    "items": [],
                }
                clusters.append(cluster)
            else:
                cluster["tokens"] = sorted(set(cluster["tokens"]) | set(tokens))
            cluster["items"].append(item)

        events = [self._finalize_cluster(cluster) for cluster in clusters]
        events.sort(
            key=lambda item: (
                item.get("published_at") or "",
                item.get("article_count") or 0,
                item.get("source_count") or 0,
            ),
            reverse=True,
        )
        return events[:limit]

    def _find_cluster(
        self,
        clusters: List[Dict[str, object]],
        item: Dict[str, object],
        event_type: str,
        tokens: List[str],
    ) -> Optional[Dict[str, object]]:
        ticker = item.get("ticker")
        sector = item.get("sector")

        for cluster in clusters:
            if cluster["event_type"] != event_type:
                continue
            if cluster.get("ticker") and ticker and cluster["ticker"] != ticker:
                continue
            if not cluster.get("ticker") and ticker and cluster.get("sector") and sector and cluster["sector"] != sector:
                continue
            similarity = self._token_similarity(tokens, cluster["tokens"])
            shared_tokens = len(set(tokens) & set(cluster["tokens"]))
            if similarity >= 0.45 or (ticker and cluster.get("ticker") == ticker and shared_tokens >= 2):
                return cluster
        return None

    def _finalize_cluster(self, cluster: Dict[str, object]) -> Dict[str, object]:
        items = cluster["items"]
        primary = max(items, key=lambda item: self._published_at(item) or datetime.min)
        source_urls = [item.get("source_url") for item in items if item.get("source_url")]
        sources = [item.get("source") for item in items if item.get("source")]
        article_ids = [item.get("id") for item in items if item.get("id") is not None]
        titles = [str(item.get("title") or "").strip() for item in items if item.get("title")]
        unique_sources = list(dict.fromkeys(sources))
        unique_urls = list(dict.fromkeys(source_urls))
        article_count = len(items)
        source_count = len(unique_sources)
        confidence = 0.55
        if source_count >= 2:
            confidence += 0.1
        if article_count >= 2:
            confidence += 0.1
        if primary.get("ticker"):
            confidence += 0.05
        if unique_urls:
            confidence += 0.05

        topic = self._topic_phrase(cluster["tokens"])
        summary = str(primary.get("summary") or "").strip()
        if article_count > 1:
            summary = (
                f"{primary.get('title', '')}. "
                f"{article_count} related articles from {source_count} sources point to {topic}."
            ).strip()
        elif not summary:
            summary = str(primary.get("title") or "News event detected.").strip()

        impact_direction = self._infer_direction(" ".join(titles + [summary]))
        impact_level = "high" if source_count >= 3 else "medium" if article_count >= 2 else "low"

        return {
            "dedupe_key": self._build_dedupe_key(primary, cluster["event_type"], cluster["tokens"]),
            "ticker": primary.get("ticker"),
            "sector": primary.get("sector"),
            "scope": primary.get("scope"),
            "event_type": cluster["event_type"],
            "title": primary.get("title"),
            "summary": summary,
            "impact_direction": impact_direction,
            "impact_level": impact_level,
            "confidence": min(confidence, 0.9),
            "published_at": self._published_at(primary).isoformat() if self._published_at(primary) else None,
            "source_url": unique_urls[0] if unique_urls else None,
            "sources": unique_sources,
            "source_count": source_count,
            "article_count": article_count,
            "article_ids": article_ids,
            "titles": titles,
        }

    def _classify_event_type(self, item: Dict[str, object]) -> str:
        text = self._combined_text(item)
        for event_type, keywords in self._EVENT_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return event_type
        return "news"

    def _topic_phrase(self, tokens: List[str]) -> str:
        if not tokens:
            return "the same investment theme"
        return " / ".join(tokens[:3])

    def _keywords(self, item: Dict[str, object]) -> List[str]:
        words = re.findall(r"[a-z0-9]{3,}", self._combined_text(item))
        counts = Counter(word for word in words if word not in self._STOPWORDS)
        return [word for word, _ in counts.most_common(8)]

    def _combined_text(self, item: Dict[str, object]) -> str:
        title = str(item.get("title") or "")
        summary = str(item.get("summary") or "")
        return f"{title} {summary}".lower()

    def _token_similarity(self, left: List[str], right: List[str]) -> float:
        left_set = set(left)
        right_set = set(right)
        if not left_set or not right_set:
            return 0.0
        return len(left_set & right_set) / len(left_set | right_set)

    def _infer_direction(self, text: str) -> str:
        normalized = text.lower()
        positive = sum(1 for keyword in self._POSITIVE_KEYWORDS if keyword in normalized)
        negative = sum(1 for keyword in self._NEGATIVE_KEYWORDS if keyword in normalized)
        if positive > negative:
            return "positive"
        if negative > positive:
            return "negative"
        return "neutral"

    def _build_dedupe_key(self, primary: Dict[str, object], event_type: str, tokens: List[str]) -> str:
        return "|".join([
            str(primary.get("ticker") or primary.get("sector") or "market").lower(),
            event_type,
            ",".join(tokens[:5]),
        ])

    @staticmethod
    def _published_at(item: Dict[str, object]) -> Optional[datetime]:
        value = item.get("published_at")
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                return None
        return None
