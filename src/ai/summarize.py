# src/ai/summarize.py
import os
import json
import requests
from typing import Optional
from dotenv import load_dotenv

# .env 자동 로드 (중복 호출해도 무해)
load_dotenv()

ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
DEPLOY = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
# v1 또는 2024-10-01-preview 둘 다 가능. v1은 model에 "배포 이름"을 넣음.
USE_V1 = True
API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-01-preview")


def _call_v1_chat(prompt: str) -> str:
    url = f"{ENDPOINT}/openai/v1/chat/completions"
    headers = {"api-key": API_KEY, "Content-Type": "application/json"}
    body = {
        "model": DEPLOY,  # v1은 model 자리에 '배포 이름' 사용
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    r = requests.post(url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def _call_preview_chat(prompt: str) -> str:
    url = f"{ENDPOINT}/openai/deployments/{DEPLOY}/chat/completions?api-version={API_VERSION}"
    headers = {"api-key": API_KEY, "Content-Type": "application/json"}
    body = {"messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
    r = requests.post(url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def summarize_alerts(metrics: dict) -> Optional[str]:
    """
    Azure OpenAI로 /metrics 내용을 요약.
    - 환경변수 미설정/호출 실패 시 None 반환.
    """
    if not ENDPOINT or not API_KEY or not DEPLOY:
        return None

    # 입력이 너무 커지지 않게 timeseries는 최근 30포인트만 사용
    m = dict(metrics)
    ts = m.get("timeseries", [])
    m["timeseries"] = ts[-30:] if isinstance(ts, list) else []

    prompt = (
        "당신은 KT 로그인 서비스 관제 보조 AI입니다.\n"
        "주어진 KPI, 최근 시계열, 알림 리스트를 기반으로:\n"
        "1) 한 문장 요약, 2) 가능한 원인(최대 4개) 불릿, 3) 즉각 조치(최대 4개) 불릿을 "
        "간결한 한국어로 작성하세요. 이슈가 없다면 건강한 상태임을 한 줄로 알려주세요.\n\n"
        f"JSON 입력:\n{json.dumps(m)[:6000]}"
    )

    try:
        if USE_V1:
            return _call_v1_chat(prompt)
        return _call_preview_chat(prompt)
    except Exception as e:
        print("⚠️ summarize_alerts 오류:", e)
        return None
