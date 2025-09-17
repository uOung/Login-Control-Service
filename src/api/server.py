# src/api/server.py
from fastapi import FastAPI, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
import hashlib
import os
import random
import time
import threading

from dotenv import load_dotenv
load_dotenv()  # .env 자동 로드

from ml.anomaly import compute_metrics
from ai.summarize import summarize_alerts
from notify.webhook import notify_slack_blocks

# ====== DB 경로 설정 (src/data/events.sqlite) ======
BASE_DIR = Path(__file__).resolve().parents[1]  # src/
DB_PATH = BASE_DIR / "data" / "events.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", future=True)

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

# ====== 백그라운드 더미 트래픽 생성기 ======
def _insert_dummy_once(engine, success_ratio: float = 0.85) -> None:
    ok = random.random() < success_ratio
    now = datetime.now(timezone.utc).isoformat()

    channel = random.choice(["WEB", "MYKT", "MEMBERSHIP"])
    email = "user@example.com" if ok else "attacker@example.com"
    user_hash = hashlib.sha256(email.encode()).hexdigest()
    ip = random.choice(["10.0.0.1", "10.0.0.2", "172.16.0.5"])
    ua = "bg-traffic/1.0"
    fingerprint = f"fp-{random.randint(1, 8)}"
    result = "SUCCESS" if ok else "FAIL"
    fail_reason = "NONE" if ok else random.choice(["INVALID_PW", "LOCKED", "OTP_FAIL"])
    latency_ms = int(max(20, random.gauss(90 if ok else 160, 25)))

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO login_events
                    (ts, channel, user_hash, ip, ua, fingerprint, result, fail_reason, latency_ms)
                VALUES
                    (:ts, :channel, :user_hash, :ip, :ua, :fp, :result, :fail_reason, :latency_ms)
            """),
            dict(
                ts=now, channel=channel, user_hash=user_hash,
                ip=ip, ua=ua, fp=fingerprint,
                result=result, fail_reason=fail_reason, latency_ms=latency_ms
            )
        )

def _bg_traffic_loop(engine, stop_event: threading.Event) -> None:
    # 환경변수로 유량/패턴 제어
    base_sleep   = float(os.getenv("BG_BASE_SLEEP",  "2.0"))   # 기본 간격(초)
    burst_prob   = float(os.getenv("BG_BURST_PROB",  "0.12"))  # 버스트(장애/공격) 확률
    normal_succ  = float(os.getenv("BG_NORMAL_SUCC", "0.85"))  # 정상 성공률
    burst_succ   = float(os.getenv("BG_BURST_SUCC",  "0.30"))  # 버스트 성공률
    normal_batch = int(os.getenv("BG_NORMAL_BATCH",  "5"))     # 정상 묶음
    burst_batch  = int(os.getenv("BG_BURST_BATCH",   "20"))    # 버스트 묶음

    while not stop_event.is_set():
        try:
            if random.random() < burst_prob:
                for _ in range(burst_batch):
                    _insert_dummy_once(engine, success_ratio=burst_succ)
            else:
                for _ in range(normal_batch):
                    _insert_dummy_once(engine, success_ratio=normal_succ)
            time.sleep(base_sleep)
        except Exception as e:
            print(f"[bg-traffic] error: {e}", flush=True)
            time.sleep(base_sleep)

# ====== FastAPI lifespan: startup/shutdown 훅 ======
_stop_event: threading.Event | None = None
_bg_thread: threading.Thread | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _stop_event, _bg_thread
    _stop_event = threading.Event()

    if os.getenv("ENABLE_BG_TRAFFIC") == "1":
        print("[bg-traffic] enabled", flush=True)
        _bg_thread = threading.Thread(
            target=_bg_traffic_loop, args=(engine, _stop_event), daemon=True
        )
        _bg_thread.start()
    else:
        print("[bg-traffic] disabled (set ENABLE_BG_TRAFFIC=1 to enable)", flush=True)

    # --- startup 완료 ---
    yield
    # --- shutdown 시작 ---
    if _stop_event:
        _stop_event.set()

app = FastAPI(title="Login API · Anomaly Detection + Azure AI Summary", lifespan=lifespan)

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

@app.get("/health")
def health():
    return {"ok": True}

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
        try:
            notify_slack_blocks(a, base.get("summary"), base.get("kpis", {}))
        except Exception as e:
            print("notify_slack_blocks error:", e, flush=True)

    return base
