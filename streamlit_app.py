"""Streamlit UI: collect a trip request, run the multi-agent planner, email the plan.

Run with:
    streamlit run streamlit_app.py
"""
import asyncio
from datetime import date, timedelta

import streamlit as st

from app.config import settings
from app.main import plan_trip
from app.notifications import EmailError, is_valid_email, send_plan_email

st.set_page_config(page_title="Travel Planner", page_icon="✈️", layout="wide")
st.title("✈️ Light Planning Multi-Agent Travel System")
st.caption("Planner → Flight / Hotel / Activity agents (parallel) → Blackboard → Excel MCP → Budget → Output")


def send_email(markdown_plan: str, recipient: str, subject: str) -> None:
    try:
        with st.spinner(f"Sending the plan to {recipient}..."):
            send_plan_email(markdown_plan, recipient, subject)
        st.success(f"Plan sent to {recipient}.")
    except EmailError as exc:
        st.error(f"Email not sent: {exc}")


# ---------------------------------------------------------------------------
# Sidebar: delivery + system status
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Delivery")
    recipient = st.text_input("Send plan to", value=settings.EMAIL_RECIPIENT)
    auto_send = st.checkbox("Email the plan automatically", value=True)
    if not settings.email_enabled:
        st.warning("SMTP is not configured. Set SMTP_USERNAME and SMTP_PASSWORD in `.env` to enable email.")

    st.header("System")
    st.write(f"Data provider: `{settings.TRAVEL_DATA_PROVIDER}`")
    st.write(f"LLM: {'enabled (' + settings.LLM_MODEL + ')' if settings.llm_enabled else 'disabled (deterministic mode)'}")
    if settings.TRAVEL_DATA_PROVIDER == "sample":
        st.info("Sample mode covers Paris, Rome, Dubai and Tokyo (origins: Cairo, London, New York). "
                "Prices are demo data.")

# ---------------------------------------------------------------------------
# Request form
# ---------------------------------------------------------------------------
with st.form("trip_form"):
    col1, col2 = st.columns(2)
    with col1:
        destination = st.text_input("Destination *", placeholder="Paris")
        origin = st.text_input("Origin (optional)", placeholder="Cairo")
        travel_date = st.date_input("Travel date *", value=date.today() + timedelta(days=14), min_value=date.today())
        travel_time = st.time_input("Departure time (optional)", value=None)
    with col2:
        duration_days = st.number_input("Duration (days) *", min_value=1, max_value=30, value=5, step=1)
        use_budget = st.checkbox("I have a budget")
        budget = st.number_input("Budget", min_value=1.0, value=1500.0, step=50.0, disabled=not use_budget)
        currency = st.selectbox("Currency", ["USD", "EUR", "GBP", "EGP", "AED", "JPY"])
    submitted = st.form_submit_button("Create travel plan", type="primary", use_container_width=True)

if submitted:
    if not destination.strip():
        st.error("Please enter a destination.")
        st.stop()
    if auto_send and not is_valid_email(recipient):
        st.error(f"'{recipient}' is not a valid email address.")
        st.stop()

    request = {
        "destination": destination,
        "travel_date": f"{travel_date.isoformat()}T{travel_time.strftime('%H:%M')}" if travel_time
        else travel_date.isoformat(),
        "duration_days": int(duration_days),
        "origin": origin or None,
        "budget": float(budget) if use_budget else None,
        "currency": currency,
    }

    with st.spinner("Agents are planning your trip..."):
        try:
            result = asyncio.run(plan_trip(request))
        except Exception as exc:  # the graph degrades gracefully; this is a last-resort guard
            st.error(f"Planning failed unexpectedly: {exc}")
            st.stop()

    st.session_state["result"] = result
    st.session_state["emailed"] = False
    if auto_send and result.state.get("request_valid"):
        subject = f"Your travel plan: {result.plan.destination}, {result.plan.travel_date} ({result.plan.duration_days} days)"
        send_email(result.plan.markdown, recipient, subject)
        st.session_state["emailed"] = True

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
result = st.session_state.get("result")
if result:
    state = result.state
    if state.get("request_valid"):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Flights", state.get("flight_status", "-"))
        c2.metric("Hotels", state.get("hotel_status", "-"))
        c3.metric("Activities", state.get("activity_status", "-"))
        selected = (state.get("budget_result") or {}).get("selected")
        c4.metric("Estimated total",
                  f"{selected['estimated_total']:,.0f} {state.get('currency')}" if selected else "Unavailable")

    tab_plan, tab_blackboard, tab_budget = st.tabs(["Travel plan", "Blackboard", "Budget (via Excel MCP)"])
    with tab_plan:
        st.markdown(result.plan.markdown)
    with tab_blackboard:
        st.json(result.blackboard.get_all(), expanded=False)
    with tab_budget:
        st.json(state.get("budget_result") or {}, expanded=False)

    b1, b2 = st.columns(2)
    b1.download_button("Download plan (.md)", result.plan.markdown, file_name="travel_plan.md",
                       mime="text/markdown", use_container_width=True)
    if state.get("request_valid") and b2.button("Send plan by email", use_container_width=True):
        send_email(result.plan.markdown, recipient,
                   f"Your travel plan: {result.plan.destination}, {result.plan.travel_date}")
