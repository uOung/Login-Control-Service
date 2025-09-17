from sqlalchemy import text
import pandas as pd
from datetime import datetime, timedelta, timezone
from sklearn.ensemble import IsolationForest
import numpy as np

def _read_last_minutes(engine, minutes=60):
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    with engine.begin() as conn:
        df = pd.read_sql_query(
            text("SELECT * FROM login_events WHERE ts >= :since"),
            conn, params={"since": since}
        )
    if df.empty:
        return pd.DataFrame({
            "ts": pd.Series(dtype="datetime64[ns, UTC]"),
            "channel": pd.Series(dtype="object"),
            "result": pd.Series(dtype="object"),
            "fingerprint": pd.Series(dtype="object"),
            "user_hash": pd.Series(dtype="object"),
            "latency_ms": pd.Series(dtype="float64"),
        })

    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    df["latency_ms"] = pd.to_numeric(df.get("latency_ms", pd.Series(dtype="float64")), errors="coerce")
    return df

def _make_timeseries(df: pd.DataFrame, freq="1min"):
    if df.empty:
        # ts 인덱스가 비어 있어도 DatetimeIndex가 되도록 생성
        empty_idx = pd.DatetimeIndex([], tz="UTC")
        ts = pd.DataFrame(index=empty_idx, columns=["attempts","failures","latency_ms"]).fillna(0)
        bc = pd.DataFrame(columns=["channel","attempts","failures","failRate"])
        return ts, bc
    
    # 1) 시도/실패 시계열
    # 1) ts를 tz-aware datetime으로 보정하고 인덱스로 세팅 + 정렬
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    df = df.dropna(subset=["ts"])
    df = df.set_index("ts").sort_index()

    # (안전) result/latency 타입 보정
    df["result"] = df["result"].astype("string")
    df["latency_ms"] = pd.to_numeric(df.get("latency_ms", pd.Series(dtype="float64")), errors="coerce")

    # 2) 분단위 집계
    g = df.groupby(pd.Grouper(freq=freq))
    attempts = g.size().rename("attempts")
    failures = g.apply(lambda x: (x["result"]=="FAIL").sum()).rename("failures")
    latency = g["latency_ms"].mean().rename("latency_ms")
    ts = pd.concat([attempts, failures, latency], axis=1).fillna(0)
    ts["fail_rate"] = np.where(ts["attempts"]>0, ts["failures"]/ts["attempts"], 0.0)

    # 2) 채널별
    bc = (df.assign(fail=(df["result"]=="FAIL").astype(int))
            .groupby(["channel"])
            .agg(attempts=("result","count"), failures=("fail","sum"))
            .reset_index())
    if not bc.empty:
        bc["failRate"] = np.where(bc["attempts"]>0, bc["failures"]/bc["attempts"], 0.0)
    return ts, bc

def _iforest_scores(ts: pd.DataFrame):
    """간단한 비지도 이상치 점수 (attempts/failures/fail_rate/latency)"""
    if ts.empty or len(ts) < 10:
        return pd.Series([0.0]*len(ts), index=ts.index)
    feats = ts[["attempts","failures","fail_rate","latency_ms"]].to_numpy(dtype=float)
    # NaN/inf 방어
    feats = np.nan_to_num(feats, copy=False, nan=0.0, posinf=1e9, neginf=-1e9)
    # 스케일링 없이도 대략 동작하도록 contamination 낮게
    model = IsolationForest(n_estimators=100, contamination=0.08, random_state=42)
    model.fit(feats)
    score = -model.score_samples(feats)      # 값 클수록 이상
    return pd.Series(score, index=ts.index)

def compute_metrics(engine):
    df = _read_last_minutes(engine, minutes=60)
    ts, bc = _make_timeseries(df)

    # KPI (마지막 1분)
    last = ts.tail(1)
    if last.empty:
        kpis = dict(attempts=0, failures=0, failRate=0.0, highRisk=0)
    else:
        kpis = dict(
            attempts=int(last["attempts"].iloc[0]),
            failures=int(last["failures"].iloc[0]),
            failRate=float(last["fail_rate"].iloc[0]),
            highRisk=int(max(0, round(last["failures"].iloc[0]*0.3)))
        )

    # 이상치 점수
    ts["anom_score"] = _iforest_scores(ts)

    # 알람 생성 규칙 (간단)
    alerts = []
    if not last.empty and (last["fail_rate"].iloc[0] > 0.4 and last["attempts"].iloc[0] >= 30):
        alerts.append({
            "id": f"FR-{int(datetime.now().timestamp())}",
            "time": datetime.now(timezone.utc).isoformat(),
            "severity": "CRIT",
            "type": "FAIL_RATE_SPIKE",
            "message": f"Fail rate {(last['fail_rate'].iloc[0]*100):.1f}% over threshold"
        })
    # 최근 10분 내 IsolationForest 점수 상위 포인트
    recent = ts.tail(10).sort_values("anom_score", ascending=False).head(1)
    if not recent.empty and recent["anom_score"].iloc[0] > 0.6:
        alerts.append({
            "id": f"ML-{int(datetime.now().timestamp())}",
            "time": recent.index[-1].to_pydatetime().isoformat(),
            "severity": "WARN",
            "type": "ML_ANOMALY",
            "message": f"Model anomaly score {recent['anom_score'].iloc[0]:.2f}"
        })

    # 응답 포맷(프론트 호환)
    timeseries = [
        dict(ts=i.isoformat(), attempts=int(r.attempts), failures=int(r.failures))
        for i, r in ts.iterrows()
    ]
    byChannel = [
        dict(channel=row.channel, attempts=int(row.attempts),
             failures=int(row.failures), failRate=float(row.failRate))
        for _, row in bc.iterrows()
    ] if not bc.empty else []

    return {
        "kpis": kpis,
        "timeseries": timeseries,
        "byChannel": byChannel,
        "alerts": alerts
    }
