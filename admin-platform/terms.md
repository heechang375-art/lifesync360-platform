# LifeSync360 Admin Dashboard 용어집

## 네비게이션

| 영문 | 한글 | 비고 |
|------|------|------|
| 전체 현황 | 전체 현황 | dashboard |
| Customer 360 | Customer 360 | users |
| AI 추천 | AI 추천 | ai |
| 네트워크 | 네트워크 | ops (Network → 변경) |

---

## 전체 현황 (dashboard)

### KPI 카드 (9개)

| 용어 | 출처 | 계산식 |
|------|------|--------|
| 통합 고객 수 | On-Prem master_customer | 전체 100% |
| 플랫폼 가입자 | On-Prem users | 전체의 30% |
| 분석 대상 고객 | On-Prem users_consented | 가입자의 20% · 동의 완료 |
| AI 추천 상태 | DynamoDB | Vertex AI 상태 |
| 누적 추천 이력 | Aurora customer_recommend_history | 누적 건수 |
| 누적 활동 로그 | Aurora customer_dashboard_log | 누적 건수 |
| 추천 CTR (클릭률) | Aurora customer_recommend_history | SUM(clicked) / COUNT(*) · 전체 누적 |
| 구매 전환율 (CVR) | Aurora customer_recommend_history | SUM(purchased) / COUNT(*) · 전체 누적 |
| Redis Cache 수 | Redis DBSIZE | rec:{global_id} · TTL 6h |

### 클라우드 현황 (3개 카드)

| 용어 | 하위 항목 |
|------|-----------|
| AWS 클라우드 | Aurora, DynamoDB, ElastiCache, ECS, ALB, S3 |
| GCP 클라우드 | BigQuery, Vertex AI, Cloud Run |
| 온프레미스 | ls-db, ls-token, ls-api |

### S3 적재 현황 (5개 카드)

| 용어 | 출처 |
|------|------|
| Raw Bucket 총 파일 | S3 lifesync-raw |
| 금일 적재 건수 | S3 파티션 dt=오늘 |
| 페이로드 데이터 | Kinesis 실시간 |
| 그룹사 적재량 | S3 CSV/JSON 합계 |
| 최근 업로드 | S3 최신 객체 |

### 최근 업로드 파일

도메인 뱃지: BANK · CARD · INS · HLT · SEC · ONINS · WEARABLE

---

## AI 추천 (ai)

### 핵심 추천 지표 (KPI 4개)

| 용어 | 출처 | 기간 |
|------|------|------|
| 추천 CTR (클릭률) | Aurora customer_recommend_daily | 최근 1일 |
| 거래율 CVR (전환) | Aurora customer_recommend_daily | 최근 1일 |
| 마지막 배치 갱신 | DynamoDB lifesync_customer_result | update_time |
| 분석 대상 고객 | DynamoDB lifesync_customer_result | scan COUNT |

### 일별 추천 성과 추이 (7일)

| 용어 | 설명 |
|------|------|
| 추천 건수 | 일별 추천 수 (막대) |
| CTR | 클릭률 (선 그래프, 파란색) |
| CVR | 전환율 (선 그래프, 주황색) |
| 상품 TOP 10 | 추천 건수 + CTR 기준 |

### 세그먼트 & 분포 분석

| 용어 | 설명 |
|------|------|
| 카테고리별 추천 | 도넛 차트 |
| 연령대별 추천 성과 | On-Prem 2-step |
| 고객 등급 분포 | DynamoDB dynamic_grade |

### 빅쿼리 분석

| 용어 | 설명 |
|------|------|
| 피처 분포 | Vertex AI Feature Store (feature_table) |
| 추천 데이터 분석 | action_code 별 추천 수 (전 7일) |
| 고객 인사이트 분석 | BigQuery v_customer_summary |

### AI 모델 평가

| 용어 | 출처 |
|------|------|
| AI 예측 출현 분포 | DynamoDB dynamic_score 히스토그램 |
| 정밀도 (Precision) | Aurora model_performance_history · 추천 중 실제 클릭 비율 |

---

## 네트워크 (ops)

### AWS VPC (5개 카드)

| 카드명 | 주요 구성 |
|--------|-----------|
| AWS 플랫폼 VPC | Aurora, Redis, DynamoDB, Lambda, ALB |
| AWS 웨어러블 VPC | Kinesis Stream, Wearable EC2 |
| AWS 데이터 VPC | S3, Kinesis, Glue, EMR |
| AWS 그룹 VM VPC | BANK/CARD/SEC/INS/ONINS/HLT/HOS EC2 |
| AWS 관리 VPC | Admin EC2 (Windows Server 2022) |

### 연결 현황 · GCP · 온프레미스 (3개 카드)

| 카드명 | 주요 구성 |
|--------|-----------|
| AWS 연결 현황 | TGW, Site-to-Site VPN |
| GCP | BigQuery, Vertex AI, Cloud Run, PSC Endpoint |
| 온프레미스 (VirtualBox) | VirtualBox VM, Local MySQL, Tokenization, PrivateAPI |

### 웨어러블 실시간 (KPI 4개)

| 용어 | 설명 |
|------|------|
| 활성 기기 | 현재 데이터 송신 중인 기기 수 |
| 송신율 | 정상 송신 비율 |
| 건강 위험 (RED) | AHA/WHO 임상 임계 위반 건수 |
| 건강 주의 (YELLOW) | 경계 영역 건수 |

### 건강 이상 테이블 컬럼

심박(hr) · SpO2 · 스트레스 · global_id · 이름 · 시각 · 사유

---

## 약어 정의

| 약어 | 풀이 |
|------|------|
| CTR | Click-Through Rate (클릭률) |
| CVR | Conversion Rate (구매 전환율) |
| KPI | Key Performance Indicator (핵심 성과 지표) |
| DAU | Daily Active Users (일일 활성 사용자) |
| TGW | Transit Gateway |
| VPN | Virtual Private Network |
| SSE | Server-Sent Events |
| VPC | Virtual Private Cloud |
| ALB | Application Load Balancer |
| EMR | Elastic MapReduce |
