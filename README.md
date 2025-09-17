# Login Control Service

Azure 환경에서 로그인 이벤트를 수집·분석하고, 통계 및 이상 징후를 탐지해 알림을 제공하는 관제용 서비스입니다.  
실시간 로그인 데이터를 처리하여 보안 사고 조기 탐지 및 서비스 안정성 향상을 목표로 합니다.

---

## 🔧 사용 기술 스택

- **언어/라이브러리**
  - Python 3.11
  - pandas / NumPy : 시계열 집계, 통계 처리
  - scikit-learn (IsolationForest) : 비지도 이상치 탐지
  - SQLAlchemy : DB 접근 (PostgreSQL, Azure Database 등)

- **클라우드 서비스 (Azure)**
  - **Azure Event Hub** : 로그인 이벤트 수집 스트리밍
  - **Azure Data Explorer (ADX)** : 시계열/로그 저장 및 분석
  - **Azure Functions / App Service** : 분석 로직 실행, API 제공
  - **Azure Logic Apps** : 알람 전달 워크플로우 (Slack/Teams 등)
  - **Azure Monitor / Log Streaming** : 로그 수집 및 모니터링

- **CI/CD**
  - GitHub Actions : 빌드 및 배포 자동화
  - Azure CLI : 앱 로그 조회, 환경 구성 관리

---

## 📐 아키텍처 개요

1. **로그인 이벤트 수집**
   - 서비스에서 발생한 로그인 이벤트가 Event Hub에 전송됨

2. **저장 및 분석**
   - Event Hub → ADX 저장
   - Azure Functions/App Service가 주기적으로 DB를 조회하여 최근 이벤트 가져옴

3. **집계 및 이상치 탐지**
   - pandas `groupby + Grouper`로 분단위 시계열 집계
   - 실패율, 지연시간(latency) 평균 계산
   - IsolationForest로 비정상 패턴 감지

4. **알람**
   - 실패율 스파이크(>40%, 시도 ≥30) 감지 시 CRIT 알람
   - IsolationForest 이상치 점수 기준 WARN 알람
   - Logic Apps을 통해 Slack/Teams으로 전달

---

## 🧪 테스트 가이드

### 1. 로컬 실행
```bash
# 의존성 설치
pip install -r requirements.txt

# DB 연결 확인 (환경변수 설정)
export DB_URL="postgresql://user:pass@host:5432/dbname"

# 메트릭 계산 실행 (예: FastAPI/Flask라면 uvicorn)
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### 2. 단위 테스트
```bash
pytest tests/ -v
```

- `_make_timeseries` : 빈 데이터프레임 입력 시에도 오류 없이 동작해야 함  
- `_iforest_scores` : 최소 10개 이상 데이터가 있을 때만 모델 학습되는지 확인  

### 3. Azure 환경 배포
```bash
# 웹앱 로그 스트리밍 활성화
az webapp log config \
  --name login-control \
  --resource-group rg-ktds5-04 \
  --application-logging filesystem --level information

# 로그 확인
az webapp log tail --name login-control --resource-group rg-ktds5-04
```

### 4. 헬스체크
- 브라우저 또는 curl로 `/` 엔드포인트 호출
```bash
curl https://<APP_NAME>.azurewebsites.net/
# {"ok": true} 응답 확인
```

---

## 📊 주요 지표 (KPIs)

- `attempts` : 로그인 시도 수
- `failures` : 실패 횟수
- `failRate` : 실패율
- `latency_ms` : 평균 응답 지연 시간
- `anom_score` : IsolationForest 이상치 점수

---

## 🚨 알람 규칙

- **FAIL_RATE_SPIKE**
  - 조건 : 실패율 > 40% & 시도 ≥ 30
  - 심각도 : CRIT

- **ML_ANOMALY**
  - 조건 : IsolationForest 점수 > 0.6
  - 심각도 : WARN
