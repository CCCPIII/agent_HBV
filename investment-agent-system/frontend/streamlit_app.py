import json
from datetime import datetime

import requests
import streamlit as st

API_URL = st.secrets.get("api_url", "http://localhost:8000")


def get_json(path: str):
    try:
        response = requests.get(f"{API_URL}{path}")
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"Failed to fetch {path}: {exc}")
        return []


def post_json(path: str, payload: dict):
    try:
        response = requests.post(f"{API_URL}{path}", json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"Failed to post {path}: {exc}")
        return None


def main() -> None:
    st.set_page_config(page_title="Investment Agent System", layout="wide")
    st.title("Investment Agent System")

    tabs = st.tabs(["Watchlist", "Portfolio", "Alerts", "Catalysts", "News/Analysis", "Run Monitor"])

    with tabs[0]:
        st.header("Watchlist")
        with st.form("add_watchlist"):
            ticker = st.text_input("Ticker").upper()
            company_name = st.text_input("Company Name")
            exchange = st.text_input("Exchange")
            sector = st.text_input("Sector")
            threshold = st.number_input("Alert Threshold %", value=5.0)
            active = st.checkbox("Active", value=True)
            submitted = st.form_submit_button("Add Watchlist Item")
            if submitted and ticker and company_name:
                post_json("/watchlist", {
                    "ticker": ticker,
                    "company_name": company_name,
                    "exchange": exchange,
                    "sector": sector,
                    "alert_threshold_percent": threshold,
                    "active": active,
                })
                st.experimental_rerun()

        items = get_json("/watchlist")
        if items:
            st.table(items)

    with tabs[1]:
        st.header("Portfolio")
        with st.form("add_position"):
            ticker = st.text_input("Ticker", key="portfolio_ticker").upper()
            company_name = st.text_input("Company Name", key="portfolio_name")
            quantity = st.number_input("Quantity", value=0.0)
            average_cost = st.number_input("Average Cost", value=0.0)
            currency = st.text_input("Currency", value="USD")
            purchase_date = st.date_input("Purchase Date")
            submitted = st.form_submit_button("Add Position")
            if submitted and ticker and company_name:
                post_json("/portfolio", {
                    "ticker": ticker,
                    "company_name": company_name,
                    "quantity": quantity,
                    "average_cost": average_cost,
                    "currency": currency,
                    "purchase_date": purchase_date.isoformat(),
                    "active": True,
                })
                st.experimental_rerun()

        positions = get_json("/portfolio")
        if positions:
            st.table(positions)

    with tabs[2]:
        st.header("Alerts")
        alerts = get_json("/alerts")
        if alerts:
            st.table(alerts)

    with tabs[3]:
        st.header("Catalyst Calendar")
        catalysts = get_json("/catalysts")
        if catalysts:
            st.table(catalysts)

    with tabs[4]:
        st.header("News and Analysis")
        news = get_json("/news")
        analyses = get_json("/analyses")
        if news:
            st.subheader("News")
            st.table(news)
        if analyses:
            st.subheader("Analyses")
            st.table(analyses)

    with tabs[5]:
        st.header("Run Monitor")
        if st.button("Run monitoring cycle"):
            result = post_json("/monitor/run-once", {})
            if result:
                st.success("Monitor run completed")
                st.json(result)

    st.sidebar.title("Backend")
    st.sidebar.write(f"API URL: {API_URL}")


if __name__ == "__main__":
    main()
