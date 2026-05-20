# LifeSync360 Aurora Service-DB 스키마 레퍼런스

- **DB 서버**: Amazon Aurora MySQL 8.x
- **스키마**: `lifesync360`
- **엔진**: MySQL 8.x, InnoDB, utf8mb4_unicode_ci
- **테이블 수**: 11개 (운영) + 2개 (시드 생성용)
- **기준 일자**: 2026-05-14

## 테이블 요약

| # | 테이블 | 적재량 | 비고 |
|---|---|---|---|
| 1 | company_master | 6 | 계열사 마스터 |
| 2 | category_master | 15 | 카테고리 마스터 |
| 3 | base_product_pool | 120 | 기준 상품 풀 |
| 4 | product_variant | 10 | 상품 변형 |
| 5 | product_master | 1,200 | 상품 마스터 (120 × 10) |
| 6 | product_option | ~3,000~5,000 | 상품 옵션 (상품당 3~6개) |
| 7 | recommend_rule | 47 | 추천 규칙 |
| 8 | cross_sell_rule | 53 | 교차판매 규칙 |
| 9 | campaign_master | ~110 | 캠페인 (10 기본 + 100 seed) |
| 10 | customer_recommend_history | **0 (운영 중 INSERT)** | 고객별 추천 이력 |
| 11 | customer_dashboard_log | **0 (운영 중 INSERT)** | 고객 행동 로그 |
| - | product_option_template | (시드 생성용) | product_option 생성 템플릿 |
| - | campaign_seed | (시드 생성용) | campaign_master 자동생성 시드 |

---

## 1. company_master (계열사 마스터)

> 6건

| 컬럼 | 타입 | 비고 |
|---|---|---|
| company_id | BIGINT PK | AUTO_INCREMENT |
| company_code | VARCHAR(30) UNIQUE | 식별자 |
| company_name | VARCHAR(100) | 표시명 |
| company_type | VARCHAR(30) | 분류 |
| active_flag | CHAR(1) | `Y`/`N` |

**적재 값**:

| company_code | company_name | company_type |
|---|---|---|
| BANK | LifeSync Bank | BANK |
| CARD | LifeSync Card | CARD |
| SEC | LifeSync Securities | SEC |
| INS | LifeSync Insurance | INSURANCE |
| ONINS | LifeSync Direct Insurance | ONLINE_INS |
| HLT | LifeSync Healthcare | HEALTHCARE |

> ⚠️ **온프레 consent.domain 값(BANK/CARD/INSURANCE/INTERNET_INSURANCE/HOSPITAL/HEALTHCARE/STOCK/WEARABLE)과 매핑 불일치** — Aurora는 `SEC/INS/ONINS/HLT` 약자, 온프레는 풀텍스트. 매핑 변환 필요.

---

## 2. category_master (카테고리)

> 15건

| 카테고리 코드 | 한글명 | 주요 계열사 |
|---|---|---|
| DEPOSIT | 예금 | BANK |
| SAVING | 적금 | BANK |
| LOAN | 대출 | BANK |
| PENSION | 연금/IRP | BANK, INS, SEC |
| CARD | 카드 | CARD |
| POINT | 포인트/리워드 | CARD, HLT |
| LIFESTYLE | 생활혜택 | CARD |
| ETF | ETF | SEC |
| FUND | 펀드 | SEC |
| WM | 자산관리 | SEC |
| INSURANCE | 보험 | INS |
| DIRECT_INS | 온라인보험 | ONINS |
| HEALTHCARE | 헬스케어 | HLT |
| WELLNESS | 건강관리/웰니스 | HLT |
| TELEMED | 화상진료/건강상담 | HLT |

---

## 3. base_product_pool (기준 상품 풀)

> 120건 — 계열사 × 20 (BANK 20 / CARD 20 / SEC 20 / INS 20 / ONINS 20 / HLT 20)

| 컬럼 | 타입 | 비고 |
|---|---|---|
| base_product_id | BIGINT PK | AUTO_INCREMENT |
| company_code | VARCHAR(30) | FK 개념 |
| category_code | VARCHAR(30) | FK 개념 |
| base_product_name | VARCHAR(200) | 'PB 프리미엄 정기예금' 등 |
| base_grade | VARCHAR(20) | VIP/GOLD/SILVER/BASIC/CARE |
| base_min_score | DECIMAL(8,2) | 0/60/70/80/90 |
| base_max_score | DECIMAL(8,2) | 100 |
| base_risk_level | VARCHAR(20) | LOW/MID/HIGH |
| product_theme | VARCHAR(100) | 'PB/프리미엄 예금' 등 |

---

## 4. product_variant (상품 변형)

> 10건

| variant_code | variant_name | score_bonus | priority_bonus | 설명 |
|---|---|---|---|---|
| STANDARD | Standard | 0 | 0 | 기본형 |
| PREMIUM | Premium | 5 | -1 | 프리미엄 고객 대상 |
| VIP | VIP 전용 | 10 | -3 | VIP 고객 전용 |
| AI | AI 추천형 | 3 | -2 | AI 추천 우선 |
| YOUTH | 청년 특화형 | 0 | 1 | 청년/신규 고객 |
| SENIOR | 시니어 특화형 | 0 | 1 | 시니어 고객 |
| FAMILY | 가족 결합형 | 0 | 1 | 가족 단위 |
| WELLNESS | 웰니스 연계형 | 2 | -1 | 건강관리 연계 |
| ESG | ESG 특화형 | 2 | 0 | ESG/친환경 |
| 2026 | 2026 Edition | 1 | 0 | 2026 캠페인 |

---

## 5. product_master (상품 마스터)

> 1,200건 — `120 base × 10 variant`

`product_code` 패턴: `{company_code}-{category_code}-{base_id 5자리}-{variant_id 2자리}` (예: `BANK-DEPOSIT-00001-01`)

| 컬럼 | 타입 | 생성 규칙 |
|---|---|---|
| product_id | BIGINT PK | AUTO_INCREMENT |
| company_id | BIGINT FK | company_master |
| category_id | BIGINT FK | category_master |
| product_code | VARCHAR(50) UNIQUE | 위 패턴 |
| product_name | VARCHAR(200) | base_product_name + variant_name (STANDARD는 base만) |
| description | TEXT | 자동 생성 |
| target_grade | VARCHAR(20) | (아래 규칙) |
| min_score | DECIMAL(8,2) | base_min_score + variant.score_bonus (VIP는 90 고정) |
| max_score | DECIMAL(8,2) | 100 |
| risk_level | VARCHAR(20) | LOW/MID/HIGH (SEC AI/ESG는 HIGH 강제) |
| priority_rank | INT | 1~20 |
| active_flag | CHAR(1) | `Y` |
| start_date | DATE | CURDATE() |
| end_date | DATE | CURDATE() + 365일 |

**target_grade 결정 로직**:
- variant=VIP → `VIP`
- variant=PREMIUM AND base in (GOLD,SILVER) → `GOLD`
- variant=YOUTH → `BASIC`
- variant=SENIOR → `SILVER`
- variant=WELLNESS AND company in (HLT,INS,ONINS) → `CARE`
- else → base_grade

---

## 6. product_option (상품 옵션)

> 상품당 3~6개 옵션 — 계열사/카테고리별 템플릿 적용

| 컬럼 | 타입 |
|---|---|
| option_id | BIGINT PK |
| product_id | BIGINT FK → product_master |
| option_name | VARCHAR(100) |
| option_value | VARCHAR(300) |

**옵션 종류 (계열사·카테고리별)**:

| 계열사/카테고리 | option_name |
|---|---|
| BANK/DEPOSIT | interest_rate, min_deposit_amount, term_month, preferential_condition |
| BANK/SAVING | interest_rate, monthly_limit, term_month, auto_transfer_required |
| BANK/LOAN | loan_limit, loan_rate, repayment_type, credit_score_required |
| CARD/CARD | annual_fee, cashback_rate, mileage_rate, main_benefit |
| CARD/POINT, LIFESTYLE | point_rate, point_brand, discount_rate, benefit_category |
| SEC/ETF, FUND, WM | expected_return, volatility, investment_region, asset_type, risk_grade, fund_type, advisor_type |
| INS/INSURANCE, PENSION | monthly_premium, coverage_type, coverage_amount, join_age_range, pension_start_age, tax_benefit |
| ONINS/DIRECT_INS | monthly_premium, mobile_join, simple_underwriting, coverage_period |
| HLT/HEALTHCARE | service_channel, health_sync, checkup_type, ai_report |
| HLT/WELLNESS | coaching_cycle, service_channel, wearable_sync, reward_point |
| HLT/TELEMED | consulting_type, service_channel, reservation_required |

option_value는 RAND 기반 자동 생성 (interest_rate=2.5~5%, annual_fee=10000~200000 KRW 등).

---

## 7. recommend_rule (추천 규칙)

> 47건 (29 기본 + 18 확장)

| 컬럼 | 타입 |
|---|---|
| rule_id | BIGINT PK |
| target_grade | VARCHAR(20) |
| action_code | VARCHAR(50) |
| min_score | DECIMAL(8,2) |
| max_score | DECIMAL(8,2) |
| vip_required | CHAR(1) |
| health_min_score | DECIMAL(8,2) NULL |
| category_code | VARCHAR(30) |
| priority_rank | INT |
| active_flag | CHAR(1) |

**등급별 추천 카테고리 (요약)**:

| 등급 | 점수 | 우선 추천 카테고리 |
|---|---|---|
| VIP | 90~100 | DEPOSIT, WM, ETF, INSURANCE, CARD, HEALTHCARE, PENSION, GLOBAL_INV |
| GOLD | 80~100 | ETF, FUND, WM, CARD, INSURANCE, HEALTHCARE, DEPOSIT, PENSION, POINT |
| SILVER | 70~100 | SAVING, CARD, LIFESTYLE, FUND, INSURANCE, WELLNESS, DEPOSIT, PENSION, POINT, DIRECT_INS |
| BASIC | 60~100 | SAVING, CARD, LIFESTYLE, DIRECT_INS, LOAN, WELLNESS, DEPOSIT, POINT |
| CARE | 0~100 | HEALTHCARE, WELLNESS, TELEMED, INSURANCE, DIRECT_INS |

**action_code 종류**: RECOMMEND_PB, RECOMMEND_WM, RECOMMEND_INVEST, RECOMMEND_INSURANCE, RECOMMEND_CARD, RECOMMEND_HEALTH, RECOMMEND_SAVING, RECOMMEND_HEALTH_INS, RECOMMEND_PENSION, RECOMMEND_GLOBAL_INV, RECOMMEND_LOAN, RECOMMEND_DIRECT_INS, RECOMMEND_WELLNESS, RECOMMEND_TELEMED, RECOMMEND_MOBILE_INS, RECOMMEND_MOBILE_CARE

**health_min_score**가 있는 규칙은 건강점수 기준 충족 시에만 매칭 (예: VIP HEALTHCARE 70점 이상).

---

## 8. cross_sell_rule (교차판매 규칙)

> 53건

| 컬럼 | 타입 |
|---|---|
| cross_id | BIGINT PK |
| base_category | VARCHAR(30) |
| target_category | VARCHAR(30) |
| priority_rank | INT |
| active_flag | CHAR(1) |

**연관 흐름**:
- `HEALTHCARE`/`WELLNESS`/`TELEMED` → `INSURANCE`/`DIRECT_INS`
- `INSURANCE`/`DIRECT_INS` → `HEALTHCARE`/`WELLNESS`
- `DEPOSIT`/`SAVING` → `CARD`/`FUND`/`ETF`/`PENSION`
- `LOAN` → `INSURANCE`/`CARD`/`DIRECT_INS`
- `PENSION` → `INSURANCE`/`HEALTHCARE`/`WM`
- `CARD` → `DIRECT_INS`/`INSURANCE`/`LIFESTYLE`/`POINT`
- `POINT`/`LIFESTYLE` → 서로 교차
- `ETF`/`FUND` → `PENSION`/`WM`/`INSURANCE`
- `WM` → `INSURANCE`/`HEALTHCARE`/`PENSION`

---

## 9. campaign_master (캠페인)

> ~110건 (10 기본 + 100 seed 자동생성)

| 컬럼 | 타입 |
|---|---|
| campaign_id | BIGINT PK |
| campaign_name | VARCHAR(200) |
| target_grade | VARCHAR(20) |
| banner_title | VARCHAR(300) |
| banner_desc | TEXT |
| start_date | DATE |
| end_date | DATE |
| active_flag | CHAR(1) |

**등급별 캠페인 테마**:

| 등급 | 테마 |
|---|---|
| VIP | 프리미엄 자산관리, VIP 라이프케어, 상속/절세 설계 |
| GOLD | 글로벌 투자, 프리미엄 카드혜택, 프리미엄 건강보장 |
| SILVER | 생활금융 혜택, 건강보장 시작, 목적자금 만들기 |
| BASIC | 금융 시작, 생활비 절약, 간편보험 시작 |
| CARE | AI 건강관리, 웰니스 보험연계, 비대면 건강상담 |

---

## 10. customer_recommend_history (고객 추천 이력) — **시드 없음**

> 0건. 운영 중 platform `/api/recommendations` 호출 시 INSERT 누적.

| 컬럼 | 타입 | 출처 |
|---|---|---|
| hist_id | BIGINT PK | AUTO_INCREMENT |
| global_id | VARCHAR(50) | onprem master_customer.global_id |
| product_id | BIGINT FK | product_master |
| dynamic_score | DECIMAL(8,2) | DynamoDB |
| dynamic_grade | VARCHAR(20) | DynamoDB |
| action_code | VARCHAR(50) | platform 코드에서 부여 |
| recommended_at | DATETIME | NOW() |
| clicked_flag | CHAR(1) DEFAULT 'N' | 클릭 이벤트 시 업데이트 필요 |
| purchased_flag | CHAR(1) DEFAULT 'N' | 구매 이벤트 시 업데이트 필요 |

**현재 코드 동작**:
- `/api/recommendations` 호출 시 추천된 상품들 INSERT (`clicked_flag='N'`, `purchased_flag='N'`)
- 클릭/구매 이벤트 추적은 별도 UPDATE 코드 필요 (현재 미구현)

> ⚠️ 추천이 누적되어야 어드민 "최근 추천", "추천 funnel", "유저별 추천이력"이 표시됨.

---

## 11. customer_dashboard_log (고객 행동 로그) — **시드 없음**

> 0건. 운영 중 platform `/api/event` 호출 시 INSERT 누적.

| 컬럼 | 타입 |
|---|---|
| log_id | BIGINT PK |
| global_id | VARCHAR(50) |
| page_type | VARCHAR(30) DEFAULT 'MAIN' |
| banner_click | CHAR(1) DEFAULT 'N' |
| product_click | CHAR(1) DEFAULT 'N' |
| click_product_id | BIGINT NULL |
| session_id | VARCHAR(100) |
| view_time | DATETIME |

> ⚠️ 이벤트가 누적되어야 어드민 "행동 현황", "탭 클릭", "상품 조회 TOP" 등이 표시됨.

---

## 인덱스

- `product_master`: target_grade / (min_score, max_score) / active_flag / priority_rank
- `customer_recommend_history`: global_id / recommended_at
- `customer_dashboard_log`: global_id / view_time
- `recommend_rule`: target_grade / action_code

---

## 데이터 흐름

```
[Aurora 시드 1~9.sql] → 정적 마스터/규칙/캠페인 (1회 적재)

[고객 행동]
   ├─ /api/recommendations → customer_recommend_history INSERT (dynamic_grade/score는 DynamoDB)
   └─ /api/event           → customer_dashboard_log INSERT

[어드민 조회]
   ├─ overview     → product_master, campaign_master 집계 + (recommend_history 누적 시 funnel)
   ├─ user_detail  → customer_recommend_history WHERE global_id
   └─ users 목록   → DynamoDB scan (Aurora 직접 X)
```

---

## 현재 비어있는 데이터 (운영 누적 필요)

| 테이블 | 채워지는 조건 |
|---|---|
| `customer_recommend_history` | platform `/api/recommendations` 호출 시 자동 누적 |
| `customer_dashboard_log` | platform `/api/event` 호출 시 자동 누적 |
| `clicked_flag` / `purchased_flag` | 클릭/구매 이벤트 UPDATE 코드 별도 구현 필요 |

→ 시연 시 위 이벤트를 일부 호출해야 어드민 화면에 데이터 나타남. 또는 시드 INSERT 스크립트 별도 작성.

---

## 시드 생성용 보조 테이블 (참고)

| 테이블 | 용도 |
|---|---|
| `product_option_template` | `5.product_option.sql` 실행 시 옵션 자동 생성 템플릿 |
| `campaign_seed` | `8.campaign_master.sql` 실행 시 캠페인 100건 자동 생성 시드 |

---

## 정합성 메모

### Aurora `company_code` ↔ 온프레 `consent.domain` 매핑

**상품/추천 매핑 대상** (어드민 funnel 등에서 변환 필요):

| Aurora company_code | 온프레 consent.domain |
|---|---|
| BANK | BANK ✅ |
| CARD | CARD ✅ |
| SEC | STOCK ⚠️ |
| INS | INSURANCE ⚠️ |
| ONINS | INTERNET_INSURANCE ⚠️ |
| HLT | HEALTHCARE ⚠️ |

**분석용 도메인** (동의 테이블에만 존재, Aurora 상품/추천 매핑 없음 — 의도된 설계):

| 온프레 consent.domain | 용도 |
|---|---|
| HOSPITAL | 분석용 (병원 데이터 활용 동의) |
| WEARABLE | 분석용 (웨어러블 데이터 활용 동의) |

→ 이 두 도메인은 어드민/플랫폼의 상품 매핑 로직에서는 무시 (consent 화면, 분석 파이프라인 입력으로만 사용)

### 기타
- **DynamoDB `dynamic_grade` ↔ Aurora `target_grade`**: 동일 값 사용 (`VIP/GOLD/SILVER/BASIC/CARE`)
- **Aurora `min_score`/`max_score`** ↔ DynamoDB `dynamic_score`: 추천 시 매칭 (`score BETWEEN min AND max`)
