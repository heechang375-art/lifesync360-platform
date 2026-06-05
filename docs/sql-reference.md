# SQL / DynamoDB 쿼리 레퍼런스

DB 연결 정보:
- **온프렘**: `ls-db` (192.168.56.11) · 스키마 `lifesync_onprem`
- **Aurora**: `auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com` · 스키마 `lifesync360`
- **DynamoDB**: 테이블 `lifesync_customer_result` · 리전 `ap-northeast-2`

---

## 1. 온프렘 MySQL (`lifesync_onprem`)

### 로그인 검증
```sql
-- 이메일로 사용자 조회 (로그인 시)
SELECT user_id, ls_user_id, global_id, password_hash, user_status
FROM users
WHERE login_email = 'user0000924@lifesync.com';
```

### 사용자 정보 조회
```sql
-- global_id로 플랫폼 회원 조회
SELECT u.ls_user_id, u.login_email, u.user_status, u.consent_completed,
       u.created_dt, u.last_login_dt
FROM users u
WHERE u.global_id = 'G000000924';

-- 전체 정보: 회원 + 마스터 + 360프로파일 조인
SELECT u.ls_user_id, u.login_email, u.user_status,
       mc.customer_status, mc.vip_grade, mc.customer_type, mc.first_created_dt,
       cp.gender, cp.age_band, cp.region, cp.income_grade, cp.asset_grade,
       cp.wearable_flag, cp.health_score, cp.finance_score, cp.lifesync_score
FROM users u
JOIN master_customer mc ON u.global_id = mc.global_id
JOIN customer_360_profile cp ON u.global_id = cp.global_id
WHERE u.global_id = 'G000000924';
```

### 동의 조회
```sql
-- 특정 고객의 현재 동의 도메인 목록
SELECT domain, consent_flag, consent_dt, revoke_dt
FROM consent
WHERE global_id = 'G000000924'
  AND consent_flag = 'Y'
  AND revoke_dt IS NULL
ORDER BY domain;

-- 특정 도메인 동의 여부 단건 확인
SELECT consent_flag
FROM consent
WHERE global_id = 'G000000924' AND domain = 'BANK';
```

### 통계 / 현황 확인
```sql
-- 테이블별 행 수 빠른 확인
SELECT table_name, table_rows
FROM information_schema.tables
WHERE table_schema = 'lifesync_onprem'
ORDER BY table_rows DESC;

-- 활성 회원 수
SELECT user_status, COUNT(*) AS cnt
FROM users
GROUP BY user_status;

-- 도메인별 현재 동의 수
SELECT domain, COUNT(*) AS consented_cnt
FROM consent
WHERE consent_flag = 'Y' AND revoke_dt IS NULL
GROUP BY domain
ORDER BY consented_cnt DESC;

-- 현재 동의 고객 수 (중복 제거)
SELECT COUNT(DISTINCT global_id) AS consented_users
FROM consent
WHERE consent_flag = 'Y' AND revoke_dt IS NULL;
```

### 계열사 매핑 조회
```sql
-- 특정 고객의 계열사 ID 매핑 전체
SELECT domain, source_customer_id, match_type, active_flag
FROM customer_identity_map
WHERE global_id = 'G000000924';

-- 도메인별 매핑 건수
SELECT domain, COUNT(*) AS cnt, SUM(active_flag='Y') AS active_cnt
FROM customer_identity_map
GROUP BY domain
ORDER BY cnt DESC;
```

### PII 확인 (관리용)
```sql
-- PII 암호화 상태 확인 (3건 샘플)
SELECT pii_token, global_id,
       LEFT(customer_name_enc, 10) AS name_enc_prefix,
       LEFT(rrn_enc, 10) AS rrn_enc_prefix
FROM customer_pii_secure
LIMIT 3;

-- global_id로 PII 토큰 조회
SELECT pii_token FROM customer_pii_secure WHERE global_id = 'G000000924';
```

### 매칭 감사 로그
```sql
-- 최근 매칭 이력 20건
SELECT request_id, ls_user_id, matched_global_id, match_rule, match_score, result, request_dt
FROM matching_audit_log
ORDER BY request_dt DESC
LIMIT 20;

-- 특정 global_id 매칭 이력
SELECT * FROM matching_audit_log
WHERE matched_global_id = 'G000000924'
ORDER BY request_dt DESC;
```

---

## 2. Aurora MySQL (`lifesync360`)

### 추천 이력 조회
```sql
-- 특정 고객 최근 추천 이력 10건
SELECT h.hist_id, p.product_name, p.category_id, h.dynamic_score, h.dynamic_grade,
       h.action_code, h.recommended_at, h.clicked_flag, h.purchased_flag
FROM customer_recommend_history h
JOIN product_master p ON h.product_id = p.product_id
WHERE h.global_id = 'G000000924'
ORDER BY h.recommended_at DESC
LIMIT 10;

-- 특정 고객 CTR / CVR
SELECT
    COUNT(*) AS total_rec,
    SUM(clicked_flag = 'Y') AS clicks,
    SUM(purchased_flag = 'Y') AS purchases,
    ROUND(SUM(clicked_flag='Y') / COUNT(*) * 100, 1) AS ctr_pct,
    ROUND(SUM(purchased_flag='Y') / NULLIF(SUM(clicked_flag='Y'), 0) * 100, 1) AS cvr_pct
FROM customer_recommend_history
WHERE global_id = 'G000000924';
```

### 상품 조회
```sql
-- 등급별 활성 상품 목록 (priority 순)
SELECT p.product_id, p.product_code, p.product_name, p.target_grade,
       p.min_score, p.max_score, p.priority_rank,
       cm.company_code, cm.company_name, cat.category_code, cat.category_name
FROM product_master p
JOIN company_master cm ON p.company_id = cm.company_id
JOIN category_master cat ON p.category_id = cat.category_id
WHERE p.target_grade = 'VIP'
  AND p.active_flag = 'Y'
  AND (p.end_date IS NULL OR p.end_date >= CURDATE())
ORDER BY p.priority_rank
LIMIT 20;

-- 상품 상세 (옵션 포함)
SELECT p.product_name, p.description, p.target_grade, p.risk_level,
       o.option_name, o.option_value
FROM product_master p
LEFT JOIN product_option o ON p.product_id = o.product_id
WHERE p.product_id = 1;

-- 점수 범위로 추천 가능한 상품
SELECT p.product_id, p.product_name, p.target_grade, p.priority_rank,
       cm.company_code
FROM product_master p
JOIN company_master cm ON p.company_id = cm.company_id
WHERE p.active_flag = 'Y'
  AND p.min_score <= 84.7 AND p.max_score >= 84.7
ORDER BY p.priority_rank
LIMIT 10;
```

### 캠페인 조회
```sql
-- 등급별 활성 캠페인
SELECT campaign_id, campaign_name, target_grade, banner_title, banner_desc, start_date, end_date
FROM campaign_master
WHERE target_grade = 'GOLD'
  AND active_flag = 'Y'
  AND start_date <= CURDATE()
  AND (end_date IS NULL OR end_date >= CURDATE())
ORDER BY campaign_id;
```

### 통계 / 분석
```sql
-- 테이블별 행 수 빠른 확인
SELECT table_name, table_rows
FROM information_schema.tables
WHERE table_schema = 'lifesync360'
ORDER BY table_rows DESC;

-- 일별 추천 건수 추이 (최근 7일)
SELECT DATE(recommended_at) AS rec_date, COUNT(*) AS rec_cnt,
       SUM(clicked_flag='Y') AS clicks,
       SUM(purchased_flag='Y') AS purchases
FROM customer_recommend_history
WHERE recommended_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY DATE(recommended_at)
ORDER BY rec_date DESC;

-- 상품별 추천 TOP 10
SELECT p.product_name, cm.company_code, COUNT(*) AS rec_cnt,
       SUM(h.clicked_flag='Y') AS clicks,
       ROUND(SUM(h.clicked_flag='Y') / COUNT(*) * 100, 1) AS ctr_pct
FROM customer_recommend_history h
JOIN product_master p ON h.product_id = p.product_id
JOIN company_master cm ON p.company_id = cm.company_id
GROUP BY h.product_id, p.product_name, cm.company_code
ORDER BY rec_cnt DESC
LIMIT 10;

-- 등급별 추천 분포
SELECT dynamic_grade, COUNT(*) AS cnt,
       ROUND(COUNT(*) / SUM(COUNT(*)) OVER() * 100, 1) AS pct
FROM customer_recommend_history
GROUP BY dynamic_grade
ORDER BY cnt DESC;
```

### 추천 룰 / 교차판매 룰 조회
```sql
-- 등급별 추천 룰 조회
SELECT target_grade, action_code, category_code, min_score, max_score, priority_rank
FROM recommend_rule
WHERE target_grade = 'VIP' AND active_flag = 'Y'
ORDER BY priority_rank;

-- 교차판매 룰 (특정 카테고리 관심 시 추천할 카테고리)
SELECT base_category, target_category, priority_rank
FROM cross_sell_rule
WHERE base_category = 'HEALTHCARE' AND active_flag = 'Y'
ORDER BY priority_rank;
```

### 고객 행동 로그
```sql
-- 특정 고객 최근 행동 로그
SELECT page_type, banner_click, product_click, click_product_id, view_time
FROM customer_dashboard_log
WHERE global_id = 'G000000924'
ORDER BY view_time DESC
LIMIT 20;

-- 페이지 타입별 배너/상품 클릭률
SELECT page_type,
       COUNT(*) AS views,
       SUM(banner_click='Y') AS banner_clicks,
       SUM(product_click='Y') AS product_clicks
FROM customer_dashboard_log
WHERE view_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY page_type;
```

---

## 3. DynamoDB (`lifesync_customer_result`)

스키마: `HASH = global_id (S)` · `RANGE = update_time (S)`

### boto3 (Python)

```python
import boto3
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
table = dynamodb.Table('lifesync_customer_result')

# 단건 조회 (global_id + update_time 알 때)
resp = table.get_item(Key={'global_id': 'G000000924', 'update_time': '2026-05-22T10:00:00'})
item = resp.get('Item')

# 최신 기록 1건 (update_time DESC)
resp = table.query(
    KeyConditionExpression='global_id = :gid',
    ExpressionAttributeValues={':gid': 'G000000924'},
    ScanIndexForward=False,
    Limit=1
)
item = resp['Items'][0] if resp['Items'] else None

# 등급별 필터 스캔 (소량 테스트용 — 운영 대량 사용 지양)
resp = table.scan(
    FilterExpression='dynamic_grade = :grade',
    ExpressionAttributeValues={':grade': 'VIP'},
    Limit=100
)
items = resp['Items']
```

### AWS CLI

```bash
# 단건 조회
aws dynamodb get-item \
  --table-name lifesync_customer_result \
  --key '{"global_id":{"S":"G000000924"},"update_time":{"S":"2026-05-22T10:00:00"}}' \
  --region ap-northeast-2

# 특정 global_id의 모든 기록 (최신순)
aws dynamodb query \
  --table-name lifesync_customer_result \
  --key-condition-expression "global_id = :gid" \
  --expression-attribute-values '{":gid":{"S":"G000000924"}}' \
  --scan-index-forward false \
  --region ap-northeast-2

# 항목 수 확인 (느림, 테스트용)
aws dynamodb scan \
  --table-name lifesync_customer_result \
  --select COUNT \
  --region ap-northeast-2

# 테이블 메타 (빠름)
aws dynamodb describe-table \
  --table-name lifesync_customer_result \
  --query 'Table.{Items:ItemCount,SizeBytes:TableSizeBytes,Status:TableStatus}' \
  --region ap-northeast-2
```

---

## 빠른 연결 (CloudShell / 로컬)

```bash
# 온프렘 (ls-vpngw 경유)
ssh ansible@192.168.56.10
mysql -h 192.168.56.11 -u lifesync -p lifesync_onprem

# Aurora (CloudShell — VPN/Bastion 필요)
mysql -h auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com \
      -u <DB_USER> -p lifesync360
```
