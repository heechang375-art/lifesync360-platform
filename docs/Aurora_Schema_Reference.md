# LifeSync360 Aurora MySQL 스키마 레퍼런스

- **DB 서버**: AWS Aurora MySQL 8.x
- **스키마**: `lifesync360`
- **엔진**: InnoDB, utf8mb4_unicode_ci
- **테이블 수**: 10개 (마스터 7 + 운영 2 + 보조 1)
- **기준 일자**: 2026-05-17

---

## 📊 테이블 분류

### 마스터 데이터 (정적, 운영 중 거의 변경 없음)
1. company_master — 회사 마스터 (계열사 정보)
2. category_master — 카테고리 마스터 (상품 카테고리)
3. base_product_pool — 기준 상품 후보 (120개)
4. product_variant — 상품 Variant (10종)
5. product_master — 상품 마스터 (10,000개, base × variant 조합)
6. product_option — 상품 옵션
7. product_option_template — 상품 옵션 표준 코드

### 추천/캠페인 룰 데이터
8. recommend_rule — 추천 규칙 (등급별 액션 매핑)
9. cross_sell_rule — 교차판매 규칙 (카테고리간)
10. campaign_master — 캠페인 마스터 (배너/프로모션)

### 운영 데이터 (동적, 매일 증가)
11. customer_recommend_history — 고객 추천 이력
12. customer_dashboard_log — 고객 행동 로그

---

## 1. company_master (회사 마스터)

> 계열사 정보. 약 7개 사.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| company_id | BIGINT PK | 회사 일련번호 | AUTO_INCREMENT |
| company_code | VARCHAR(30) UNIQUE | 회사 코드 | `BANK` / `CARD` / `SEC` / `INS` / `ONINS` / `HLT` / `HEALTHCARE` |
| company_name | VARCHAR(100) | 회사명 | `LifeSync Bank` 등 |
| company_type | VARCHAR(30) | 회사 타입 | `BANK` / `CARD` / `SEC` / `INSURANCE` / `ONLINE_INS` / `HLT` / `HEALTHCARE` |
| active_flag | CHAR(1) | 활성 여부 | `Y` / `N` (기본 Y) |
| created_at | DATETIME | 생성일시 | DEFAULT CURRENT_TIMESTAMP |
| updated_at | DATETIME | 갱신일시 | ON UPDATE CURRENT_TIMESTAMP |

**계열사 코드 매핑** (On-Prem `consent.domain` 과 통일):
- `BANK` (은행), `CARD` (카드), `SEC` (증권), `INS` (보험), `ONINS` (온라인보험)
- `HLT` / `HEALTHCARE` (헬스케어)

---

## 2. category_master (카테고리 마스터)

> 상품 카테고리. 15종.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| category_id | BIGINT PK | 카테고리 일련번호 | AUTO_INCREMENT |
| category_code | VARCHAR(30) UNIQUE | 카테고리 코드 | 아래 15종 |
| category_name | VARCHAR(100) | 카테고리명 | 한글명 |
| active_flag | CHAR(1) | 활성 여부 | `Y` / `N` |
| created_at | DATETIME | 생성일시 | DEFAULT CURRENT_TIMESTAMP |

**카테고리 15종**:

| 카테고리 코드 | 카테고리명 |
|---|---|
| DEPOSIT | 예금 |
| SAVING | 적금 |
| LOAN | 대출 |
| PENSION | 연금/IRP |
| CARD | 카드 |
| POINT | 포인트/리워드 |
| LIFESTYLE | 생활혜택 |
| ETF | ETF |
| FUND | 펀드 |
| WM | 자산관리 |
| INSURANCE | 보험 |
| DIRECT_INS | 온라인보험 |
| HEALTHCARE | 헬스케어 |
| WELLNESS | 건강관리/웰니스 |
| TELEMED | 화상진료/건강상담 |

---

## 3. base_product_pool (기준 상품 후보)

> 실제 금융상품 레퍼런스 기반 120개 기준 상품. product_master 생성의 베이스.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| base_product_id | BIGINT PK | 기준 상품 일련번호 | AUTO_INCREMENT |
| company_code | VARCHAR(30) | 회사 코드 | FK 아님 (참조용) |
| category_code | VARCHAR(30) | 카테고리 코드 | FK 아님 (참조용) |
| base_product_name | VARCHAR(200) | 기준 상품명 | `PB 프리미엄 정기예금` 등 |
| base_description | TEXT | 상품 상세 설명 | 실제 금융상품 레퍼런스 |
| base_grade | VARCHAR(20) | 기준 등급 | `BASIC` / `SILVER` / `GOLD` / `VIP` |
| base_min_score | DECIMAL(8,2) | 최소 점수 | 0~100 |
| base_max_score | DECIMAL(8,2) | 최대 점수 | 0~100 |
| base_risk_level | VARCHAR(20) | 위험 등급 | `LOW` / `MID` / `HIGH` |
| product_theme | VARCHAR(100) | 상품 테마 | `PB/프리미엄 예금` 등 |
| active_flag | CHAR(1) | 활성 여부 | `Y` / `N` |
| created_at | DATETIME | 생성일시 | DEFAULT CURRENT_TIMESTAMP |

---

## 4. product_variant (상품 Variant)

> 기준 상품을 확장하는 Variant. 10종.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| variant_id | BIGINT PK | Variant 일련번호 | AUTO_INCREMENT |
| variant_code | VARCHAR(30) | Variant 코드 | 아래 10종 |
| variant_name | VARCHAR(100) | Variant명 | |
| variant_desc | VARCHAR(300) | Variant 설명 | |
| score_bonus | DECIMAL(8,2) | 점수 가산 | DEFAULT 0 |
| priority_bonus | INT | 우선순위 가산 | DEFAULT 0 |
| active_flag | CHAR(1) | 활성 여부 | `Y` / `N` |
| created_at | DATETIME | 생성일시 | DEFAULT CURRENT_TIMESTAMP |

**Variant 10종**:

| 코드 | 이름 | 설명 |
|---|---|---|
| STANDARD | Standard | 기본형 |
| PREMIUM | Premium | 프리미엄 고객 대상 (score +5, priority -1) |
| VIP | VIP 전용 | VIP 고객 전용 (score +10, priority -3) |
| AI | AI 추천형 | AI 추천 우선 (score +3, priority -2) |
| YOUTH | 청년 특화형 | 청년/신규 고객 |
| SENIOR | 시니어 특화형 | 시니어 고객 |
| FAMILY | 가족 결합형 | 가족 단위 고객 |
| WELLNESS | 웰니스 연계형 | 건강관리 연계 |
| ESG | ESG 특화형 | ESG/친환경 |
| 2026 | 2026 Edition | 2026년 캠페인 |

---

## 5. product_master (상품 마스터)

> **base_product_pool × product_variant 조합으로 생성된 10,000개 상품**.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| product_id | BIGINT PK | 상품 일련번호 | AUTO_INCREMENT |
| company_id | BIGINT FK | 회사 ID | → company_master |
| category_id | BIGINT FK | 카테고리 ID | → category_master |
| product_code | VARCHAR(50) UNIQUE | 상품 코드 | `BANK-DEPOSIT-00001-VIP` 형식 |
| product_name | VARCHAR(200) | 상품명 | |
| description | TEXT | 상품 설명 | |
| target_grade | VARCHAR(20) | 대상 등급 | `BASIC` / `SILVER` / `GOLD` / `VIP` |
| min_score | DECIMAL(8,2) | 최소 점수 | 0~100 |
| max_score | DECIMAL(8,2) | 최대 점수 | 0~100 |
| risk_level | VARCHAR(20) | 위험 등급 | `LOW` / `MID` / `HIGH` |
| priority_rank | INT | 우선순위 | DEFAULT 100 (낮을수록 우선) |
| active_flag | CHAR(1) | 활성 여부 | `Y` / `N` |
| start_date | DATE | 시작일 | |
| end_date | DATE | 종료일 | |
| created_at | DATETIME | 생성일시 | DEFAULT CURRENT_TIMESTAMP |
| updated_at | DATETIME | 갱신일시 | ON UPDATE CURRENT_TIMESTAMP |

**인덱스**:
- `idx_product_grade (target_grade)`
- `idx_product_score (min_score, max_score)`
- `idx_product_active (active_flag)`
- `idx_product_priority (priority_rank)`

---

## 6. product_option (상품 옵션)

> 상품별 세부 옵션 (금리, 한도, 기간 등).

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| option_id | BIGINT PK | 옵션 일련번호 | AUTO_INCREMENT |
| product_id | BIGINT FK | 상품 ID | → product_master |
| option_name | VARCHAR(100) | 옵션명 | `interest_rate` / `term_month` 등 |
| option_value | VARCHAR(300) | 옵션 값 | |
| created_at | DATETIME | 생성일시 | DEFAULT CURRENT_TIMESTAMP |

---

## 7. product_option_template (옵션 표준 코드)

> 회사/카테고리별 옵션 표준 정의.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| template_id | BIGINT PK | 템플릿 일련번호 | AUTO_INCREMENT |
| company_code | VARCHAR(30) | 회사 코드 | |
| category_code | VARCHAR(30) | 카테고리 코드 | |
| option_name | VARCHAR(100) | 옵션명 | `interest_rate` 등 |
| option_desc | VARCHAR(300) | 옵션 설명 | `예금 금리` 등 |
| active_flag | CHAR(1) | 활성 여부 | `Y` / `N` |
| created_at | DATETIME | 생성일시 | DEFAULT CURRENT_TIMESTAMP |

---

## 8. recommend_rule (추천 규칙)

> 고객 등급 + 점수 + 카테고리 조합으로 추천 액션 매핑.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| rule_id | BIGINT PK | 규칙 일련번호 | AUTO_INCREMENT |
| target_grade | VARCHAR(20) | 대상 등급 | `BASIC` / `SILVER` / `GOLD` / `VIP` |
| action_code | VARCHAR(50) | 액션 코드 | 아래 17종 |
| min_score | DECIMAL(8,2) | 최소 점수 | |
| max_score | DECIMAL(8,2) | 최대 점수 | |
| vip_required | CHAR(1) | VIP 필수 여부 | `Y` / `N` |
| health_min_score | DECIMAL(8,2) | 건강 최소 점수 | NULL 가능 |
| category_code | VARCHAR(30) | 카테고리 코드 | |
| priority_rank | INT | 우선순위 | DEFAULT 1 |
| active_flag | CHAR(1) | 활성 여부 | `Y` / `N` |
| created_at | DATETIME | 생성일시 | DEFAULT CURRENT_TIMESTAMP |

**action_code 17종**:

| 액션 코드 | 의미 |
|---|---|
| RECOMMEND_PB | PB 상담 추천 |
| RECOMMEND_WM | 자산관리 추천 |
| RECOMMEND_INVEST | 투자 추천 |
| RECOMMEND_INSURANCE | 보험 추천 |
| RECOMMEND_CARD | 카드 추천 |
| RECOMMEND_HEALTH | 건강검진 추천 |
| RECOMMEND_DIRECT_INS | 온라인보험 추천 |
| RECOMMEND_HEALTH_INS | 건강보험 추천 |
| RECOMMEND_FUND | 펀드 추천 |
| RECOMMEND_GLOBAL_INV | 글로벌 투자 추천 |
| RECOMMEND_LOAN | 대출 추천 |
| RECOMMEND_MOBILE_CARE | 모바일 케어 추천 |
| RECOMMEND_MOBILE_INS | 모바일 보험 추천 |
| RECOMMEND_PENSION | 연금 추천 |
| RECOMMEND_SAVING | 적금 추천 |
| RECOMMEND_TELEMED | 화상진료 추천 |
| RECOMMEND_WELLNESS | 웰니스 추천 |

**인덱스**:
- `idx_rule_grade (target_grade)`
- `idx_rule_action (action_code)`

---

## 9. cross_sell_rule (교차판매 규칙)

> 카테고리간 교차판매 매핑 (base → target).

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| cross_id | BIGINT PK | 교차판매 일련번호 | AUTO_INCREMENT |
| base_category | VARCHAR(30) | 현재 관심 카테고리 | |
| target_category | VARCHAR(30) | 추천 카테고리 | |
| priority_rank | INT | 우선순위 | DEFAULT 1 |
| active_flag | CHAR(1) | 활성 여부 | `Y` / `N` |
| created_at | DATETIME | 생성일시 | DEFAULT CURRENT_TIMESTAMP |

**예시 룰**:
- HEALTHCARE → INSURANCE / DIRECT_INS / WELLNESS
- WELLNESS → INSURANCE / DIRECT_INS / HEALTHCARE

---

## 10. campaign_master (캠페인 마스터)

> 등급별 캠페인 배너/프로모션.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| campaign_id | BIGINT PK | 캠페인 일련번호 | AUTO_INCREMENT |
| campaign_name | VARCHAR(200) | 캠페인명 | |
| target_grade | VARCHAR(20) | 대상 등급 | `BASIC` / `SILVER` / `GOLD` / `VIP` |
| banner_title | VARCHAR(300) | 배너 제목 | |
| banner_desc | TEXT | 배너 설명 | |
| start_date | DATE | 시작일 | |
| end_date | DATE | 종료일 | |
| active_flag | CHAR(1) | 활성 여부 | `Y` / `N` |
| created_at | DATETIME | 생성일시 | DEFAULT CURRENT_TIMESTAMP |

---

## 11. customer_recommend_history (고객 추천 이력)

> **운영 데이터**. 매일 증가. 추천 → 클릭 → 구매 라이프사이클.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| hist_id | BIGINT PK | 이력 일련번호 | AUTO_INCREMENT |
| global_id | VARCHAR(50) | 통합 고객키 | On-Prem master_customer 참조 (FK 아님) |
| product_id | BIGINT FK | 상품 ID | → product_master |
| dynamic_score | DECIMAL(8,2) | AI 점수 | Vertex AI 산출 |
| dynamic_grade | VARCHAR(20) | AI 등급 | `BASIC` / `CARE` / `SILVER` / `GOLD` / `VIP` |
| action_code | VARCHAR(50) | 액션 코드 | recommend_rule의 action_code |
| recommended_at | DATETIME | 추천일시 | DEFAULT CURRENT_TIMESTAMP |
| clicked_flag | CHAR(1) | 클릭 여부 | `Y` / `N` (DEFAULT N) |
| purchased_flag | CHAR(1) | 구매 여부 | `Y` / `N` (DEFAULT N) |

**인덱스**:
- `idx_hist_global (global_id)`
- `idx_hist_date (recommended_at)`

**핵심 패턴**:
```sql
-- 고객별 최근 추천 이력
WHERE global_id=? ORDER BY recommended_at DESC LIMIT N

-- CTR 계산
SUM(clicked_flag='Y') / COUNT(*)

-- CVR 계산
SUM(purchased_flag='Y') / SUM(clicked_flag='Y')

-- 상품 TOP10
GROUP BY product_id ORDER BY COUNT(*) DESC LIMIT 10

-- 일별 추이
GROUP BY DATE(recommended_at)
```

---

## 12. customer_dashboard_log (고객 행동 로그)

> **운영 데이터**. 매일 증가. 배너/상품 클릭, 세션.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| log_id | BIGINT PK | 로그 일련번호 | AUTO_INCREMENT |
| global_id | VARCHAR(50) | 통합 고객키 | |
| page_type | VARCHAR(30) | 페이지 타입 | DEFAULT `MAIN` |
| banner_click | CHAR(1) | 배너 클릭 여부 | `Y` / `N` (DEFAULT N) |
| product_click | CHAR(1) | 상품 클릭 여부 | `Y` / `N` (DEFAULT N) |
| click_product_id | BIGINT | 클릭한 상품 ID | NULL 가능 |
| session_id | VARCHAR(100) | 세션 ID | |
| view_time | DATETIME | 조회 시각 | DEFAULT CURRENT_TIMESTAMP |

**인덱스**:
- `idx_log_global (global_id)`
- `idx_log_viewtime (view_time)`

**핵심 패턴**:
```sql
-- 고객별 최근 행동 로그
WHERE global_id=? ORDER BY view_time DESC LIMIT N

-- 채널별 CTR (recommend_history.clicked_flag + dashboard_log.banner_click/product_click)
SELECT page_type, 
       SUM(banner_click='Y') AS banner_clicks,
       SUM(product_click='Y') AS product_clicks
FROM customer_dashboard_log
GROUP BY page_type
```

---

## 🔑 외래키 관계도

```
company_master ─┐
                ├─> product_master ─┬─> product_option
category_master ┘                  │
                                   └─> customer_recommend_history
                                                  │
                                                  │ global_id (FK 아님)
                                                  ▼
                                       [On-Prem master_customer]

customer_dashboard_log
  └─ click_product_id (FK 아님, NULL 가능)
```

---

## 📐 데이터 양 추정

| 테이블 | 건수 | 비고 |
|---|---|---|
| company_master | 7 | 계열사 7개 |
| category_master | 15 | 카테고리 15종 |
| base_product_pool | 120 | 기준 상품 |
| product_variant | 10 | Variant 10종 |
| product_master | **10,000** | 120 base × ~83 variant = 약 10,000 |
| product_option | 다수 | 상품별 옵션 |
| product_option_template | 다수 | 회사/카테고리 × 옵션명 |
| recommend_rule | 약 30~50 | 등급별 액션 매핑 |
| cross_sell_rule | 약 30 | 카테고리간 매핑 |
| campaign_master | 약 20 | 등급별 캠페인 |
| customer_recommend_history | **1,000,000+** | 누적 (분석 대상 60,000명 대상) |
| customer_dashboard_log | **10,000,000+** | 누적 행동 로그 |

---

## 🔗 다른 시스템과의 연관

### On-Prem (lifesync_onprem)
- `global_id`로 연결됨 (FK 아님, Aurora는 token_id 안 받고 직접 global_id 사용)
- On-Prem `master_customer` ↔ Aurora `customer_recommend_history.global_id`

### AWS DynamoDB
- `lifesync_customer_result`의 `dynamic_grade` ↔ Aurora `customer_recommend_history.dynamic_grade`
- Vertex AI 산출 결과가 Aurora에도 ML 출력으로 일부 저장됨

### AWS Redis (ElastiCache)
- `rec:{global_id}` 캐시 miss 시 Aurora `customer_recommend_history`로 fallback

### GCP BigQuery
- Aurora 데이터 → Glue/S3 → BigQuery sync (운영 시 일별 배치)
- BigQuery `lifesync_curated.recommendation_mart`는 EMR이 별도 생성

---

## 🛠 운영 스크립트

| 파일 | 용도 |
|---|---|
| `Aurora_MySQL_DB_Create.sql` | 전체 스키마 생성 |
| `1.company_master.sql` ~ `8.campaign_master.sql` | 마스터 데이터 INSERT |
| `lifesync360-data.sh` | 전체 데이터 적재 실행 |
| `service-db-execution.sh` | 서비스 DB 구축 실행 |
| `service-db-destory.sh` | DB 초기화 |
| `test/test.py` | 데이터 검증 |
| `config/db.env` | DB 접속 정보 |
