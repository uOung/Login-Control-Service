# AI 기반 로그인 이상징후 탐지 및 관제 자동화

## 📌 프로젝트 개요
KT.com, 마이케이티앱, KT 멤버십앱 등의 로그인 시스템에서 발생하는 대규모 트래픽 및 다양한 인증 요청을 실시간으로 분석하고, AI를 활용해 **비정상 로그인 패턴**을 조기에 탐지하여 관제팀에 자동 알림 및 대응 가이드를 제공하는 시스템입니다.

---

## 🎯 목적
- **로그인 보안 강화**: 계정 탈취, 무차별 대입 공격, 봇 로그인 등을 사전에 차단
- **관제 효율성 향상**: 대량의 로그를 AI로 전처리·분석하여 관제 인력이 고위험 이벤트에만 집중
- **사용자 경험 유지**: 불필요한 차단 최소화 및 정상 사용자의 인증 편의성 보장

---

## 🛠 기술 스택
- **클라우드**: Azure Machine Learning, Azure Functions, Azure Event Hub
- **데이터 수집/처리**: Azure Data Explorer(Kusto), Azure Blob Storage
- **AI 모델**: 이상징후 탐지 모델(Anomaly Detection), 시계열 예측 모델
- **알림/연동**: Azure Logic Apps, Teams Webhook, Slack API

---

## 🔍 주요 기능
1. **실시간 로그인 로그 수집**
   - API Gateway 또는 로그 수집 에이전트를 통해 Azure Event Hub로 전송
2. **AI 기반 이상징후 탐지**
   - 로그인 시도 횟수, IP 분포, 기기 정보, 지역 정보 등을 학습한 모델로 비정상 패턴 식별
3. **위험도 점수화(Risk Scoring)**
   - 의심 수준을 점수화하여 관제 알람의 우선순위 결정
4. **자동 알림 및 대응**
   - 위험도 임계치 초과 시 관제팀 Slack/Teams 채널로 실시간 전송
   - 필요 시 Azure Functions를 통해 자동 계정 잠금, Captcha 강제 등 조치
5. **관제 대시보드**
   - Azure Dashboard + Power BI를 이용해 실시간 시각화

---

## 📊 시스템 아키텍처(예시)

```plaintext
[Login Attempt]
        │
        ▼
[Azure Event Hub] ──▶ [Azure Data Explorer] ──▶ [관제 대시보드]
        │
        ▼
[Anomaly Detection Model] ──▶ [Risk Scoring]
        │
        ├──▶ [자동 조치: Azure Functions]
        └──▶ [알림 전송: Slack / Teams]
