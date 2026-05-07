from __future__ import annotations

from typing import Iterable, List, Optional


_TICKER_ALIASES = {
    "0700.HK": ["TCEHY", "700.HK"],
    "700.HK": ["TCEHY"],
}

_COMPANY_ALIASES = {
    "tencent holdings": ["TCEHY", "700.HK"],
    "tencent holdings ltd": ["TCEHY", "700.HK"],
    "tencent holdings limited": ["TCEHY", "700.HK"],
}


def build_finnhub_symbol_candidates(
    ticker: str,
    company_name: Optional[str] = None,
    discovered_symbols: Optional[Iterable[str]] = None,
) -> List[str]:
    ticker = (ticker or "").upper().strip()
    company_key = (company_name or "").strip().lower()

    candidates: List[str] = []
    _append_unique(candidates, ticker)

    if ticker.endswith(".HK"):
        numeric = ticker.split(".", 1)[0].lstrip("0")
        if numeric:
            _append_unique(candidates, f"{numeric}.HK")

    for alias in _TICKER_ALIASES.get(ticker, []):
        _append_unique(candidates, alias)

    for alias in _COMPANY_ALIASES.get(company_key, []):
        _append_unique(candidates, alias)

    for symbol in discovered_symbols or []:
        _append_unique(candidates, (symbol or "").upper())

    return [symbol for symbol in candidates if symbol]


def _append_unique(items: List[str], value: str) -> None:
    normalized = (value or "").strip().upper()
    if normalized and normalized not in items:
        items.append(normalized)
