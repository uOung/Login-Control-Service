import time
import random
import requests
import os

from dotenv import load_dotenv
load_dotenv()  # .env 자동 로드

# ===== 설정 =====
BASE = os.environ.get("TRAFFIC_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
EMAIL_OK = "user@example.com"
PASS_OK = "pass123"
CHANNELS = ["WEB", "MYKT", "MEMBERSHIP"]

def hit(success_ratio=0.8):
    """
    로그인 시도를 1회 수행
    success_ratio: 성공 확률 (0.0 ~ 1.0)
    """
    ok = random.random() < success_ratio
    body = {
        "email": EMAIL_OK if ok else "user@example.com",
        "password": PASS_OK if ok else "wrong",
        "channel": random.choice(CHANNELS),
        "fingerprint": f"fp-{random.randint(1,6)}"
    }
    try:
        r = requests.post(f"{BASE}/login", json=body, timeout=3)
        print(r.json())
    except Exception as e:
        print("요청 실패:", e)

if __name__ == "__main__":
    print("트래픽 발생 시작! Ctrl+C로 중단하세요.")
    while True:
        # 10% 확률로 공격/장애 상황(실패율 급증) 흉내내기
        if random.random() < 0.1:
            for _ in range(20):
                hit(success_ratio=0.3)   # 실패율 높음
        else:
            for _ in range(5):
                hit(success_ratio=0.85)  # 정상: 성공 위주
        time.sleep(2)