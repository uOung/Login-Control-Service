# src/dashboard/streamlit_app.py
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Login Anomaly Monitor (Python + Azure AI)", layout="wide")
st.title("🔎 Login Anomaly Monitor (Python + Azure AI Summary)")

# ---- Controls ----
with st.sidebar:
    st.header("Settings")
    base = st.text_input("API Base URL", value="http://127.0.0.1:8080", help="예: http://127.0.0.1:8080")
    interval = st.slider("Auto refresh (sec)", 3, 30, 7)
    manual = st.button("🔄 Refresh now")

status = st.empty()
kpi_area = st.empty()
left, right = st.columns([2, 1])
alerts_area = st.empty()
summary_area = st.empty()
footer = st.empty()

def fetch(base_url: str) -> dict:
    resp = requests.get(f"{base_url.rstrip('/')}/metrics", timeout=10)
    resp.raise_for_status()
    return resp.json()

def render(data: dict):
    k = data.get("kpis", {})
    attempts = k.get("attempts", 0)
    failures = k.get("failures", 0)
    fail_rate = k.get("failRate", 0.0)
    high_risk = k.get("highRisk", 0)

    # KPIs
    with kpi_area.container():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Attempts (last min)", f"{attempts:,}")
        c2.metric("Failures (last min)", f"{failures:,}")
        c3.metric("Fail Rate", f"{fail_rate*100:.1f}%")
        c4.metric("High-Risk (est.)", f"{high_risk:,}")

    # Charts
    with left:
        st.subheader("Attempts & Failures (last ~60m)")
        ts = pd.DataFrame(data.get("timeseries", []))
        if not ts.empty:
            ts["ts"] = pd.to_datetime(ts["ts"])
            ts = ts.set_index("ts")
            st.line_chart(ts[["attempts", "failures"]])
        else:
            st.info("No data yet. /login 호출로 데이터를 생성하세요.")

    with right:
        st.subheader("By Channel")
        bc = pd.DataFrame(data.get("byChannel", []))
        if not bc.empty:
            st.bar_chart(bc.set_index("channel")[["attempts", "failures"]])
            st.caption("Fail Rate (%)")
            st.table(
                bc[["channel", "failRate"]].assign(failRate=lambda d: (d["failRate"] * 100).round(1))
            )
        else:
            st.info("No channel breakdown yet.")

    # Alerts
    with alerts_area.container():
        st.subheader("Recent Alerts")
        alerts = list(reversed(data.get("alerts", [])))
        if not alerts:
            st.write("No alerts.")
        else:
            for a in alerts:
                sev = a.get("severity", "INFO")
                sev_color = dict(CRIT="red", WARN="orange", INFO="blue").get(sev, "gray")
                st.markdown(
                    f"**[{sev}]** <span style='color:{sev_color}'>`{a.get('type','')}`</span> — {a.get('message','')}"
                    f"<br/><span style='color:#8aa'>🕒 {a.get('time','')}</span>",
                    unsafe_allow_html=True,
                )

    # AI Summary
    with summary_area.container():
        st.subheader("AI 요약 (Azure OpenAI)")
        summary = data.get("summary")
        if summary:
            st.markdown(summary)
        else:
            st.caption("요약 없음 (환경변수 미설정 또는 데이터 부족/호출 실패)")

# ---- Main loop ----
while True:
    try:
        data = fetch(base)
        render(data)
        status.info(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        status.error(f"Fetch error: {e}")

    # manual refresh button clicked?
    if manual:
        manual = False  # 한번 처리 후 초기화
        continue

    time.sleep(interval)
