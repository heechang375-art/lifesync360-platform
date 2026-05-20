# UI 데이터 조합 분석 — 그룹데이터 통합 인프라 관점

> **프로젝트 정체성**: 계열사 데이터 통합 + PII 분리 + 동의 거버넌스 + 통합 분석/AI 추천 인프라
> **기준 DB**: schema_reference.md (온프레 8 테이블) + service_db_reference.md (Aurora 11 테이블) + DynamoDB (`lifesync_customer_result`)
> **분석 일자**: 2026-05-14

---

# A. 현재 DB만으로 가능한 데이터 조합

## A-1. 어드민 (그룹데이터 관리자)

> **분류 기준**: 일상 운영용(매일 확인) → 가끔 확인 → 마케팅/분석가 영역(거의 미사용)
> 그룹데이터 통합 인프라 관리자 기준 — 마케팅성 인구통계/추천 funnel은 별도 분석 도구 영역.

### [일상 운영] A-1-1. 데이터 정합 / 적재 현황 대시보드
| 보여줄 메트릭 | 데이터 출처 |
|---|---|
| 5개 핵심 테이블 row 수 + 일관성 (1M 매칭) | `users` + `master_customer` + `customer_pii_secure` + `customer_360_profile` count 비교 |
| 도메인별 동의 적재량 | `consent` GROUP BY domain (8 × 1M = 8M 기대) |
| 도메인별 ID 매핑 분포 | `customer_identity_map` GROUP BY domain |
| token_map 발급 비율 | `token_map` count / `master_customer` count |
| 누락 row 식별 | LEFT JOIN으로 master 있는데 다른 테이블 없는 case |

### [일상 운영] A-1-2. 계열사 ID 매칭 품질
| 보여줄 메트릭 | 데이터 출처 |
|---|---|
| 매칭 방식 분포 (EXACT vs FUZZY) | `customer_identity_map.match_type` GROUP BY |
| 한 global_id당 평균 연동 도메인 수 | `customer_identity_map` GROUP BY global_id → AVG |
| 도메인별 매칭 커버리지 (BANK/CARD/SEC/INS/ONINS/HLT) | `customer_identity_map` WHERE domain |
| 활성 vs 비활성 매핑 비율 | `active_flag` GROUP BY |
| 매칭 시도 이력 (성공/실패) | `matching_audit_log.result` (MATCH/NO_MATCH) |
| 매칭 규칙별 점수 분포 | `matching_audit_log.match_rule` + `match_score` |
| 최근 매칭 요청 타임라인 | `matching_audit_log.request_dt` |

### [일상 운영] A-1-3. 동의 거버넌스
| 보여줄 메트릭 | 데이터 출처 |
|---|---|
| 도메인별 활성 동의율 (8 × 1M 기준) | `consent` WHERE `consent_flag='Y'` GROUP BY domain |
| 도메인별 철회율 | `consent` WHERE `revoke_dt IS NOT NULL` GROUP BY domain |
| 미동의 비율 (한 번도 동의 안 함) | `consent` WHERE `consent_flag='N' AND consent_dt IS NULL` |
| 동의 추이 (월별 누적) | `consent.consent_dt` 일별/월별 GROUP BY |
| 철회 추이 | `consent.revoke_dt` 동일 |
| 동의 버전 분포 | `consent.consent_version` GROUP BY |
| 도메인별 평균 동의 보유 수 (1인당) | `consent` GROUP BY global_id |

### [일상 운영] A-1-4. PII 보호 현황
| 보여줄 메트릭 | 데이터 출처 |
|---|---|
| PII 컬럼별 채워진 비율 | `customer_pii_secure` 5개 enc 컬럼 NOT NULL count |
| pii_token 정합 | `pii_token` 패턴 검증 (`PII-` + SHA256[:16]) |
| token_map UNIQUE 무결성 | `original_hash` UNIQUE 위반 0 |
| token_map FK 정합 | `token_map.global_id` ↔ `master_customer.global_id` orphan 0 |

### [일상 운영] A-1-5. 개별 유저 (user_detail) — CS/감사 대응
| 보여줄 영역 | 데이터 출처 |
|---|---|
| 회원 프로파일 (운영 정보) | `users` + `master_customer` (PII 제외) |
| 동의 매트릭스 (8 도메인) | `consent` + 일시 |
| 계열사 매핑 | `customer_identity_map` 8 도메인 커버리지 |
| 매칭 이력 | `matching_audit_log` WHERE ls_user_id |
| 토큰 매핑 | `token_map` WHERE global_id (AWS 송신 검증용) |
| (분석 결과/추천 이력은 별도 분석 도구로 이관) | — |

---

### [가끔 확인] A-1-6. 고객 세그먼트 분포

> 데이터 관리자가 매일 보는 영역은 아님. 월간/분기 운영 리뷰용.

| 보여줄 메트릭 | 데이터 출처 |
|---|---|
| 고객 상태 분포 | `master_customer.customer_status` (ACTIVE/DORMANT/WITHDRAWN) |
| 고객 타입 분포 | `master_customer.customer_type` (INDIVIDUAL/CORPORATE) |
| 가입 추이 | `master_customer.first_created_dt` 월별 |
| 최근 활동 (last_login 30/90/180일) | `users.last_login_dt` |
| 동의 완료율 | `users.consent_completed` GROUP BY |
| user_status 분포 | `users.user_status` (ACTIVE/LOCK) |
| VIP 등급 분포 | `master_customer.vip_grade` (마케팅성 — 분석가 도구로 이관 권장) |

### [가끔 확인] A-1-7. 통합 AI 분석 적재 정합

> 분석 결과는 분석가/모델팀 영역. 데이터 관리자는 **적재 완료 여부와 분포 이상 감지**만.

| 보여줄 메트릭 | 데이터 출처 |
|---|---|
| 분석 완료 비율 | DynamoDB row 수 / `master_customer` 1M |
| 마지막 분석 시각 | `customer_360_profile.last_calc_dt` + DynamoDB `update_time` |
| 등급 분포 (적재 결과 분포 이상 감지용) | DynamoDB `dynamic_grade` 빈도 |
| lifesync_score 분포 (이상치 감지용) | `customer_360_profile.lifesync_score` histogram |
| (점수 평균/분산/ML 확률 등 본격 분석은 분석가 도구로) | — |

### [마케팅/분석가 영역 — 미포함 권장] A-1-8. 추천 funnel + 행동 로그

> 그룹데이터 통합 인프라 관리자 화면이 아님. 별도 마케팅 분석 도구(BI / Redshift) 영역.
> 적재 정합만 일상 운영에서 확인 (`customer_recommend_history`, `customer_dashboard_log` row 누적량).

| 만약 포함한다면 | 데이터 출처 |
|---|---|
| 추천 → 클릭 → 구매 funnel | `customer_recommend_history` clicked_flag/purchased_flag |
| 등급별 추천 효과 차이 | recommend_history GROUP BY `dynamic_grade` |
| 페이지 뷰 / 클릭 추이 | `customer_dashboard_log` GROUP BY DATE |
| 가장 많이 클릭된 상품 | `click_product_id` GROUP BY (TOP N) |

---

## A-2. 플랫폼 (고객) — 본인 데이터 표시

### A-2-1. 본인 동의 + 변경 이력 (settings)
| 영역 | 데이터 출처 |
|---|---|
| 8 도메인 동의 토글 | `consent` (이미 구현) |
| 동의/철회 시각 | `consent.consent_dt` + `revoke_dt` |
| 동의 버전 (재동의 안내) | `consent.consent_version` |

### A-2-2. 본인 계열사 연동 현황
| 영역 | 데이터 출처 |
|---|---|
| 연동된 계열사 매핑 | `customer_identity_map` WHERE global_id |
| 매칭 방식 (EXACT/FUZZY) | `match_type` (선택) |
| 미연동 계열사 안내 | identity_map에 없는 도메인 추출 |

### A-2-3. 본인 AI 분석 결과 (이미 부분 구현)
| 영역 | 데이터 출처 |
|---|---|
| 종합 점수 + 등급 | DynamoDB |
| 건강 점수 + 지표 | DynamoDB + (운영 시 BQ 검진/걸음수 등) |
| **(분석 입력 raw 점수 = onprem customer_360_profile)** | 본인 분석 결과로 볼 수 있음 |

### A-2-4. 본인 추천 상품 (이미 구현)
| 영역 | 데이터 출처 |
|---|---|
| 등급 기반 추천 | Aurora `recommend_rule` + `product_master` JOIN |
| 교차판매 추천 | `cross_sell_rule` |
| 활성 캠페인 (등급 맞춤) | `campaign_master` WHERE target_grade=내등급 |

---

# B. 본질 가치를 잘 드러내는 어드민 화면 우선순위 (추천)

그룹데이터 관리자에게 일상 가치 있는 5개:

| 우선순위 | 화면 | 핵심 가치 |
|---|---|---|
| **1** | 데이터 정합 / 적재 현황 (A-1-1) | 1M 매칭 확인, 데이터 파이프라인 건강도 |
| **2** | 계열사 ID 매칭 품질 (A-1-2) | 통합 인프라의 핵심 가치 — 매칭률/방식/감사 |
| **3** | 동의 거버넌스 (A-1-3) | 컴플라이언스 + 데이터 활용 허용 범위 시각화 |
| **4** | PII 보호 현황 (A-1-4) | 보안/암호화 정합, 토큰화 무결성 |
| **5** | 개별 유저 통합 (A-1-5) | CS/감사 대응 — 한 유저의 정합/연동/동의 한눈에 |

A-1-6 (세그먼트 분포), A-1-7 (AI 적재 정합)은 가끔 확인용. A-1-8 (추천 funnel/행동 로그)는 별도 분석 도구 영역.

---

# C. 현재 DB에 없지만 추가하면 좋을 정보 (설계 문서/아키텍처 보강 필요)

> 아래는 schema_reference/service_db_reference에 정의되지 않은 데이터. 운영 가치/시연 가치 큰 항목만 정리.
> **순서**: 일상 운영 가치 높은 것 → 가끔 보는 것 → 장기/시연 임팩트.

## [일상 운영] C-1. 데이터 파이프라인 메타 (운영 가시성)
| 추가 테이블/소스 | 보여줄 메트릭 |
|---|---|
| `etl_job_history` 신설 (또는 Glue/EMR 메타 활용) | 일별 ETL 실행 시각 / 처리 row 수 / 실패율 / 처리 시간 |
| `pipeline_sync_status` 신설 | 각 테이블별 마지막 sync_dt / 다음 예정 시각 / 지연 여부 |
| CloudWatch 메트릭 연동 | Lambda 호출 통계 (gcp_result_ingest, onprem_customer_query, consent_filter 등) |

→ 화면: "데이터 적재 파이프라인 모니터" — 그룹데이터 관리자의 일상 운영 화면

## [일상 운영] C-9. 데이터 소스 / 외부 시스템 연동 상태 (이전 C-9)
| 추가 테이블 | 보여줄 메트릭 |
|---|---|
| `external_system_status` 신설 | 계열사별 데이터 소스 (BANK API, CARD API 등) 연결 상태 |
| (마지막 sync, 응답 시간, 오류율) | 그룹데이터 통합 안정성 |

→ 화면: 어드민 "외부 연동 모니터" — 계열사 데이터 수집의 핵심. 매일 모니터링 대상.

## [일상 운영] C-4. 가입 상품 동기화 (이전 C-4)
| 추가 테이블 | 보여줄 메트릭 |
|---|---|
| `customer_subscription` 신설 | global_id, product_id, company_code, subscription_date, status, terminated_at |
| `subscription_event_log` 신설 | 가입/해지/변경 이벤트 이력 |

→ 화면: 어드민 user_detail "보유 상품" 탭 (Aurora `customer_recommend_history` 직접 SELECT). 현재 `recommend_history.purchased_flag`는 추천 기반 구매만 추적, 실제 그룹사에서 가입한 상품은 별도 동기화 필요. (플랫폼 `/api/my-products` 라우트는 2026-05-20 제거 — commit a6cfd58)

## [가끔 확인 — 거버넌스/감사] C-2. PII 접근 감사 로그
| 추가 테이블 | 보여줄 메트릭 |
|---|---|
| `pii_access_audit_log` 신설 | 누가 / 언제 / 어떤 global_id의 PII 복호화했는지 |
| (컬럼 후보: audit_id, actor_user, target_global_id, access_dt, reason, source_ip) | 비정상 접근 탐지, 권한 변경 이력 |

→ 화면: "PII 접근 감사" — 보안 + 컴플라이언스용. 매일 보지 않고 보안 이슈 발생 시 / 정기 감사 시. `matching_audit_log`는 매칭 시도 감사만 다루므로 PII 접근은 별도 필요.

## [가끔 확인 — 거버넌스] C-7. 분석 모델 메타 (AI 거버넌스)
| 추가 테이블 | 보여줄 메트릭 |
|---|---|
| `ai_model_version` 신설 | 모델 이름, 버전, 학습일, 입력 feature 목록 |
| `ai_inference_log` 신설 | global_id 별 어떤 모델 버전이 어떤 결과 도출 |

→ 화면: 어드민 "AI 추적 가능성" — 점수/등급이 어떤 모델로 도출됐는지 추적 가능 (규제 대응). 모델 업데이트/감사 시점에만 확인.

## [가끔 확인 — 마케팅 효과] C-3. 캠페인 노출/전환 추적
| 추가 테이블 | 보여줄 메트릭 |
|---|---|
| `campaign_exposure` 신설 | 캠페인 X가 누구에게 노출됐는지 (campaign_id, global_id, exposed_at) |
| `campaign_conversion` 신설 | 노출 → 클릭 → 가입 funnel (campaign_id 기준) |

→ 화면: 캠페인 ROI 측정. 마케팅 영역. 데이터 관리자는 적재 정합만 확인.

## [장기 / 시연용] C-5. 고객 라이프타임 가치 (LTV) 통합 지표
| 추가 테이블/뷰 | 보여줄 메트릭 |
|---|---|
| `customer_ltv_summary` (집계 뷰 또는 별도 테이블) | global_id 별 추정 LTV, 그룹 전체 기여 가치 |
| 계열사별 매출 기여도 (BANK/CARD/SEC/INS/HLT) | 계열사 데이터 통합으로 가능한 가치 |

→ 화면: 어드민 유저 상세에 "그룹 기여 가치" 탭. **그룹데이터 통합의 결과 가치를 정량화**.

## [장기 / 시연용] C-6. Cross-Affiliate Activity (계열사 간 교차 활동)
| 추가 테이블 | 보여줄 메트릭 |
|---|---|
| `cross_affiliate_event` 신설 | 한 고객이 여러 계열사 사이에서 발생시킨 연계 이벤트 |
| (예: 은행 적금 만기 → 보험 가입, 카드 사용 → 헬스케어 등) | 통합 인프라가 만든 시너지 |

→ 화면: 어드민 "교차 활동 사례" — 통합 데이터의 진짜 가치 시연.

## [가끔 확인] C-8. 알림/안내 발송 이력
| 추가 테이블 | 보여줄 메트릭 |
|---|---|
| `notification_history` 신설 | 동의 만료, 휴면 전환, 등급 변경 등 시스템 알림 발송 이력 |
| (채널: push/SMS/email) | 채널별 도달률 |

→ 화면: 어드민 알림 운영 + 고객 settings에 "받은 알림" 영역.

---

# D. 적용 우선순위 권장 (시연/운영 가치 기준)

## 일상 운영 — 즉시 시연 가능 (현재 DB로)
1. 어드민 데이터 정합 / 적재 대시보드 (A-1-1)
2. 어드민 계열사 ID 매칭 품질 (A-1-2)
3. 어드민 동의 거버넌스 (A-1-3)
4. 어드민 PII 보호 현황 (A-1-4)
5. 어드민 user_detail 통합 (A-1-5)
6. 플랫폼 본인 동의/연동 (A-2-1 / A-2-2 — 일부 구현됨)

## 일상 운영 — 추가 설계 필요 (운영 전환 시)
7. 데이터 파이프라인 모니터 (C-1)
8. 외부 연동 모니터 (C-9)
9. 가입 상품 동기화 (C-4)

## 가끔 확인 — 시연 가능
10. 어드민 고객 세그먼트 분포 (A-1-6)
11. 어드민 AI 적재 정합 (A-1-7)

## 가끔 확인 — 추가 설계 필요
12. PII 접근 감사 (C-2)
13. AI 추적 가능성 (C-7)
14. 캠페인 노출/전환 추적 (C-3)
15. 알림 발송 이력 (C-8)

## 장기 — 그룹 통합 가치 시각화 (시연 임팩트 큼)
16. LTV (C-5)
17. Cross-Affiliate Activity (C-6)

## 미포함 권장 — 마케팅/분석가 영역
- 추천 funnel + 행동 로그 (A-1-8) — 별도 BI/Redshift 도구로

---

# E. 핵심 가이드 (디자인 시 유의)

1. **마케팅 시각화 (인구통계 분포, 상품 카테고리 인기 등)는 후순위** — 그룹데이터 관리자가 일상에 안 봄
2. **데이터 흐름/품질/감사 영역이 일상 운영의 중심** — 정합, 매칭, 동의, PII, 분석 메타
3. **개별 유저 화면(`user_detail`)도 운영 정보 중심** — 이름/이메일 같은 PII는 최소화
4. **고객 화면(플랫폼)은 본인 데이터만** — 본인 동의/연동/분석/추천. 마케팅성 요소는 부가
5. **시연 시 가장 임팩트 큰 영역 = "그룹 통합 가치"** — 1M 유저 × N 계열사 매칭, 동의 거버넌스, PII 분리 흐름
