# src/dashboard/streamlit_app.py
import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # .env 자동 로드

# =========================
# Settings
# =========================
ENV_API_BASE = os.environ.get("API_BASE_URL")

st.set_page_config(page_title="Login Control Dashboard", layout="wide")
st.title("🔐 Login Control Dashboard")

# ---- Controls ----
with st.sidebar:
    st.header("Settings")
    base = st.text_input(
        "API Base URL",
        value=ENV_API_BASE or "",
        help="예: https://login-control.azurewebsites.net",
        placeholder="https://<your-fastapi-app>.azurewebsites.net",
    )
    manual = st.button("🔄 Refresh now")  # 수동 새로고침만 유지

status = st.empty()
kpi_area = st.empty()
left, right = st.columns([2, 1])
alerts_area = st.empty()
summary_area = st.empty()

# =========================
# API fetch
# =========================
@st.cache_data(ttl=10)
def fetch_metrics_from_api(base_url: str):
    if not base_url:
        raise ValueError("API Base URL이 비어 있습니다. 사이드바에 입력하세요.")
    url = f"{base_url.rstrip('/')}/metrics"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()

def render(data: dict):
    k = data.get("kpis", {}) or {}
    attempts = int(k.get("attempts", 0))
    failures = int(k.get("failures", 0))
    fail_rate = float(k.get("failRate", 0.0))
    high_risk = int(k.get("highRisk", 0))

    # KPIs
    with kpi_area.container():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Attempts (last min)", f"{attempts:,}")
        c2.metric("Failures (last min)", f"{failures:,}")
        c3.metric("Fail Rate", f"{fail_rate*100:.1f}%")
        c4.metric("High-Risk (est.)", f"{high_risk:,}")

    # Charts: Timeseries
    with left:
        st.subheader("Attempts & Failures (last ~60m)")
        ts = pd.DataFrame(data.get("timeseries", []))
        if not ts.empty:
            ts["ts"] = pd.to_datetime(ts["ts"], utc=True, errors="coerce")
            ts = ts.dropna(subset=["ts"]).set_index("ts").sort_index()
            ycols = [c for c in ["attempts", "failures"] if c in ts.columns]
            if ycols:
                st.line_chart(ts[ycols])
            else:
                st.info("표시할 시계열 열이 없습니다.")
        else:
            st.info("No data yet. /login 호출로 데이터를 생성하세요.")

    # Charts: By Channel
    with right:
        st.subheader("By Channel")
        bc = pd.DataFrame(data.get("byChannel", []))
        if not bc.empty:
            idxed = bc.set_index("channel")
            cols = [c for c in ["attempts", "failures"] if c in idxed.columns]
            if cols:
                st.bar_chart(idxed[cols])
            if "failRate" in bc.columns:
                st.caption("Fail Rate (%)")
                st.table(
                    bc[["channel", "failRate"]]
                    .assign(failRate=lambda d: (d["failRate"] * 100).round(1))
                )
        else:
            st.info("No channel breakdown yet.")

    # Alerts
    with alerts_area.container():
        st.subheader("🚨 Recent Alerts")
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
        st.subheader("🔍 AI 요약")
        summary = data.get("summary")
        if summary:
            st.markdown(summary)
        else:
            st.caption("요약 없음 (서버 측 환경변수 미설정 또는 데이터 부족/호출 실패)")

# =========================
# Run (manual refresh only)
# =========================
try:
    if manual:
        st.cache_data.clear()  # 캐시만 지우고 같은 실행 내에서 다시 가져옴
    data = fetch_metrics_from_api(base)
    render(data)
except Exception as e:
    status.error(f"Fetch error: {e}")
    st.stop()
