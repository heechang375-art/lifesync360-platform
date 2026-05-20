# LifeSync360 테스트 참조 — 계정 / SQL / API

---

## 1. 플랫폼 테스트 계정 (lifesync360-platform, Mock 모드)

> `USE_MOCK=true` 일 때만 유효. 운영 연동 시 Aurora DB 계정 사용.

| 이메일 | 비밀번호 | 이름 | 등급 | ls_user_id |
|--------|----------|------|------|-----------|
| test@lifesync.com  | password123 | 김철수 | PLATINUM | LS-AABBCC11-000001 |
| test2@lifesync.com | password123 | 이수진 | GOLD     | LS-DDEEFF22-000002 |
| test3@lifesync.com | password123 | 박지훈 | SILVER   | LS-99AABB33-000003 |

### 계정별 특성

| 항목 | 김철수 (PLATINUM) | 이수진 (GOLD) | 박지훈 (SILVER) |
|------|-----------------|-------------|----------------|
| dynamic_score | 92.4 | 74.0 | 55.2 |
| health_score  | 88   | 72   | 53   |
| 동의 계열사 | 전체 7개 | bank/card/insurance/healthcare | bank/card/healthcare |
| 미동의 → MY탭 | 없음 (전부 표시) | inet_ins/securities/hospital → 403 | insurance/inet_ins/securities/hospital → 403 |
| 웨어러블 연동 | O | X | X |
| 혈당 상태 | NORMAL | CAUTION | DANGER |

**테스트 목적별 계정 선택**
- 전체 기능 확인 → **김철수**
- 동의 없는 계열사 403 확인 → **이수진** (inet_ins, securities, hospital 클릭)
- 건강지표 DANGER 표시 확인 → **박지훈**

---

## 2. 어드민 계정 (admin-platform)

> `ADMIN_USER` / `ADMIN_PASSWORD` 환경변수로 설정. 기본 계정명은 `admin`.

| 항목 | 값 |
|------|-----|
| 접속 URL (로컬) | http://localhost:5001 |
| 계정명 | `admin` |
| 비밀번호 | `ADMIN_PASSWORD` 환경변수 값 |
| 로컬 기동 시 | 아래 환경변수 설정 필요 |

```bash
# 로컬 기동 예시
export ADMIN_USER=admin
export ADMIN_PASSWORD=admin123
export SECRET_KEY=local-secret-key
export USE_MOCK=true
export DYNAMO_TABLE=lifesync-scores
export AWS_REGION=ap-northeast-2
python app.py
```

---

## 3. 로컬 플랫폼 기동

```bash
cd lifesync360-platform
export USE_MOCK=true
export JWT_SECRET=local-dev-secret
python app.py
# → http://localhost:5000
```

---

## 4. API 테스트 (curl)

### 4-1. 로그인 → JWT 획득

```bash
# 로컬
TOKEN=$(curl -s -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@lifesync.com","password":"password123"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

echo $TOKEN
```

이후 모든 API 요청에 `-H "Authorization: Bearer $TOKEN"` 붙여서 사용.

### 4-2. 내 정보 확인

```bash
# 언제: 로그인 후 유저 정보(이름/등급/global_id) 확인
curl http://localhost:5000/api/me \
  -H "Authorization: Bearer $TOKEN"
```

### 4-3. 대시보드 점수 조회

```bash
# 언제: 홈 화면 동적 점수/건강점수/지표 렌더링 확인
curl http://localhost:5000/api/dashboard \
  -H "Authorization: Bearer $TOKEN"
```

### 4-4. 상품 추천 조회

```bash
# 언제: FOR YOU 탭 상품 카드 노출 확인
curl http://localhost:5000/api/recommendations \
  -H "Authorization: Bearer $TOKEN"
```

### 4-5. 헬스체크

```bash
curl http://localhost:5000/health         # platform
curl http://localhost:5001/health         # admin
curl http://192.168.56.12:8000/health     # 온프레미스 tokenization
curl http://192.168.56.13/health          # 온프레미스 private API (Nginx 경유)
```

---

## 5. Aurora MySQL 조회 (USE_MOCK=false 운영 연동 시)

접속:
```bash
mysql -h <aurora-endpoint> -u lifesync_app -p lifesync
```

### 5-1. 사용자 조회

```sql
-- 전체 사용자 목록
SELECT ls_user_id, global_id, name, email, grade, created_at
FROM users
ORDER BY created_at DESC
LIMIT 20;

-- 특정 사용자 조회
SELECT * FROM users WHERE email = 'test@lifesync.com';

-- 등급별 사용자 수
SELECT grade, COUNT(*) AS cnt FROM users GROUP BY grade ORDER BY cnt DESC;
```

**언제**: 회원가입(/api/register) 후 DB 반영 확인, 등급 분포 파악

### 5-2. 동의 현황 조회

```sql
-- 특정 사용자의 동의 현황
SELECT consent_key, consent_yn, updated_at
FROM consent
WHERE global_id = 'G000000001'
ORDER BY consent_key;

-- 계열사별 동의 집계
SELECT consent_key,
       SUM(consent_yn = 'Y') AS 동의수,
       SUM(consent_yn = 'N') AS 미동의수
FROM consent
GROUP BY consent_key;

```

**언제**: /api/consent POST 후 반영 확인

### 5-3. 상품 마스터 조회

```sql
-- 활성 상품 전체
SELECT product_id, company_id, product_type, product_name, min_grade
FROM product_master
WHERE is_active = 1
ORDER BY company_id, product_id
LIMIT 50;

-- 특정 등급 이상에게 노출되는 상품
SELECT product_id, product_name, min_grade
FROM product_master
WHERE min_grade IN ('BASIC','SILVER') AND is_active = 1;
```

**언제**: /api/recommendations 결과가 DB 상품과 일치하는지 확인

### 5-4. 추천 이력 조회

```sql
-- 특정 유저 추천 → 클릭 → 구매 퍼널
SELECT r.global_id, r.product_id, p.product_name,
       r.recommended_at, r.clicked_at, r.purchased_at
FROM customer_recommend_history r
JOIN product_master p ON p.product_id = r.product_id
WHERE r.global_id = 'G000000001'
ORDER BY r.recommended_at DESC;

-- 클릭률 상위 상품
SELECT product_id,
       COUNT(*) AS 추천수,
       SUM(clicked_at IS NOT NULL) AS 클릭수,
       ROUND(SUM(clicked_at IS NOT NULL) / COUNT(*) * 100, 1) AS 클릭률
FROM customer_recommend_history
GROUP BY product_id
ORDER BY 클릭률 DESC
LIMIT 10;
```

**언제**: 어드민 - 상품 퍼널 효과 분석

### 5-5. 대시보드 로그 조회

```sql
-- 특정 유저 최근 액션
SELECT action_type, action_detail, created_at
FROM customer_dashboard_log
WHERE global_id = 'G000000001'
ORDER BY created_at DESC
LIMIT 20;

-- 오늘 액션 타입별 집계
SELECT action_type, COUNT(*) AS cnt
FROM customer_dashboard_log
WHERE DATE(created_at) = CURDATE()
GROUP BY action_type;
```

---

## 6. 온프레미스 MySQL 조회 (ls-db: 192.168.56.11)

접속:
```bash
# ls-db VM에서 직접
mysql -u lifesync -p lifesync_onprem

# 또는 ls-vpngw에서 원격 접속
mysql -h 192.168.56.11 -u lifesync -p lifesync_onprem
```

### 6-1. 고객 매핑 조회

```sql
-- 특정 global_id의 계열사 ID 매핑
SELECT global_id, company_id, affiliate_customer_id, linked_at
FROM customer_identity_map
WHERE global_id = 'G000000001';

-- 매핑 없는 global_id (Lambda 프로필 동기화 대상)
SELECT u.global_id, u.ls_user_id
FROM lifesync_onprem.users u
LEFT JOIN customer_identity_map m ON m.global_id = u.ls_user_id
WHERE m.global_id IS NULL;
```

**언제**: /api/login 후 global_id 매핑 확인, Lambda profile-sync 호출 검증

### 6-2. 토큰화 PII 조회

```sql
-- 특정 고객의 토큰화된 PII
SELECT global_id, pii_type, token_id, created_at
FROM customer_pii_secure
WHERE global_id = 'G000000001'
ORDER BY created_at DESC;

-- pii_type별 토큰 수
SELECT pii_type, COUNT(*) AS cnt
FROM customer_pii_secure
GROUP BY pii_type;
```

**언제**: /tokenize 호출 결과가 DB에 반영됐는지 확인

### 6-3. 동의 현황 조회

```sql
-- 온프레미스 동의 현황 (Aurora consent 테이블과 별도 관리)
SELECT global_id, consent_key, consent_yn, updated_at
FROM consent
WHERE global_id = 'G000000001';
```

---

## 7. 온프레미스 Tokenization API 테스트

서비스 주소: `http://192.168.56.12:8000`
허용 필드: `resident_number` `phone_number` `account_number` `card_number` `email`

```bash
# 토큰화
curl -X POST http://192.168.56.12:8000/tokenize \
  -H "Content-Type: application/json" \
  -d '{"field": "phone_number", "value": "01012345678"}'
# 기대값: {"token_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"}

# 역토큰화
curl http://192.168.56.12:8000/detokenize/<token_id>
# 기대값: {"field_name": "phone_number", "global_id": "...", "created_at": "..."}
# 원본값은 저장 안 함 (비저장 정상)

# 중복 토큰화 (같은 값 → 같은 token_id)
curl -X POST http://192.168.56.12:8000/tokenize \
  -H "Content-Type: application/json" \
  -d '{"field": "phone_number", "value": "01099999999"}'
# 두 번 호출해도 token_id 동일해야 함

# 허용되지 않은 필드 (400 에러 확인)
curl -X POST http://192.168.56.12:8000/tokenize \
  -H "Content-Type: application/json" \
  -d '{"field": "address", "value": "서울시 강남구"}'
# 기대값: HTTP 400 + {"detail": "Field 'address' not in allowed fields"}
```

---

## 8. 온프레미스 VM 정보

| VM | IP | 역할 | 접속 |
|----|----|------|------|
| ls-vpngw  | 192.168.56.10 | Ansible Control Node / VPN GW | `ssh ansible@192.168.56.10` |
| ls-db     | 192.168.56.11 | MySQL (온프레미스 고객 DB)    | `ssh ansible@192.168.56.11` |
| ls-token  | 192.168.56.12 | Tokenization Service (8000)   | `ssh ansible@192.168.56.12` |
| ls-api    | 192.168.56.13 | Private API + Cron (Nginx 80) | `ssh ansible@192.168.56.13` |

SSH 키: `~/.ssh/lifesync360-onprem.pem`

```bash
# Ansible Control Node에서 전체 VM ping
ssh ansible@192.168.56.10
cd /opt/ansible/onprem-prod-repo/ansible
ansible all -m ping -i inventory/hosts.yml
```
