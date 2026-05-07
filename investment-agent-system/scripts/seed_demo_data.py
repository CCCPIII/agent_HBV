from datetime import date, datetime

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import (
    CatalystEvent, NewsItem, PortfolioPosition,
    PriceSnapshot, WatchlistItem,
)
from services.catalyst_service import CatalystService
from services.ipo_service import IPOService
from services.news_service import NewsService


def seed_data() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        # ── Watchlist ────────────────────────────────────────────────────────
        if session.query(WatchlistItem).count() == 0:
            session.add_all([
                WatchlistItem(
                    ticker="AAPL",
                    company_name="Apple Inc.",
                    exchange="NASDAQ",
                    sector="Technology",
                    alert_threshold_percent=settings.price_alert_default_threshold,
                ),
                WatchlistItem(
                    ticker="0700.HK",
                    company_name="Tencent Holdings",
                    exchange="HKEX",
                    sector="Technology",
                    alert_threshold_percent=settings.price_alert_default_threshold,
                ),
            ])
            session.commit()
            print("  ✓ Watchlist seeded")

        # ── Portfolio ────────────────────────────────────────────────────────
        if session.query(PortfolioPosition).count() == 0:
            session.add_all([
                PortfolioPosition(
                    ticker="AAPL",
                    company_name="Apple Inc.",
                    quantity=10,
                    average_cost=150.0,
                    currency="USD",
                    purchase_date=date(2024, 1, 10),
                ),
                PortfolioPosition(
                    ticker="0700.HK",
                    company_name="Tencent Holdings",
                    quantity=5,
                    average_cost=300.0,
                    currency="HKD",
                    purchase_date=date(2024, 3, 20),
                ),
            ])
            session.commit()
            print("  ✓ Portfolio seeded")

        # ── Catalysts / demo news / IPO ──────────────────────────────────────
        CatalystService().seed_demo_catalysts(session)
        NewsService().seed_demo_news(session)
        IPOService().seed_demo_ipo(session)

        # ── Historical price snapshots & live news (last 1 month) ─────────
        _backfill_history(session, period="1mo")

    print("Demo data seeded.")


def _backfill_history(session, period: str = "1mo") -> None:
    """Pull 1 month of price history + latest news from yfinance for all watchlist tickers."""
    try:
        import yfinance as yf
    except ImportError:
        print("  ! yfinance not installed, skipping historical backfill")
        return

    tickers = [w.ticker for w in session.query(WatchlistItem).filter(WatchlistItem.active == True).all()]
    seen_titles = {r[0] for r in session.query(NewsItem.title).all()}
    saved_news = 0
    saved_snaps = 0

    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)

            # ── News ─────────────────────────────────────────────────────────
            for item in (t.news or [])[:10]:
                content = item.get("content", {})
                title = content.get("title") or item.get("title", "")
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                summary = (content.get("summary") or content.get("description") or "")[:500]
                pub_raw = content.get("pubDate") or item.get("providerPublishTime")
                try:
                    pub_dt = (
                        datetime.fromisoformat(str(pub_raw)) if isinstance(pub_raw, str)
                        else datetime.utcfromtimestamp(int(pub_raw)) if pub_raw
                        else datetime.utcnow()
                    )
                except Exception:
                    pub_dt = datetime.utcnow()
                session.add(NewsItem(
                    ticker=ticker,
                    sector=None,
                    title=title,
                    summary=summary,
                    source=(content.get("provider") or {}).get("displayName", "") or item.get("publisher", "Yahoo Finance"),
                    source_url=(content.get("canonicalUrl") or {}).get("url", "") or item.get("link", ""),
                    published_at=pub_dt,
                ))
                saved_news += 1

            # ── Price snapshots ───────────────────────────────────────────────
            hist = t.history(period=period, interval="1d")
            for ts, row in hist.iterrows():
                close = float(row["Close"])
                idx = hist.index.get_loc(ts)
                prev_close = float(hist.iloc[idx - 1]["Close"]) if idx > 0 else close
                pct = ((close - prev_close) / prev_close * 100) if prev_close else 0.0
                captured = ts.to_pydatetime().replace(tzinfo=None)
                day_start = captured.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = captured.replace(hour=23, minute=59, second=59, microsecond=0)
                exists = session.query(PriceSnapshot).filter(
                    PriceSnapshot.ticker == ticker.upper(),
                    PriceSnapshot.captured_at >= day_start,
                    PriceSnapshot.captured_at <= day_end,
                ).first()
                if not exists:
                    session.add(PriceSnapshot(
                        ticker=ticker.upper(),
                        price=close,
                        previous_close=prev_close,
                        percent_change=round(pct, 4),
                        currency="USD",
                        captured_at=captured,
                    ))
                    saved_snaps += 1

            session.commit()
        except Exception as exc:
            print(f"  ! backfill error for {ticker}: {exc}")

    print(f"  ✓ Historical backfill: {saved_snaps} price snapshots, {saved_news} news items")


if __name__ == "__main__":
    seed_data()
