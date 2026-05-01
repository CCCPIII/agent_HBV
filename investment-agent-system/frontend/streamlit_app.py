import requests
import streamlit as st
import pandas as pd

API_URL = st.secrets.get("api_url", "http://localhost:8000")

SEVERITY_COLOR = {"high": "🔴", "medium": "🟡", "low": "🟢"}
DIRECTION_COLOR = {"positive": "🟢", "negative": "🔴", "neutral": "⚪", "unknown": "❓"}


def get_json(path: str, default=None):
    if default is None:
        default = []
    try:
        r = requests.get(f"{API_URL}{path}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        st.error(f"API error [{path}]: {exc}")
        return default


def post_json(path: str, payload: dict):
    try:
        r = requests.post(f"{API_URL}{path}", json=payload, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        st.error(f"API error [{path}]: {exc}")
        return None


def delete_json(path: str):
    try:
        r = requests.delete(f"{API_URL}{path}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        st.error(f"API error [{path}]: {exc}")
        return None


def fmt_pct(val):
    if val is None:
        return "—"
    color = "green" if val >= 0 else "red"
    sign = "+" if val >= 0 else ""
    return f":{color}[{sign}{val:.2f}%]"


def fmt_pnl(val, currency="USD"):
    if val is None:
        return "—"
    color = "green" if val >= 0 else "red"
    sign = "+" if val >= 0 else ""
    return f":{color}[{sign}{val:,.2f} {currency}]"


# ─── Sidebar ────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.title("Investment Agent")
        st.caption(f"Backend: `{API_URL}`")

        health = get_json("/health", default={})
        if health.get("status") == "ok":
            st.success("Backend online")
        else:
            st.error("Backend offline")

        summary = get_json("/dashboard/summary", default={})
        if summary:
            st.divider()
            st.subheader("System Overview")
            col1, col2 = st.columns(2)
            col1.metric("Watchlist", summary.get("watchlist_count", 0))
            col2.metric("Portfolio", summary.get("portfolio_count", 0))
            col1.metric("Alerts", summary.get("alerts_count", 0))
            col2.metric("Unread", summary.get("unread_alerts", 0))
            col1.metric("Analyses", summary.get("analyses_count", 0))
            col2.metric("News", summary.get("news_count", 0))

        st.divider()
        if st.button("Run Monitor Now", use_container_width=True):
            with st.spinner("Running monitoring cycle..."):
                result = post_json("/monitor/run-once", {})
            if result:
                st.success("Cycle complete")
                st.json(result.get("summary", result))


# ─── Dashboard tab ───────────────────────────────────────────────────────────
def tab_dashboard():
    st.header("Dashboard")
    summary = get_json("/dashboard/summary", default={})
    if not summary:
        st.info("Could not load summary. Is the backend running?")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Watchlist Items", summary.get("watchlist_count", 0))
    c2.metric("Portfolio Positions", summary.get("portfolio_count", 0))
    c3.metric("Total Alerts", summary.get("alerts_count", 0), delta=f"{summary.get('unread_alerts', 0)} unread")
    c4.metric("AI Analyses", summary.get("analyses_count", 0))

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Recent Alerts")
        alerts = get_json("/alerts")
        if alerts:
            for a in alerts[:5]:
                sev = a.get("severity", "low")
                icon = SEVERITY_COLOR.get(sev, "⚪")
                with st.expander(f"{icon} [{a.get('ticker', '—')}] {a['title']}"):
                    st.write(a["message"])
                    st.caption(f"Type: `{a['alert_type']}` | {a['created_at'][:16]}")
        else:
            st.info("No alerts yet.")

    with col_b:
        st.subheader("Recent Analyses")
        analyses = get_json("/analyses")
        if analyses:
            for an in analyses[:5]:
                direction = an.get("impact_direction", "unknown")
                icon = DIRECTION_COLOR.get(direction, "❓")
                with st.expander(f"{icon} [{an.get('ticker', '—')}] {an['summary'][:80]}"):
                    st.write(f"**Direction:** {direction} | **Level:** {an.get('impact_level')}")
                    st.write(f"**Reasoning:** {an.get('reasoning')}")
                    st.caption(f"Confidence: {an.get('confidence', 0):.0%} | {an['created_at'][:16]}")
        else:
            st.info("No analyses yet.")


# ─── Watchlist tab ───────────────────────────────────────────────────────────
def tab_watchlist():
    st.header("Watchlist")

    with st.expander("Add new watchlist item", expanded=False):
        with st.form("add_watchlist"):
            c1, c2 = st.columns(2)
            ticker = c1.text_input("Ticker").upper()
            company_name = c2.text_input("Company Name")
            c3, c4 = st.columns(2)
            exchange = c3.text_input("Exchange")
            sector = c4.text_input("Sector")
            threshold = st.number_input("Alert Threshold %", value=5.0, min_value=0.1, step=0.5)
            active = st.checkbox("Active", value=True)
            if st.form_submit_button("Add to Watchlist", use_container_width=True):
                if ticker and company_name:
                    post_json("/watchlist", {
                        "ticker": ticker,
                        "company_name": company_name,
                        "exchange": exchange,
                        "sector": sector,
                        "alert_threshold_percent": threshold,
                        "active": active,
                    })
                    st.rerun()
                else:
                    st.warning("Ticker and Company Name are required.")

    items = get_json("/watchlist")
    if not items:
        st.info("No watchlist items. Add one above.")
        return

    df = pd.DataFrame(items)
    df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d")
    df["threshold"] = df["alert_threshold_percent"].apply(lambda x: f"{x:.1f}%")

    display_cols = ["ticker", "company_name", "exchange", "sector", "threshold", "created_at"]
    display_cols = [c for c in display_cols if c in df.columns]

    col_header = st.columns([3, 2, 2, 2, 2, 2, 1])
    for h, label in zip(col_header[:-1], ["Ticker", "Company", "Exchange", "Sector", "Threshold", "Added"]):
        h.markdown(f"**{label}**")
    col_header[-1].markdown("**Del**")

    for _, row in df.iterrows():
        cols = st.columns([3, 2, 2, 2, 2, 2, 1])
        cols[0].write(f"**{row['ticker']}**")
        cols[1].write(row.get("company_name", ""))
        cols[2].write(row.get("exchange") or "—")
        cols[3].write(row.get("sector") or "—")
        cols[4].write(row.get("threshold", ""))
        cols[5].write(row.get("created_at", ""))
        if cols[6].button("✕", key=f"del_wl_{row['id']}"):
            delete_json(f"/watchlist/{row['id']}")
            st.rerun()


# ─── Portfolio tab ───────────────────────────────────────────────────────────
def tab_portfolio():
    st.header("Portfolio")

    with st.expander("Add new position", expanded=False):
        with st.form("add_position"):
            c1, c2 = st.columns(2)
            ticker = c1.text_input("Ticker").upper()
            company_name = c2.text_input("Company Name")
            c3, c4 = st.columns(2)
            quantity = c3.number_input("Quantity", value=0.0, min_value=0.0)
            average_cost = c4.number_input("Average Cost", value=0.0, min_value=0.0)
            c5, c6 = st.columns(2)
            currency = c5.text_input("Currency", value="USD")
            purchase_date = c6.date_input("Purchase Date")
            if st.form_submit_button("Add Position", use_container_width=True):
                if ticker and company_name:
                    post_json("/portfolio", {
                        "ticker": ticker,
                        "company_name": company_name,
                        "quantity": quantity,
                        "average_cost": average_cost,
                        "currency": currency,
                        "purchase_date": purchase_date.isoformat(),
                        "active": True,
                    })
                    st.rerun()
                else:
                    st.warning("Ticker and Company Name are required.")

    with st.spinner("Fetching live prices..."):
        positions = get_json("/portfolio/summary")

    if not positions:
        st.info("No portfolio positions. Add one above.")
        return

    total_cost = sum(p.get("cost_basis") or 0 for p in positions)
    total_value = sum(p.get("current_value") or 0 for p in positions)
    total_pnl = total_value - total_cost if total_value else None

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total Cost Basis", f"{total_cost:,.2f}")
    if total_value:
        pnl_pct_total = (total_pnl / total_cost * 100) if total_cost else 0
        mc2.metric("Current Value", f"{total_value:,.2f}", delta=f"{total_pnl:+,.2f}")
        mc3.metric("Total P&L", f"{total_pnl:+,.2f}", delta=f"{pnl_pct_total:+.2f}%")

    st.divider()

    # Portfolio allocation pie chart
    if len(positions) > 1:
        alloc_df = pd.DataFrame([
            {"Ticker": p["ticker"], "Value": p.get("current_value") or p.get("cost_basis") or 0}
            for p in positions
        ])
        if alloc_df["Value"].sum() > 0:
            st.subheader("Allocation")
            st.bar_chart(alloc_df.set_index("Ticker"))

    st.subheader("Positions")
    headers = st.columns([2, 3, 2, 2, 2, 2, 2, 2, 1])
    for h, label in zip(headers[:-1], ["Ticker", "Company", "Qty", "Avg Cost", "Current", "Cost Basis", "P&L", "Day %"]):
        h.markdown(f"**{label}**")
    headers[-1].markdown("**Del**")

    for p in positions:
        cols = st.columns([2, 3, 2, 2, 2, 2, 2, 2, 1])
        cols[0].write(f"**{p['ticker']}**")
        cols[1].write(p.get("company_name", ""))
        cols[2].write(f"{p.get('quantity', 0):,.4g}")
        cols[3].write(f"{p.get('average_cost', 0):,.2f}")
        curr_price = p.get("current_price")
        cols[4].write(f"{curr_price:,.2f}" if curr_price is not None else "—")
        cols[5].write(f"{p.get('cost_basis', 0):,.2f}")
        pnl = p.get("pnl")
        pnl_pct = p.get("pnl_pct")
        pnl_str = fmt_pnl(pnl, p.get("currency", "USD"))
        pct_str = fmt_pct(pnl_pct)
        cols[6].markdown(pnl_str)
        day_pct = p.get("day_change_pct")
        cols[7].markdown(fmt_pct(day_pct))
        if cols[8].button("✕", key=f"del_pos_{p['id']}"):
            delete_json(f"/portfolio/{p['id']}")
            st.rerun()


# ─── Alerts tab ──────────────────────────────────────────────────────────────
def tab_alerts():
    st.header("Alerts")
    alerts = get_json("/alerts")
    if not alerts:
        st.info("No alerts yet. Run a monitoring cycle to generate them.")
        return

    severity_filter = st.multiselect(
        "Filter by severity",
        ["high", "medium", "low"],
        default=["high", "medium", "low"],
    )
    filtered = [a for a in alerts if a.get("severity") in severity_filter]

    for a in filtered:
        sev = a.get("severity", "low")
        icon = SEVERITY_COLOR.get(sev, "⚪")
        ticker = a.get("ticker") or "—"
        with st.expander(f"{icon} **{ticker}** — {a['title']} `{a['created_at'][:16]}`"):
            st.write(a["message"])
            col1, col2, col3 = st.columns(3)
            col1.caption(f"Type: `{a['alert_type']}`")
            col2.caption(f"Severity: `{sev}`")
            col3.caption(f"Sent: {'Yes' if a.get('sent') else 'No'}")
            if a.get("source_url"):
                st.markdown(f"[Source]({a['source_url']})")


# ─── Catalysts tab ───────────────────────────────────────────────────────────
def tab_catalysts():
    st.header("Catalyst Calendar")
    catalysts = get_json("/catalysts")
    if not catalysts:
        st.info("No catalyst events found.")
        return

    df = pd.DataFrame(catalysts)
    df["event_date"] = pd.to_datetime(df["event_date"])
    df = df.sort_values("event_date")
    df["confidence"] = df["confidence"].apply(lambda x: f"{x:.0%}")
    df["event_date"] = df["event_date"].dt.strftime("%Y-%m-%d")

    display_cols = ["ticker", "title", "catalyst_type", "event_date", "confidence"]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker", width="small"),
            "title": st.column_config.TextColumn("Title", width="large"),
            "catalyst_type": st.column_config.TextColumn("Type", width="medium"),
            "event_date": st.column_config.TextColumn("Date", width="small"),
            "confidence": st.column_config.TextColumn("Confidence", width="small"),
        },
    )


# ─── News & Analysis tab ──────────────────────────────────────────────────────
def tab_news():
    st.header("News & AI Analysis")

    col_news, col_analysis = st.columns(2)

    with col_news:
        st.subheader("Latest News")
        news = get_json("/news")
        if not news:
            st.info("No news items.")
        else:
            for n in news[:15]:
                with st.expander(f"[{n.get('ticker') or n.get('sector') or '—'}] {n['title'][:80]}"):
                    st.write(n.get("summary", ""))
                    st.caption(f"Source: {n.get('source')} | {n['published_at'][:10]}")
                    if n.get("source_url"):
                        st.markdown(f"[Read more]({n['source_url']})")

    with col_analysis:
        st.subheader("AI Analyses")
        analyses = get_json("/analyses")
        if not analyses:
            st.info("No analyses yet.")
        else:
            for an in analyses[:15]:
                direction = an.get("impact_direction", "unknown")
                icon = DIRECTION_COLOR.get(direction, "❓")
                ticker = an.get("ticker") or "—"
                with st.expander(f"{icon} [{ticker}] {an['summary'][:70]}"):
                    st.write(f"**Reasoning:** {an.get('reasoning')}")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Direction", direction.title())
                    c2.metric("Level", an.get("impact_level", "—").title())
                    c3.metric("Confidence", f"{an.get('confidence', 0):.0%}")
                    st.caption(an["created_at"][:16])


# ─── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    st.set_page_config(
        page_title="Investment Agent System",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    render_sidebar()

    st.title("📈 Investment Agent System")

    tabs = st.tabs(["Dashboard", "Watchlist", "Portfolio", "Alerts", "Catalysts", "News & Analysis"])

    with tabs[0]:
        tab_dashboard()
    with tabs[1]:
        tab_watchlist()
    with tabs[2]:
        tab_portfolio()
    with tabs[3]:
        tab_alerts()
    with tabs[4]:
        tab_catalysts()
    with tabs[5]:
        tab_news()


if __name__ == "__main__":
    main()
