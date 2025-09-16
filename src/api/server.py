# src/api/server.py
from fastapi import FastAPI, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from datetime import datetime, timezone
from pathlib import Path
import hashlib
from notify.webhook import notify_slack_blocks

from dotenv import load_dotenv
load_dotenv()  # .env 자동 로드

from ml.anomaly import compute_metrics
from ai.summarize import summarize_alerts

# ====== DB 경로 설정 (src/data/events.sqlite) ======
BASE_DIR = Path(__file__).resolve().parents[1]  # src/
DB_PATH = BASE_DIR / "data" / "events.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", future=True)

app = FastAPI(title="Login API · Anomaly Detection + Azure AI Summary")

# ====== 초기 테이블 생성 ======
with engine.begin() as conn:
    conn.exec_driver_sql("""
    CREATE TABLE IF NOT EXISTS login_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL,
      channel TEXT,
      user_hash TEXT,
      ip TEXT,
      ua TEXT,
      fingerprint TEXT,
      result TEXT,
      fail_reason TEXT,
      latency_ms INTEGER
    );
    """)

# ====== 모델 ======
class LoginReq(BaseModel):
    email: str | None = None
    password: str | None = None
    channel: str = "WEB"
    fingerprint: str = "anon"
    ua: str | None = None
    ip: str | None = None

# ====== 엔드포인트들 ======
@app.post("/login")
async def login(req: LoginReq, request: Request):
    # 토이 규칙: user@example.com / pass123 → SUCCESS 그 외 FAIL
    ok = (req.email == "user@example.com" and req.password == "pass123")
    result = "SUCCESS" if ok else "FAIL"
    fail_reason = "NONE" if ok else "INVALID_PW"
    latency_ms = 80 if ok else 120

    user_hash = hashlib.sha256((req.email or "").encode()).hexdigest()
    ip = req.ip or request.client.host
    ua = req.ua or request.headers.get("user-agent", "")
    now = datetime.now(timezone.utc).isoformat()

    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO login_events
              (ts, channel, user_hash, ip, ua, fingerprint, result, fail_reason, latency_ms)
              VALUES (:ts, :channel, :user_hash, :ip, :ua, :fp, :result, :fail, :lat)"""),
            dict(ts=now, channel=req.channel, user_hash=user_hash, ip=ip, ua=ua,
                 fp=req.fingerprint, result=result, fail=fail_reason, lat=latency_ms)
        )
    return {"ok": ok, "result": result}

@app.get("/metrics")
def metrics():
    """
    최근 ~60분 데이터를 바탕으로 KPI/시계열/채널별 현황 및 알림을 생성하고,
    Azure OpenAI로 요약(summary)을 덧붙여 반환한다.
    """
    base = compute_metrics(engine)
    try:
        base["summary"] = summarize_alerts(base)
    except Exception:
        base["summary"] = None

    # 슬랙 Block Kit 알림
    for a in base.get("alerts", []):
        notify_slack_blocks(a, base.get("summary"), base.get("kpis", {}))

    return base
