# src/notify/webhook.py
import os
import time
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

SLACK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
# 같은 알림이 짧은 시간에 중복 발송되는 걸 막기 위한 초간단 디듀프(메모리)
_LAST_SENT: Dict[str, float] = {}
DEDUP_TTL = int(os.environ.get("SLACK_DEDUP_TTL_SEC", "180"))  # 기본 3분

def _should_skip(key: str) -> bool:
    now = time.time()
    last = _LAST_SENT.get(key, 0)
    if now - last < DEDUP_TTL:
        return True
    _LAST_SENT[key] = now
    return False

def notify_slack_text(message: str):
    """단순 텍스트 알림(백업용)"""
    if not SLACK_URL:
        return
    try:
        r = requests.post(SLACK_URL, json={"text": message}, timeout=6)
        r.raise_for_status()
    except Exception as e:
        print("⚠️ Slack(text) notify error:", e)

def _sev_emoji(sev: str) -> str:
    return {"CRIT": "🚨", "WARN": "⚠️", "INFO": "ℹ️"}.get(sev, "🔔")

def build_slack_blocks(alert: Dict[str, Any], summary: Optional[str], kpis: Dict[str, Any]) -> Dict[str, Any]:
    """Block Kit 페이로드 생성"""
    sev = str(alert.get("severity", "INFO"))
    emoji = _sev_emoji(sev)
    header_text = f"{emoji} [{sev}] {alert.get('type','ALERT')}"
    subtitle = alert.get("message", "")
    when = alert.get("time", "")

    attempts = kpis.get("attempts", 0)
    failures = kpis.get("failures", 0)
    failRate = kpis.get("failRate", 0.0)
    highRisk = kpis.get("highRisk", 0)

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": header_text, "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{subtitle}*\n`{when}`"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Attempts:*\n{attempts:,}"},
                {"type": "mrkdwn", "text": f"*Failures:*\n{failures:,}"},
                {"type": "mrkdwn", "text": f"*Fail Rate:*\n{failRate*100:.1f}%"},
                {"type": "mrkdwn", "text": f"*High-Risk:*\n{highRisk:,}"},
            ],
        },
    ]

    if summary:
        blocks += [
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*AI 요약*\n{summary}"}},
        ]

    blocks += [
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "_자동 생성 · Login Anomaly Monitor_"}]},
    ]
    return {"blocks": blocks}

def notify_slack_blocks(alert: Dict[str, Any], summary: Optional[str], kpis: Dict[str, Any]):
    """Block Kit 알림(중복 억제 포함)"""
    if not SLACK_URL:
        return
    # 동일 유형/중요도/메시지를 TTL 내 중복 방지
    dedup_key = f"{alert.get('severity')}|{alert.get('type')}|{alert.get('message')}"
    if _should_skip(dedup_key):
        return
    try:
        payload = build_slack_blocks(alert, summary, kpis)
        r = requests.post(SLACK_URL, json=payload, timeout=6)
        r.raise_for_status()
    except Exception as e:
        print("⚠️ Slack(blocks) notify error:", e)
        # 실패 시 텍스트로 폴백
        msg = f"[{alert.get('severity')}] {alert.get('type')} - {alert.get('message')} @ {alert.get('time')}\n\n{summary or ''}"
        notify_slack_text(msg)
