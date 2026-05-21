# lifesync360-platform app.py 구조 가이드

파일 경로: `lifesync360-platform/app.py`  
포트: 5000  
역할: 고객용 웹 플랫폼. 로그인 → 개인화 추천 → 동의 관리 → 상품 신청 흐름 제공.

---

## 1. 환경변수 의존성

앱 시작 시 다음 환경변수가 없으면 **RuntimeError** 로 죽음. `start_ls360.sh` 가 Secrets Manager에서 주입.

| 변수 | 필수 | 설명 |
|------|------|------|
| `JWT_SECRET` | **필수** | HS256 서명 키. 없으면 시작 불가 |
| `USE_MOCK` | 선택 (기본 `true`) | `false` 로 설정해야 실DB 사용. 이걸 안 바꾸면 Lambda/Aurora 미호출 |
| `AURORA_HOST` | 실DB 필수 | Aurora MySQL 엔드포인트 |
| `DB_USER`, `DB_PASS` | 실DB 필수 | Aurora 접속 자격증명 |
| `DB_NAME` | 선택 (기본 `lifesync360`) | 데이터베이스 이름 |
| `REDIS_HOST` | 실DB 필수 | ElastiCache 엔드포인트 |
| `REDIS_PORT` | 선택 (기본 `6379`) | Redis 포트 |
| `DYNAMO_TABLE` | 선택 (기본 `lifesync_customer_result`) | DynamoDB 테이블명 |
| `ONPREM_QUERY_LAMBDA` | 선택 (기본 `lifesync-onprem-customer-query`) | 온프레미스 조회 Lambda |
| `PROFILE_SYNC_LAMBDA` | 선택 | ls_user_id → global_id 매핑 Lambda. 비워두면 global_id 매핑 생략 |
| `AWS_REGION` | 선택 (기본 `ap-northeast-2`) | boto3 리전 |

**트러블슈팅**: 앱이 모든 요청에 mock 데이터를 반환하면 `USE_MOCK=true` 상태. `start_ls360.sh` 에서 `USE_MOCK=false` 가 export 됐는지 확인.

---

## 2. 주요 상수

```
CONSENTS: 8개 동의 항목 (BANK/CARD/INSURANCE/SECURITIES/ONLINE_INS/HEALTHCARE/HOSPITAL/WEARABLE)
GRADE_SCORE_MAP: 등급별 최소 점수 (VIP=90, GOLD=80, SILVER=70, BASIC=60, CARE=0)
GRADE_BENEFITS: 등급별 혜택 텍스트 (settings.html 렌더링용)
```

이 상수들은 코드에 하드코딩. 등급 체계나 동의 항목이 바뀌면 여기를 직접 수정.

---

## 3. DB 연결 헬퍼

### `get_redis()`
- 싱글턴. 처음 호출 시 `REDIS_HOST`로 연결 생성.
- `decode_responses=True` — Redis에서 bytes 대신 str 반환.
- **문제 발생 시**: REDIS_HOST 환경변수 확인 → 앱 SG에서 Redis SG 6379 인바운드 허용 여부 확인.

### `get_dynamo_table()`
- DynamoDB resource 싱글턴. 테이블명 = `DYNAMO_TABLE` 환경변수.
- 테이블 schema: `global_id` (HASH) + `update_time` (RANGE). GetItem 쓰면 안 됨 — Query 필수.

### `get_db()`
- 매 호출마다 새 Aurora 연결 생성 (pymysql). 사용 후 반드시 `db.close()` 또는 `finally` 블록.
- `cursorclass=DictCursor` — 쿼리 결과가 dict 형태로 반환됨.
- **연결 실패 시**: Aurora SG 인바운드 → 앱 실행 위치(EC2 SG)가 Aurora SG 3306에 허용돼 있는지 확인.

---

## 4. On-Prem Lambda 연동

### `_call_onprem(action, **kwargs)`
- `ONPREM_QUERY_LAMBDA` (기본: `lifesync-onprem-customer-query`) 를 `InvocationType=RequestResponse` 로 호출.
- payload: `{"action": "login", "email": ..., "password": ...}` 형태.
- Lambda 응답 `statusCode != 200` 이면 ValueError 발생 → 호출부에서 catch.
- **필요한 IAM 권한**: EC2 instance profile에 `lambda:InvokeFunction` 필요. 없으면 503 반환.

### 지원하는 action 목록
| action | 설명 |
|--------|------|
| `login` | email/password 검증, ls_user_id + global_id 반환 |
| `get_user` | ls_user_id로 사용자 기본 정보 조회 |
| `get_all` | global_id로 consent + profile 통합 조회 |
| `get_pii` | global_id로 이름/전화번호 등 PII 복호화 조회 |
| `save_consent` | 동의 항목 저장 |
| `get_user_by_global` | global_id → ls_user_id 역조회 |

### `_resolve_global_id(ls_user_id, email)`
- `PROFILE_SYNC_LAMBDA` (customer-profile-sync) 호출 → global_id 반환.
- 실패해도 None 반환 (예외 무시). 현재 `/api/login` real 모드에서는 onprem lambda가 global_id 직접 반환하므로 실질적으로 미사용.

---

## 5. JWT 인증

### `make_jwt(ls_user_id, global_id)`
- payload: `sub`(ls_user_id), `gid`(global_id), `exp`(24h 후).
- HS256 알고리즘, `JWT_SECRET` 서명.

### `require_jwt` 데코레이터
- `Authorization: Bearer <token>` 헤더에서 토큰 추출 + 검증.
- 유효하면 `payload` kwargs로 함수에 주입 (`payload['sub']`=ls_user_id, `payload['gid']`=global_id).
- **프론트엔드**: localStorage key = `ls_token` (중요: `access_token` 아님). 헤더 누락 시 401.

---

## 6. 추천 엔진 (핵심 플로우)

`GET /api/recommendations` 가 아래 순서로 실행됨.

```
① DDB 조회 (_fetch_ddb_meta)
   → global_id → lifesync_customer_result 최신 1건 Query
   → grade, dynamic_score, health_score, vip_prob, next_best_action 추출

② Redis 캐시 확인 (_fetch_redis_cached_ids)
   → GET rec:{global_id}
   → JSON list of product_ids
   → HIT: product_ids로 product_master 직접 조회 (Aurora rule 매칭 건너뜀)
   → MISS: ③으로 진행

③ 룰 매칭 (_match_rules)
   → recommend_rule: target_grade + score 범위 + vip_required + health_min_score 조건 필터
   → NBA(next_best_action) 매핑된 action_code가 있으면 우선 정렬
   → cross_sell_rule: 첫 번째 base_category → target_category 최대 3개 추가

④ 상품 조회 (_fetch_products)
   → 캐시 HIT: product_id list로 IN 조회
   → 카테고리 매칭: 카테고리별 top 2개, 최대 20개
   → fallback: grade 최소 점수 기준 LIMIT 20

⑤ 추천 기록 + 점수 부여 (_enrich_and_record)
   → reason 문자열 생성 (NBA 매칭 / 등급 / cross_sell / VIP 후보 / 건강점수)
   → recommendation_score 계산 (priority_rank + 등급 보너스 + NBA 보너스 - cross_sell 패널티)
   → customer_recommend_history INSERT (모든 상품에 대해)
   → 점수 내림차순 재정렬

⑥ Redis 캐시 저장 (미스였을 때만)
   → SETEX rec:{global_id} 21600 (6h) [product_id list]

⑦ 상위 10개만 응답
   → {meta: {grade, score, health, vip_prob, nba}, products: [...]}
```

**NBA → action_code 매핑** (`_NBA_TO_ACTION`):
DynamoDB `next_best_action` 컬럼(results.csv 기반)을 `recommend_rule.action_code` 로 변환.
예: `RETENTION` → `RECOMMEND_HEALTH`, `PB` → `RECOMMEND_PB`.

**VIP 임계값**: `VIP_PROB_THRESHOLD` 환경변수 (기본 0.5). vip_prob >= threshold면 vip_required='Y' 룰도 포함.

**알려진 문제점**:
- Redis에 `rec:{global_id}` 가 `zset` 타입으로 저장돼 있으면 GET이 WRONGTYPE 오류. 직전 세션 시딩 데이터가 남은 경우. DEL로 삭제 후 재시작.
- DynamoDB에 global_id 데이터가 없으면 grade='BASIC', score=0 으로 fallback → 최저 등급 상품만 노출.

---

## 7. API 라우트 상세

### `POST /api/login`
- mock: `MOCK_USERS` dict에서 email 조회 + SHA256 해시 비교
- real: `_call_onprem('login')` → ls_user_id + global_id → JWT 발급
- **주의**: 경로가 `/api/login` 임. `/api/auth/login` 아님 (과거 혼동 사례 있음)

### `GET /api/me`
- real 모드에서 4개 병렬 호출 (`ThreadPoolExecutor max_workers=4`):
  - `get_user` (ls_user_id → login_email, global_id)
  - `get_all` (global_id → consents, profile)
  - `get_pii` (global_id → name)
  - `_ddb_get_latest` (global_id → dynamic_grade)
- 각 future가 실패해도 개별 except 처리 → 부분 데이터 반환
- **미완성**: PII 복호화 + DynamoDB grade 연동은 구현됐으나 실제 onprem Lambda에서 name/grade 반환하는지는 별도 검증 필요

### `POST /api/event`
- **이벤트 타입 → DB 매핑**:

| event_type | page_type | product_click | banner_click | history 업데이트 |
|------------|-----------|---------------|--------------|-----------------|
| recommendation_click | MAIN | Y | N | clicked_flag='Y' |
| product_view | DETAIL | Y | N | 없음 |
| apply_view | DETAIL | N | N | 없음 |
| apply_started | DETAIL | Y | N | 없음 |
| apply_submitted | DETAIL | Y | N | purchased_flag='Y' |
| purchased | MAIN | N | N | purchased_flag='Y' |
| banner_click | MAIN | N | Y | 없음 |
| tab_click | MAIN | N | N | 없음 |

- `customer_dashboard_log` INSERT + (product_id 있을 때) `customer_recommend_history` UPDATE.
- 실패해도 200 반환 (로깅만). 클라이언트에서 재시도 로직 없음.

### `GET /api/my-applications`
- `customer_product_application` + product/company/category JOIN.
- mock에서는 하드코딩 3건 반환.
- real에서 `created_at`이 NULL인 경우 있음 (스키마 v3 기준 applied_at 컬럼명 불일치 가능성).

### `POST /api/product/<code>/apply`
- onprem Lambda `get_user_by_global` → 실제 ls_user_id 재조회 (JWT 값과 다를 수 있음).
- `application_id` = `APP-{UTC timestamp}-{ls_user_id 끝 6자리}`.
- INSERT 후 `customer_recommend_history.purchased_flag='Y'` UPDATE + `customer_dashboard_log` INSERT도 직접 수행 (event와 중복 안전).

---

## 8. 페이지 라우트

| 경로 | 템플릿 | 설명 |
|------|--------|------|
| `/login` | `login.html` | JWT 없어도 접근 가능 |
| `/` | `index.html` | 추천 메인 (JWT 필요, JS에서 `/api/recommendations` 호출) |
| `/consent` | `consent.html` | CONSENTS 상수 렌더링, 동의 저장은 `/api/consent` POST |
| `/settings` | `settings.html` | GRADE_BENEFITS + CONSENTS 전달 |
| `/product/<code>` | `product.html` | product_master + product_option 조회 |
| `/product/<code>/apply` | `apply.html` | 신청 폼 (실제 신청은 POST `/api/product/<code>/apply`) |
| `/register` | `register.html` | 현재 정적 (가입 API 미구현) |
| `/health` | JSON | 헬스체크. USE_MOCK 상태 확인용 |

---

## 9. Mock 모드 vs 실데이터 모드

`USE_MOCK=true` (기본값): Lambda, Aurora, Redis, DynamoDB 호출 없음.
`mock_data.py`에서 `MOCK_USERS`, `MOCK_RECOMMENDATIONS`, `PRODUCTS_MAP`, `get_mock_health` 사용.

실데이터 전환 시 반드시 확인:
1. `USE_MOCK=false` 환경변수 설정 (`start_ls360.sh` 에 있음)
2. Secrets Manager에 `AURORA_HOST`, `DB_USER`, `DB_PASS`, `REDIS_HOST` 포함 여부
3. EC2 IAM role에 `lambda:InvokeFunction` + `dynamodb:Query` + `secretsmanager:GetSecretValue` 권한
4. Aurora SG에 EC2 SG 3306 인바운드 허용
5. Redis SG에 EC2 SG 6379 인바운드 허용

---

## 10. 알려진 한계 / 미완성 항목

| 항목 | 현황 | 비고 |
|------|------|------|
| `/api/me` name/grade | 구현됨, 검증 필요 | onprem Lambda `get_pii` 응답 스키마 확인 필요 |
| `/register` 가입 API | 미구현 | 템플릿만 존재 |
| 추천 캐시 무효화 | 없음 | 6h TTL 만료 전 동의 변경해도 캐시 유지 |
| Aurora 커넥션 풀 | 없음 | 요청마다 새 연결 생성/해제. 고트래픽 시 문제 |
| 웨어러블 실시간 점수 반영 | 없음 | DDB는 일배치. 실시간 점수는 DDB 미갱신 상태 |
