# Admin Platform 쿼리·스키마 정합성 감사 (2026-05-23)

## 감사 범위

| 대상 | 파일 |
|------|------|
| 설계서 | `관리자_대시보드_설계서_V5_3.xlsx` (4 시트: dashboard / users / ai / ops) |
| 구현 | `admin-platform/app.py` (2,338 라인) |
| 스키마 레퍼런스 | `schema_reference.md` (On-Prem 8 테이블), `Aurora_Schema_Reference.md` (Aurora 12 테이블) |
| 샘플 데이터 | `results.csv` (DynamoDB `lifesync_customer_result` 50건) |

**파일 자체 syntax / 실행 오류는 없음.** 설계서 ↔ 코드 ↔ 실 스키마 3자 간 정합성 이슈만 정리.

---

## 🚨 Critical

### #1. Aurora에 존재하지 않는 테이블 4개를 코드/UI가 참조 중

`Aurora_Schema_Reference.md` 의 12개 테이블 목록에 없음.

| 코드/문서 위치 | 참조 테이블 | 영향 |
|---------------|-----------|------|
| `admin-platform/app.py:986` (`_aurora_pr_models`) | `ml_model_evaluation_daily` | AI Precision 카드 항상 빈 값 또는 except |
| `admin-platform/app.py:1488`, `app.py:1833` (`_ai_kpi4_from_aws`) | `customer_recommend_daily` | AI KPI CTR/CVR 카드 항상 빈 값 |
| `admin-platform/app.py:2264`, `app.py:2270` (신청 페이지) | `customer_product_application` | 신청 페이지 동작 불가 |
| `admin-platform/terms.md:95`, `admin-platform/templates/ai.html:236` | `model_performance_history` | UI 라벨에만 표시, 코드는 다른 이름, 실 DB 둘 다 없음 |

**원인**: 3개 모두 일배치 마트(daily aggregate). EMR/Glue 잡으로 생성되어야 하나 스키마 레퍼런스엔 DDL 정의 없음.

**권고**:
- 운영 환경에 실제로 있는지 우선 확인 (`SHOW TABLES LIKE '%_daily'` / `LIKE '%application%'`).
- (A) 마트 잡 정식 정의 → DDL + EMR Step + 스키마 레퍼런스 업데이트
- (B) 마트 없이 `customer_recommend_history`에서 직접 집계하도록 코드 수정

---

### #2. CVR 공식이 문서 3개끼리 충돌

| 출처 | CVR 정의 | 식 |
|------|---------|------|
| `관리자_대시보드_설계서_V5_3.xlsx` 대시보드/AI 시트 | **노출 대비** | `SUM(purchased)/COUNT(*)` |
| `Aurora_Schema_Reference.md:313` | **클릭 대비** | `SUM(purchased)/SUM(clicked)` |
| `admin-platform/app.py:1563` (`_stub_aurora_summary`) | 노출 대비 | `pur/total*100` ✅ 설계서 일치 |
| `admin-platform/app.py:1962` (`_ai_age_perf_2step`) | 클릭 대비 | `pur/clk*100` ❌ 설계서와 다름 |
| `admin-platform/app.py:1833` (`_ai_kpi4_from_aws`) | 마트 컬럼 신뢰 | `customer_recommend_daily.cvr` (마트 정의에 의존) |

**영향**: 같은 화면 다른 카드끼리 숫자가 어긋남.

**권고**: 비즈니스 합의(마케팅/운영) 후 모든 문서·코드 한 줄로 통일.

---

### #3. consent 도메인 표기 충돌 (약어 vs 풀네임)

| 출처 | 표기 |
|------|------|
| `schema_reference.md:138-145` (실 On-Prem `consent.domain`) | `BANK / CARD / SEC / INS / ONINS / HLT / HOS / WBL` (약어) |
| 설계서 Users 시트 4번 영역 | `BANK / CARD / INSURANCE / SECURITIES / HEALTHCARE / HOSPITAL / ONLINE_INSURANCE / WEARABLE` (풀네임) |

**영향**: S3 동의 스냅샷(`consent_snapshot_aggregator` Lambda) 출력이 어느 표기인지에 따라 어드민 동의 뱃지 표시가 통째로 깨질 수 있음.

**권고**: Lambda 출력 형태 확인 후 한 쪽으로 통일.

---

### #4. company_master 도메인 ≠ consent 도메인

| 출처 | 도메인 코드 |
|------|------------|
| `Aurora_Schema_Reference.md:40` (company_master.company_code) | `BANK / CARD / SEC / INS / ONINS / HLT / HEALTHCARE` (7개) |
| `schema_reference.md:138` (consent.domain) | `BANK / CARD / SEC / INS / ONINS / HLT / HOS / WBL` (8개) |

**불일치**: `HOS`(병원) / `WBL`(웨어러블) 는 동의는 받지만 `company_master`에 회사 row가 없음. `HLT` ↔ `HEALTHCARE` 도 동일 회사인지 별도인지 모호.

**권고**: 회사 마스터에 HOS/WBL 회사 row 추가 또는 매핑 테이블 신설.

---

## 🟡 High (설계 자체 결함 또는 의도성 검증 필요)

### #5. `_ai_age_perf_2step` CVR 식 불일치

- 위치: `admin-platform/app.py:1962`
- 식: `cvr = round(pur * 100.0 / clk, 1) if clk else 0` (클릭 대비)
- 같은 코드 다른 함수(`_stub_aurora_summary` 1563)는 노출 대비
- → **#2 결정에 따라 한 줄 수정**

---

### #6. cross_sell_rule 개인화 누락

- 위치: `admin-platform/app.py:1264-1270`
- 현재 쿼리:
  ```sql
  FROM cross_sell_rule r
  WHERE r.active_flag = "Y"
  ORDER BY r.priority_rank ASC
  LIMIT 3
  ```
- 설계서 (Users 시트 7번): "보유 상품 X → 추천 상품 Y 규칙"
- 실 스키마 (`Aurora_Schema_Reference.md:251-258`): `cross_sell_rule(base_category, target_category)` — base_category 컬럼 **존재함**
- **현재 코드는 사용자 보유 상품을 무시**하고 priority_rank 상위 3개만 일괄 반환 → 모든 고객에게 같은 교차 추천

**권고 수정안**:
```sql
SELECT r.target_category, ...
FROM cross_sell_rule r
WHERE r.active_flag='Y'
  AND r.base_category IN (
    SELECT cat.category_code
    FROM customer_recommend_history h
      JOIN product_master p   ON h.product_id=p.product_id
      JOIN category_master cat ON p.category_id=cat.category_id
    WHERE h.global_id=%s AND h.purchased_flag IN ('Y','1')
  )
ORDER BY r.priority_rank ASC LIMIT 3
```

---

### #7. DynamoDB Scan 가정의 운영 정책 의존성

| 위치 | 가정 | 검증 |
|------|------|------|
| `app.py:1543`, `app.py:1844-1847` | `Scan(Limit=1)` 결과의 `update_time` = "가장 최근" | DDB Scan은 정렬 무보장. 단, `results.csv` 50건 모두 `update_time` 동일 → 현재 batch 정책상은 우연히 동작 |
| `app.py:1856-1862` (`_ai_kpi4_from_aws` 분석 대상 고객) | Scan COUNT = 고객 수 | 테이블 키 `global_id` HASH + `update_time` RANGE → 1고객 N row 가능. `results.csv` 샘플은 1고객 1row → OK |
| `app.py:943` (`_ddb_grade_dist`) | 등급 분포 row 단위 집계 | 1고객 1row 정책 의존 |
| `app.py:1000`, `app.py:2025` (`_ddb_score_histogram_for_ai`) | dynamic_score 히스토그램 row 단위 집계 | 동일 |

**현 상태**: results.csv 기준 운영상 "전 고객 매일 한 batch에 덮어쓰기" 정책이 유지되는 한 의도대로 작동.

**잠재 위험**: 일부 고객만 incremental update되거나 history 누적으로 정책이 바뀌면 즉시 깨짐.

**권고**:
- 옵션 A: 정책 명문화 (운영 문서에 "1고객 1row 덮어쓰기" 명시)
- 옵션 B: `update_time` GSI 만들고 `Query(ScanIndexForward=False, Limit=1)` 로 전환
- 옵션 C: 별도 `analytics_meta` 테이블(또는 메타 키)에 마지막 batch 시각 기록 → GetItem

---

## 🟢 Medium

### #8. `master_customer.last_login_dt` 컬럼 부재 (설계서 오류)

- 설계서 Users 시트 2번 영역: "가입 · 마스터 | last_login_dt | master_customer"
- 실제 `schema_reference.md:47-54` `master_customer`: `first_created_dt`, `last_updated_dt` 만 존재 (`last_login_dt` 없음)
- `last_login_dt` 는 `schema_reference.md:37` **users 테이블**에 있음

**영향**: 코드는 onprem Lambda 위임이라 추상화돼서 안 드러나지만, 설계서 자체가 잘못된 테이블을 가리킴.

**권고**: 설계서 Users 시트 수정 (`master_customer.last_login_dt` → `users.last_login_dt`).

---

### #9. `clicked_flag IN ('Y','1')` 패턴

- 위치: `app.py:1555-1556`, `app.py:1898`, `app.py:1948-1949` 등 다수
- 설계서: `clicked_flag='Y'` 단일 값
- `Aurora_Schema_Reference.md:297` `customer_recommend_history.clicked_flag`: `CHAR(1) Y/N (DEFAULT N)`
- 코드는 `('Y','1')` 둘 다 허용

**영향**: 데이터에 `'1'` 형태가 실제로 들어오면 매칭, 안 들어오면 무해. 다만 "왜 둘 다인지" 컨텍스트가 코드에 없음 → 마이그레이션 잔재일 가능성.

**권고**: 실 데이터 한 번 샘플링 (`SELECT DISTINCT clicked_flag FROM customer_recommend_history`) 후 한 쪽으로 정리.

---

## ✅ 검증 OK

| 항목 | 위치 | 근거 |
|------|------|------|
| KPI 1~3 onprem Lambda 위임 | `app.py:1533` | 설계서 SQL은 ls-db 내부 명세, 외부는 Lambda `count_master_customer` 등 호출 — 정합 |
| dashboard CTR/CVR 공식 | `app.py:1562-1563` | 노출 대비 — 설계서 일치 |
| 7일 추이 `customer_recommend_history` GROUP BY DATE | `app.py:880-889` | 설계서 일치, `idx_hist_date` 사용 가능 |
| 상품 TOP10 3-way JOIN | `app.py:912-922` | `category_master` / `product_master` JOIN 컬럼 일치 |
| `_aurora_action_code_rec_data` | `app.py:967-972` | `customer_recommend_history.action_code` 컬럼 실재 (`Aurora_Schema_Reference.md:295`) |
| `_aurora_customer_insight` | `app.py:1040-1045` | COUNT DISTINCT global_id + AVG CTR/CVR + COUNT(*) — 컬럼·테이블 모두 실재 |
| `_ddb_feature_importance` | `app.py:1991-2008` | `vip_prob / rec_prob / signup_prob` AVG 프록시 — DDB 필드 `results.csv`에서 확인됨 |
| `api_customer_ai_result` Query | `app.py:2097` | composite key Query (KeyCondition + ScanIndexForward=False) — Scan과 달리 Query는 정렬 보장됨 ✅ |
| Redis Personalized ZREVRANGE | `app.py:2111` | 설계서 일치 (별건: HANDOFF.md 의 platform-side `SETEX` vs admin-side `ZREVRANGE` 타입 불일치는 다른 트랙) |

---

## results.csv 데이터 검증 노트

- 50건 샘플 전부 `update_time = 2026-05-15 03:29:17.270935 UTC` 로 **완전 동일**
  → "전 고객 매일 한 batch에 덮어쓰기" 운영 정책 추정 가능
- 같은 `global_id` 중복 없음 → 1고객 1row 정책 추정 가능
- DDB 필드: `dynamic_grade, dynamic_score, health_score, next_best_action, rec_prob, signup_prob, source, ttl, vip_prob` — 코드 사용 필드와 일치
- `dynamic_grade` 분포: CARE 47 / SILVER 1 / BASIC 1 / 기타 1 (50건 기준) → 모델 캘리브레이션 이슈, 코드와 무관

---

## 후속 액션 우선순위

| 순위 | 항목 | 액션 | 예상 작업량 |
|------|------|------|------------|
| 1 | 마트 테이블 3개 실재 확인 | `SHOW TABLES LIKE '%_daily'` / `LIKE '%application%'` | 5분 |
| 2 | CVR 공식 일원화 | 비즈니스 합의 + 4 위치 동기화 | 합의 후 30분 |
| 3 | `cross_sell` 개인화 (#6) | SQL 1개 교체 + 단건 테스트 | 30분 |
| 4 | `_aurora_pr_models` 테이블명 (#1) | 마트 실재 여부 결정 후 | 5분 |
| 5 | `_ai_age_perf_2step` CVR (#5) | 한 줄 수정 | 5분 |
| 6 | consent 도메인 통일 (#3) | Lambda 출력 확인 → 매핑 추가 또는 설계서 수정 | 30분 |
| 7 | DDB Scan 정책 명문화 또는 GSI 도입 (#7) | 운영 정책 결정 후 | 명문화 10분 / GSI 도입 2~3h |
| 8 | 설계서 `master_customer.last_login_dt` 수정 (#8) | 엑셀 한 셀 | 1분 |
| 9 | `clicked_flag` 표기 통일 (#9) | 데이터 샘플링 후 결정 | 15분 |

**1번부터 시작 권장** — 나머지 7개는 1번 결과(마트가 실재하는지)에 따라 액션이 갈라짐.

---

## 검증 시 사용한 쿼리·도구 메모

- xlsx 추출: `openpyxl` (`python -c "import openpyxl; ..."`)
- 코드 SQL 추출: `Grep` 패턴 `SELECT|FROM |WHERE|GROUP BY|...`
- 스키마 대조: 라인 단위 매핑 (file_path:line_number)
- 실 DB 접속 검증: **미수행** — 후속 액션 #1 에서 수행 예정

---

## 부록 A. 후속 액션 #1 진행 가이드 — 마트 테이블 실재 확인

### 사전 점검 (코드 동작 확정)

| 함수 | Exception 시 동작 | 화면 표시 |
|------|------------------|----------|
| `_ai_kpi4_from_aws` (`app.py:1832-1841`) | `pass` → cards value 그대로 `'-'` | "-" |
| `_aurora_pr_models` (`app.py:993-994`) | `return []` | 빈 차트 (mockup 미사용) |
| `api_customer_application_list` (`app.py:2290-2291`) | `return jsonify({'error': ...}), 500` | HTTP 500 |

→ **3개 함수 모두 mockup fallback 없음**. 화면에 정상 숫자가 떴다면 마트가 실재한다는 뜻. 0건/빈 차트/500이 떴다면 마트가 없거나 비어 있는 것.

### 확인할 테이블 4개

```
ml_model_evaluation_daily       (app.py:986 — _aurora_pr_models)
customer_recommend_daily        (app.py:1833 — _ai_kpi4_from_aws)
customer_product_application    (app.py:2264 — 신청 페이지)
model_performance_history       (terms.md / ai.html UI 라벨 — 코드 미사용)
```

확인 대상 스키마: `lifesync360` (Aurora)

---

### 옵션 A — RDS Data API (가장 빠름. Data API 활성화 필요)

```bash
# 1) Aurora cluster ARN
CLUSTER_ARN=$(aws rds describe-db-clusters \
  --query "DBClusters[?contains(DBClusterIdentifier,'lifesync')].DBClusterArn|[0]" \
  --output text)
echo "$CLUSTER_ARN"

# 2) Secret ARN
SECRET_ARN=$(aws secretsmanager describe-secret \
  --secret-id /lifesync/dev/db/master \
  --query ARN --output text)
echo "$SECRET_ARN"

# 3) SHOW TABLES 실행
aws rds-data execute-statement \
  --resource-arn "$CLUSTER_ARN" \
  --secret-arn "$SECRET_ARN" \
  --database lifesync360 \
  --sql "SHOW TABLES" \
  --query "records[*][0].stringValue" --output table
```

**판별**:
- 정상 출력 → 출력된 테이블 리스트에서 위 4개 검색
- `BadRequestException: HttpEndpoint is not enabled for the DB cluster` → Data API 꺼져 있음. 옵션 B 로

(필요 시 Data API 켜기: `aws rds modify-db-cluster --db-cluster-identifier <id> --enable-http-endpoint --apply-immediately` — 약 1분 소요. 단, 운영용 클러스터에 즉시 적용은 영향 평가 후)

---

### 옵션 B — SSM Send-Command (Aurora VPC 내 EC2 경유)

Aurora 가 Platform VPC 에 있으니, 같은 VPC 또는 TGW 연결된 VPC 의 mysql client 보유 EC2 에서 실행.

```bash
# 1) Aurora 엔드포인트
aws rds describe-db-clusters \
  --query "DBClusters[?contains(DBClusterIdentifier,'lifesync')].[DBClusterIdentifier,Endpoint,Port]" \
  --output table

# 2) 현재 running 인 lifesync EC2 목록
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=lifesync-*" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].[InstanceId,Tags[?Key=='Name']|[0].Value,VpcId]" \
  --output table

# 3) 후보 instance 1개 골라 SSM ping
aws ssm describe-instance-information \
  --filters "Key=InstanceIds,Values=<instance-id>" \
  --query "InstanceInformationList[*].[InstanceId,PingStatus]" --output table
#   PingStatus=Online 이어야 SSM SendCommand 가능

# 4) SHOW TABLES 실행 (mysql client 깔려 있다고 가정)
INSTANCE_ID=<위에서 고른 id>

CMD_ID=$(aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "Aurora SHOW TABLES audit" \
  --parameters 'commands=[
    "SECRET=$(aws secretsmanager get-secret-value --secret-id /lifesync/dev/db/master --query SecretString --output text)",
    "USER=$(echo $SECRET | jq -r .username)",
    "PASS=$(echo $SECRET | jq -r .password)",
    "HOST=$(echo $SECRET | jq -r .host)",
    "mysql -h $HOST -u $USER -p$PASS lifesync360 -e \"SHOW TABLES; SELECT COUNT(*) FROM customer_recommend_daily; SELECT COUNT(*) FROM ml_model_evaluation_daily; SELECT COUNT(*) FROM customer_product_application; SELECT COUNT(*) FROM model_performance_history;\" 2>&1"
  ]' \
  --query "Command.CommandId" --output text)
echo "$CMD_ID"

# 5) 결과 (Status=Success 면 stdout 회수)
sleep 5
aws ssm get-command-invocation \
  --command-id "$CMD_ID" \
  --instance-id "$INSTANCE_ID" \
  --query "[Status, StandardOutputContent, StandardErrorContent]" --output text
```

**EC2 에 mysql client 가 없을 때**: 한 줄 추가

```bash
"sudo yum install -y mysql || sudo apt-get install -y mysql-client || true",
```

위 commands 배열의 `SECRET=...` 앞에 끼워 넣으면 됨.

**EC2 가 SSM Online 이 아닐 때**: IAM Instance Profile (AmazonSSMManagedInstanceCore) / SSM VPC Endpoint SG / NAT GW 라우팅 순서로 점검 (SSM 트러블슈팅 절차 참조).

---

### 옵션 C — AWS 콘솔 RDS Query Editor (수동, 가장 빠른 1회성)

1. AWS 콘솔 → RDS → 좌측 메뉴 "쿼리 에디터" (Query Editor)
2. 데이터베이스 연결:
   - 클러스터: `lifesync-*` 선택
   - 인증: Secrets Manager → `/lifesync/dev/db/master`
   - DB 이름: `lifesync360`
3. 실행:
   ```sql
   SHOW TABLES;
   ```
4. 4개 테이블 존재 시 행 수까지 확인:
   ```sql
   SELECT 'customer_recommend_daily' AS t, COUNT(*) FROM customer_recommend_daily
   UNION ALL SELECT 'ml_model_evaluation_daily', COUNT(*) FROM ml_model_evaluation_daily
   UNION ALL SELECT 'customer_product_application', COUNT(*) FROM customer_product_application
   UNION ALL SELECT 'model_performance_history', COUNT(*) FROM model_performance_history;
   ```

→ Query Editor 도 결국 RDS Data API 위에서 동작하므로 Data API 꺼져 있으면 "쿼리 에디터를 사용할 수 없음" 안내. 그 경우 옵션 B 로.

---

### 결과 해석 → 다음 액션 분기

| 결과 | 다음 액션 |
|------|----------|
| 4개 다 존재 + 행 있음 | 감사 #1 해소. `Aurora_Schema_Reference.md` 에 4개 테이블 추가 (DDL + 행 수). UI 라벨(`terms.md` / `ai.html`)이 가리키는 `model_performance_history` 와 코드가 쓰는 `ml_model_evaluation_daily` 가 별개 테이블인지 동일 데이터인지 추가 확인 |
| 4개 다 존재 + 행 0 | 마트 잡(EMR/Glue) 가 멈춰 있음. CloudWatch Logs 에서 마지막 실행 시각 확인, 잡 트리거 |
| 일부만 존재 | 누락 테이블 DDL 작성 + 마트 잡 추가. 동시에 `Aurora_Schema_Reference.md` 업데이트 |
| 4개 다 없음 + 화면에 숫자 떴다 | 데이터 출처 재추적 — 다른 함수가 채워주거나 클라이언트 캐시일 가능성. `app.py` 전역 변수 / 다른 마트 / SSR 캐시 검색 |
| 4개 다 없음 + 화면에 `-` 또는 빈 차트 | 감사 #1 그대로 유효. 마트 잡 신설 또는 history 직접 집계로 코드 교체 (감사 #1 권고 B) |

---

### 마트 발견 시 추가로 확인할 컬럼 (DDL 정밀 매칭)

테이블이 있으면 컬럼 스키마까지 봐야 코드의 `SELECT` 가 정확히 맞는지 검증 가능:

```sql
DESCRIBE customer_recommend_daily;
-- 코드(app.py:1833)는 ctr, cvr, date 컬럼을 SELECT — 이 3개 컬럼 존재 여부 확인

DESCRIBE ml_model_evaluation_daily;
-- 코드(app.py:984-986)는 model_name, precision_score, eval_date 컬럼을 SELECT — 3개 존재 여부

DESCRIBE customer_product_application;
-- 코드(app.py:2270-2280)는 application_id, global_id, ls_user_id, product_id, status,
--   reviewer_id, reviewed_at, applied_at, updated_at 컬럼 사용 — 9개 존재 여부
```

---

### 체크리스트 (실행 순서)

- [ ] 옵션 A 시도 → Data API 응답 확인
- [ ] (A 실패 시) 옵션 B 또는 C 로 전환
- [ ] `SHOW TABLES` 출력에서 4개 테이블 grep
- [ ] 존재하는 테이블에 대해 `SELECT COUNT(*)` 로 행 수 확인
- [ ] 존재하는 테이블에 대해 `DESCRIBE` 로 컬럼 매칭
- [ ] 결과를 이 문서 "결과 해석" 표의 어느 케이스에 해당하는지 기록
- [ ] 해당 액션 진행

---

*내부 감사*
*감사 일시: 2026-05-23*
*감사 대상 commit: 1bfb142 (main 브랜치, 로컬 미커밋 변경 포함)*
