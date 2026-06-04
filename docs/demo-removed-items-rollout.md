# 시연용 제거 항목 + 운영 전환 가이드

> **기준일**: 2026-05-14
> **목적**: 시연을 위해 임시로 빼낸 기능들과 그 이유, 그리고 운영 환경에서 복원/구현하는 방법 정리
>
> ⚠️ **프로젝트 종료(2026-06) — 운영 전환 미실행.** 시연 상태로 마감됐습니다. 아래 운영 복원 방법과 14번 체크리스트의 `[ ]` 항목은 실행되지 않았습니다. **"시연을 위해 어떤 기능을 뺐고, 운영하려면 무엇을 복원해야 하는지"의 인계 기록**으로 참고하세요.

---

## 1. 점수 표시 — 금융/행동 점수 제거

### 제거 내용
- `lifesync360-platform/app.py` `/api/dashboard` 응답에서 `fin_score`, `behavior_score` 키 제거
- `lifesync360-platform/templates/index.html` 점수 토글 4개 → 2개 (종합/건강만)
- `scoreMap`에서 금융/행동 키 제거

### 제거 이유
- DynamoDB `lifesync_customer_result` 테이블에 `fin_score`, `behavior_score` 컬럼 없음
- 현재 적재된 컬럼: `dynamic_score`, `health_score`, `vip_prob`, `signup_prob`, `rec_prob`, `next_best_action`, `update_time`, `dynamic_grade`
- 운영에서 호출 시 `_f('fin_score')`는 항상 None → 화면 0 표시되어 어색

### 운영 구현 방법
1. **데이터 적재**: `customer_360_profile.finance_score` / `customer_360_profile.asset_score` 같은 raw 점수를 DynamoDB로 동기화
   - 옵션 A: `gcp_result_ingest` Lambda 확장 — GCP 분석 결과 + 온프레 raw 점수 통합 적재
   - 옵션 B: 별도 sync Lambda 신설 — `customer_360_profile.last_calc_dt` 기준 증분 적재
2. **코드 원복**: `/api/dashboard` 응답에 `finance_score`, `behavior_score` 추가, `index.html` 토글 4개 복원

---

## 2. MY 탭 — 가입 상품 드릴다운 제거

### 제거 내용
- `index.html` 헤더의 `my-back-btn`, `header-my-company` 토글 제거
- MY 탭 내부 계열사 메뉴(`my-sec-companies`), 세그먼트 컨트롤, `my-detail` div 제거
- `showMyDetail` / `showMyList` / `switchMySection` 함수 제거
- nav 클릭 핸들러의 `if (activeTab === 'my')` 분기 제거

### 제거 이유
- Aurora `customer_recommend_history`에 `purchased_flag='Y'`인 row 0건 → 가입 상품 데이터 없음
- 현재 DB 구조엔 별도 `customer_subscription` 같은 가입 이력 테이블도 없음
- 빈 화면 시연 어색

### 운영 구현 방법
> 참고: `/api/my-products` 라우트 + `MOCK_MY_PRODUCTS` + `MOCK_CONSENTED_KEYS` 는 2026-05-20 (commit a6cfd58) 에서 통째 제거됨. 복원 시 새 라우트 신설 필요.

1. **테이블 신설**: `customer_subscription` 또는 `customer_purchase`
   - 컬럼: `subscription_id`, `global_id`, `product_id`, `company_code`, `subscription_date`, `status` 등
2. **결제/구매 이벤트 → INSERT**: 실제 구매 시점에 그 테이블에 row 추가
3. **`/api/my-products` 새로 신설**: `customer_subscription` 조회 기반으로 라우트 + 동의 체크 로직 재구현
4. **`index.html` MY 탭 복원**: 계열사 메뉴 + my-detail 영역 + JS 함수 다시 추가

---

## 3. 계정 정보 — 회원번호(ls_user_id) 제거

### 제거 내용
- `settings.html` "계정 정보" 서브뷰의 회원번호 행 제거
- `s-userid` 관련 JS 제거

### 제거 이유
- 사용자가 내부 식별자(`LS-AABBCC11-000001`)를 직접 활용할 일 없음
- PII 최소화 원칙 — 화면 노출 최소화

### 운영 구현 방법
- 굳이 표시할 필요 없음. 유지 가능
- 고객센터 문의 시 식별 위해 표시하고 싶다면 `s-userid` 행 복원
- 또는 마스킹 (`LS-***-000001`) 등으로 보여줄 수도

---

## 4. 등급 업그레이드 가이드 제거

### 제거 내용
- `settings.html` "등급 혜택" 서브뷰의 `upgrade-actions-section` 제거
- `/api/upgrade-actions` fetch + 표시 JS 제거

### 제거 이유
- `/api/upgrade-actions` 운영 모드가 `return jsonify([])` 빈 배열 반환
- `upgrade_actions_engine`이 동작하려면 DynamoDB(grade/점수) + 온프레(consent) + Aurora(이력) 데이터 모두 필요한데 일부 부재

### 운영 구현 방법
> 참고: 2026-05-20 (commit a6cfd58) 에서 `/api/upgrade-actions` 라우트 + `upgrade_actions_engine.py` + `_MOCK_USER_CONTEXT` 통째 제거됨. 복원 시 라우트와 엔진을 새로 작성해야 함.

1. **데이터 충족**: DynamoDB에 grade/scores 적재 + 온프레 consent 호출 가능 + Aurora 추천 이력 누적
2. **엔진 + 라우트 재작성**: `upgrade_actions_engine.py` 신규 작성 (개인화 룰) + `/api/upgrade-actions` 라우트 신설 + USE_MOCK 분기로 엔진 호출
3. **`settings.html` 섹션 복원**: `upgrade-actions-section` + 관련 fetch + 표시 JS 다시 추가

---

## 5. 어드민 — 추천/행동 섹션 제거 (예정, 아직 미반영)

### 제거 예정 내용
- `admin-platform/templates/overview.html`
  - "최근 추천" 섹션
  - "추천 전환 funnel" 섹션
  - "행동 현황" (상품 조회 TOP / 탭 클릭) 섹션
- `admin-platform/templates/user_detail.html`
  - "추천 & 구매" 탭
  - "활동 로그" 탭 (신설 예정이었음)

### 제거 이유
- Aurora `customer_recommend_history`, `customer_dashboard_log` 0건 적재
- 화면이 비어있어 시연 어색

### 운영 구현 방법
1. **데이터 누적**: 시간 지나면 `/api/recommendations`, `/api/event` 호출로 자동 누적
2. **시드 적재** (시연 빠르게 보여주려면): 100~1000건 모의 데이터 INSERT 스크립트 작성
3. **clicked_flag/purchased_flag UPDATE 로직** 이미 추가됨 (`product.html`에서 `product_id` 전달, `api_event`에서 UPDATE)

---

## 6. 어드민 — user_detail 탭 라벨 변경 (예정)

### 변경 예정 내용
- "계정 정보" 탭 → **"회원 프로파일"** 로 변경
- 이름/이메일/회원번호/Global ID 표시 → 운영 정보 중심으로 (PII 0건)
  - Global ID, 회원 상태, 고객 상태, VIP 등급, 고객 타입, 동의 완료, 가입일, 최근 로그인, 현재 등급, 인구통계 6종

### 이유
- 어드민이 보는 화면에 "계정 정보"라는 용어는 부적절 (본인 화면 표현)
- 어드민은 PII 노출 최소화

### 구현 시점
- 시연 후 어드민 본격 정리 시점

---

## 7. 인증 — api_login / api_register Mock 강제 (Lambda 미배포 임시)

### 임시 변경
- `lifesync360-platform/app.py`:
  - `from mock_data import MOCK_USERS` 부활 (다른 mock은 그대로 import 주석)
  - `api_register`: 무조건 `MOCK_USERS` 첫 번째 유저 토큰 발급
  - `api_login`: `MOCK_USERS` 이메일/비번 검증 (Lambda 안 거침)
- `api_me`: `_call_onprem` 실패 시 `MOCK_USERS` fallback으로 name/email 채움

### 이유
- `lifesync-onprem-customer-query` Lambda 미배포 → 인증 흐름 (`_call_onprem('login'/'register')`) 작동 불가

### 운영 구현 방법
1. **Lambda 배포** (`docs/lambda-onprem-query-deploy.md` STEP 1~9)
2. **온프레 private_api 재배포** (Ansible)
3. **온프레 ipsec.conf rightsubnet 추가** (Platform VPC CIDR)
4. **시연용 임시 코드 원복**:
   ```python
   # 변경 전 (임시)
   def api_login():
       user = MOCK_USERS.get(email)
       if not user or sha256(...) != user['password_hash']:
           return 401
       token = make_jwt(...)
       return jsonify(...)

   # 변경 후 (운영)
   def api_login():
       try:
           user = _call_onprem('login', email=email, password=password)
       except ValueError:
           return 401
       except Exception as e:
           return 502
       token = make_jwt(...)
       return jsonify(...)
   ```
5. **MOCK_USERS import 다시 주석**
6. **`api_me` fallback 단순화** (선택)

---

## 8. ECS taskdef — 컨테이너 이름/포트/family 정합

### 시연 진행 중 변경
- `lifesync360-platform/taskdef.json`:
  - `family`: `lifesync-platform` → `lifesync-dev-21-lifesync-ecs-existing-vpc-v4-td`
  - `containerDefinitions[0].name`: `platform` → `app`
  - `portMappings[0].containerPort`: `8000` → `80`
  - `environment` `DB_NAME`: `lifesync` → `lifesync360`
  - `environment` `DYNAMO_TABLE`: `lifesync-scores` → `lifesync_customer_result`
- `lifesync360-platform/appspec.yaml`:
  - `ContainerName`: `platform` → `app`
  - `ContainerPort`: `8000` → `80`

### 이유
- 기존 ECS Service의 LoadBalancer가 `app` container의 `80` port를 가리키고 있음
- 기존 IaC가 만든 Task Definition family 이름이 `lifesync-dev-21-...-td`
- DB/DynamoDB 실 이름과 일치

### 영구 반영 필요
- 위 변경은 ECS 새 revision register로 시연 환경엔 적용됨
- **git push** 시 영구 (CodePipeline 자동 등록 시 정합 유지)

---

## 9. 어드민 측 동일 정합 (뒤로 미룬 작업)

### 미반영 항목
- `admin-platform/taskdef.json`:
  - `family` 실제 이름으로 (list-task-definitions로 확인)
  - `containerDefinitions[0].name` 실제 service 기대값으로
  - `portMappings[0].containerPort` 실제 listen port로
- `admin-platform/appspec.yaml`: 동일

### 구현 방법
- platform과 동일 패턴 (`docs/ecs-taskdef-redeploy.md` STEP 1~5)

---

## 10. 운영 추천 응답 구조 정합

### 현재 이슈
- `lifesync360-platform/app.py` `/api/recommendations` 비Mock 분기가 평탄 list 반환
- `index.html` JS는 `[{key, name, products: [...]}, ...]` 구조 가정
- → 운영 모드에서 추천 탭 빈 화면

### 운영 구현 방법
- 백엔드를 mock 구조와 동일하게 그룹핑:
```python
# 현재 (평탄)
return jsonify(products)

# 변경 (그룹)
grouped = {}
for p in products:
    key = p['company_code'].lower()
    grouped.setdefault(key, {'key': key, 'name': p['company_name'], 'products': []})
    grouped[key]['products'].append({
        'id': p['product_code'],
        'type': p['category_code'],
        'name': p['product_name'],
        'desc': p['description'][:50],
        'product_id': p['product_id'],  # clicked_flag UPDATE용
    })
return jsonify(list(grouped.values()))
```
- 적용 후 index.html 추천 탭/홈 추천 미리보기 정상 표시

---

## 14. 운영 전환 체크리스트 (요약)

### 인프라
- [ ] `docs/lambda-onprem-query-deploy.md` 가이드대로 Lambda 배포
- [ ] LifeSync VPC TGW Attachment + 온프레 라우팅
- [ ] 온프레 ipsec.conf rightsubnet Platform VPC CIDR 추가
- [ ] 온프레 private_api 재배포 (Ansible)
- [ ] Vault에 `vault_token_aes_key_b64` 추가
- [ ] ECS Task Role에 `lambda:InvokeFunction` 권한

### 코드 원복 (운영 모드 활성화)
- [ ] `api_login`, `api_register` 임시 Mock 강제 제거 → `_call_onprem` 흐름 복원
- [ ] `from mock_data import MOCK_USERS` 다시 주석
- [ ] `api_me` Lambda fallback 단순화 (선택)
- [ ] `/api/recommendations` 응답 그룹핑 구조 변경
- [ ] `index.html` 점수 토글 4개 / MY 탭 가입상품 복원 (데이터 적재 후)
- [ ] `settings.html` 회원번호 / 등급 업그레이드 가이드 복원 (선택)

### 데이터
- [ ] DynamoDB 100만 유저 적재 (gcp_result_ingest 운영)
- [ ] `customer_recommend_history`, `customer_dashboard_log` 누적 (자연 또는 시드)
- [ ] DynamoDB에 raw 점수 5종 동기화 (선택)
- [ ] `customer_subscription` 테이블 신설 + 가입 데이터 적재

### 어드민
- [ ] `admin-platform/taskdef.json`/`appspec.yaml` family/name/port 정합
- [ ] ECS register-task-definition + force-deploy
- [ ] overview/users/user_detail 재설계 (4탭 회원프로파일/AI/동의/제휴사)
- [ ] 추천/funnel/행동 섹션 데이터 누적 후 복원

---

## 관련 문서

- `docs/lambda-onprem-query-deploy.md` — Lambda + VPN 배포
- `docs/ecs-taskdef-redeploy.md` — ECS Task Definition 재등록 + force-deploy
- `schema_reference.md` — 온프레 DB 레퍼런스
- `service_db_reference.md` — Aurora Service-DB 레퍼런스
- `project-progress.md` — 전체 진행 이력
