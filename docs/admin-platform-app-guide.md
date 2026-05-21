# admin-platform app.py 구조 가이드

파일 경로: `admin-platform/app.py`  
포트: 5001  
역할: 관리자 대시보드. 인프라 모니터링, 고객 360도 조회, AI 추천 성과 분석, 운영 상태 확인.

---

## 1. 시작 시 초기화 순서

앱 시작 시 아래 순서로 환경변수 주입. 이미 set된 값은 덮어쓰지 않음.

```
① _bootstrap_dotenv()
   admin-platform/.env 또는 .env.local 파일 로드
   로컬 개발 전용. 운영/EC2에선 이 파일 없어도 됨

② _bootstrap_secrets()
   Secrets Manager /lifesync/dev/db/master 에서 AURORA_HOST, DB_USER, DB_PASS, REDIS_HOST 주입
   SSM Parameter Store /lifesync/gcp_project_id 에서 GCP_PROJECT_ID 주입
   AWS 자격증명 없으면 pass (IAM role 없는 로컬 개발 환경 대응)

③ wearable_engine.load_initial(mock_wearable_batch.json)
   웨어러블 시뮬레이션 데이터 메모리 적재
   wearable_engine.start_loop(interval=1.0) — 1초 tick으로 심박/혈압 등 변동 시뮬레이션
   파일 없으면 FileNotFoundError pass (admin 부팅은 계속)
```

**트러블슈팅**: Secrets Manager 로드 실패 시 `.env` 파일이 없으면 DB 연결 실패. `AURORA_HOST` 환경변수가 직접 설정됐는지 확인.

---

## 2. 환경변수 의존성

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AURORA_HOST` | — | Aurora MySQL 엔드포인트. 없으면 DB 연결 실패 |
| `DB_USER` | `admin` | Aurora 사용자 |
| `DB_PASS` | `ChangeMe123!` | Aurora 비밀번호 |
| `DB_NAME` | `lifesync360` | 데이터베이스 |
| `REDIS_HOST` | — | ElastiCache 엔드포인트. 없으면 Redis 기능 비활성 |
| `REDIS_PORT` | `6379` | Redis 포트 |
| `DYNAMO_TABLE` | `lifesync_customer_result` | 고객 AI 결과 테이블 |
| `DDB_SEGMENT_TABLE` | `analytics_segment_performance` | 세그먼트 분석 테이블 |
| `DDB_DEMOGRAPHIC_TABLE` | `analytics_demographic_information` | 인구통계 분석 테이블 |
| `AWS_REGION` | `ap-northeast-2` | boto3 리전 |
| `ONPREM_QUERY_LAMBDA` | `''` (빈 문자열) | 온프레미스 조회 Lambda. 비어 있으면 `_call_onprem` 이 빈 dict 반환 |
| `LIFESYNC_RAW_S3_BUCKET` | — | raw S3 버킷. 없으면 S3 관련 기능 비활성 |
| `INGESTION_STREAM_NAME` | `lifesync-kinesis-wearable-stream` | Kinesis 스트림명 |
| `GLUE_JOB_PHYSICAL_NAME` | `lifesync-etl` | Glue Job명 |
| `GLUE_SCHEDULE_RULE` | `lifesync-daily-etl-rule` | EventBridge 규칙명 |
| `GCP_PROJECT_ID` | — | GCP 프로젝트 ID. 없으면 GCP 기능 전체 비활성 |
| `GCP_BQ_DATASET` | `lifesync_curated` | BigQuery 데이터셋 |
| `GCP_VERTEX_LOCATION` | `asia-northeast3` | Vertex AI 리전 |
| `ADMIN_USER` | `admin` | 관리자 로그인 아이디 |
| `ADMIN_PASSWORD` | `admin123` | 관리자 로그인 비밀번호 |
| `SECRET_KEY` | `admin-dev-secret-32bytes-lifesync!!` | Flask session 서명 키. 운영 시 반드시 교체 |
| `LAMBDA_PREFIX_FILTER` | `lifesync-` | Lambda 자동 발견 prefix |

---

## 3. 인증

- Flask session 기반 (`session['logged_in']`). JWT 아님.
- `login_required` 데코레이터로 모든 페이지/API 보호.
- `POST /login` → form username/password 비교 → session 설정.
- **운영 주의**: `ADMIN_USER`, `ADMIN_PASSWORD`, `SECRET_KEY` 모두 환경변수로 교체 필수.

---

## 4. DB/인프라 연결 헬퍼

### `get_db()`
- Aurora MySQL 연결 (pymysql). 매 호출마다 새 연결.
- `cursorclass=DictCursor` — dict 형태 반환.
- **커넥션 풀 없음**: admin은 요청 빈도가 낮으므로 허용. 고빈도 폴링 API는 주의.

### `get_dynamo_table()`
- `DYNAMO_TABLE` 환경변수 (`lifesync_customer_result`) 싱글턴.
- 이 테이블 schema: `global_id` (HASH) + `update_time` (RANGE). 반드시 Query 사용.

### `_get_lambda()`
- Lambda client 싱글턴. **타임아웃 설정 중요**:
  - `connect_timeout=3`, `read_timeout=20`, `max_attempts=1`.
  - Lambda 응답 없어도 3초 대기 후 종료 → 화면 hang 방지.

### `_get_redis()`
- Redis 싱글턴. `socket_connect_timeout=3`, `socket_timeout=3`.
- `REDIS_HOST` 없으면 None 반환 → 호출부에서 `if r is None: return {}` 처리.

### `_boto(service)`
- boto3 클라이언트 캐시 dict. 서비스명 key로 재사용.
- `rds`, `dynamodb`, `elasticache`, `ecs`, `elbv2`, `s3`, `cloudwatch`, `lambda`, `kinesis`, `glue`, `emr`, `ec2`, `events` 등 사용.

### `_call_onprem(action, **kwargs)`
- `ONPREM_QUERY_LAMBDA` 가 비어 있으면 즉시 `{}` 반환 (VPN 미연결 상태 안전 처리).
- 타임아웃은 `_get_lambda()` 의 3/20초 설정 적용.
- **실패 시**: 빈 dict 반환 (RuntimeError 발생 안 함) — 플랫폼 앱과 다름.

---

## 5. 모니터링 헬퍼 함수

모두 실패 시 빈 list/dict 반환. 화면에는 `-` 또는 `ERR` 상태로 표시됨.

### AWS 리소스 상태

| 함수 | 호출 서비스 | 반환 |
|------|------------|------|
| `_ping_cloud_status()` | RDS/DynamoDB/ElastiCache/ECS/ALB/S3 describe | 6개 서비스 `{service, state, note}` list |
| `_ping_s3_ingestion()` | CloudWatch S3 NumberOfObjects + S3 list_objects_v2 | raw bucket 파일 수, 오늘 적재 수, IoT 수, 용량, 최근 업로드 |
| `_ping_domain_flow()` | S3 list_objects_v2 (도메인 prefix 별) + Kinesis CW | 7개 도메인 적재 현황 (BANK/CARD/INSURANCE/SECURITIES/HEALTHCARE/HOSPITAL/WEARABLE) |
| `_ping_vm_status()` | EC2 describe_vpcs + describe_instances | `lifesync-*-vpc` 내 EC2 목록 (deploy_group 자동 분류) |
| `_boost_vm_cpu()` | CW get_metric_data (EC2 CPUUtilization 10분) | vm_status rows에 cpu_pct 보강. 1회 batch 호출 |
| `_list_lifesync_lambdas()` | Lambda list_functions paginator | `lifesync-` prefix Lambda 이름 목록 |
| `_ping_lambda_metrics()` | CW Invocations/Errors/Duration (1h) | 함수별 `{fn, invocations_1h, errors_1h, avg_duration_ms}` |
| `_ping_glue_last_run()` | Glue get_job_runs MaxResults=1 | 최근 실행 `{state, started_at, completed_at, duration_sec}` |
| `_ping_next_batch()` | EventBridge describe_rule | 스케줄 표현식 (next fire time은 AWS API 없어서 표시 불가) |
| `_ping_kinesis()` | Kinesis describe_stream_summary + CW IteratorAgeMilliseconds | 스트림 상태 + 처리 지연 |
| `_ping_emr()` | EMR list_clusters | RUNNING/WAITING 상태 클러스터 목록 |

### 네트워크 연결

| 함수 | 반환 |
|------|------|
| `_ping_tgw()` | TGW ID + 상태 + attachment 수 |
| `_ping_vpn()` | VPN 터널 목록 (BGP ASN, 상태, peer IP). VgwTelemetry 기반 |
| `_ping_vpc_peering()` | VPC Peering 연결 목록 (requester/accepter VPC) |

### Wearable 실시간

| 함수 | 반환 |
|------|------|
| `_ping_wearable_realtime()` | CW LifeSync/Wearable namespace 6개 metric 5분 평균 |
| `_ping_wearable_metrics()` | CW LifeSync/Wearable 7개 metric (heart_rate/bp_sys/bp_dia/spo2/steps/activity_kcal/alerts) |
| `_ping_local_lab()` | onprem Lambda `local_lab_status` action → VM/서비스 상태 |

---

## 6. GCP 연동 헬퍼

GCP_PROJECT_ID 없으면 모든 함수가 빈 list/dict 반환 (인증 없이 안전).

| 함수 | 필요한 GCP 권한 | 반환 |
|------|----------------|------|
| `_get_bq()` | BigQuery Data Viewer | BigQuery Client 싱글턴 |
| `_init_aip()` | Vertex AI 접근 | aiplatform 초기화 여부 |
| `_get_mon()` | Monitoring Viewer | MetricServiceClient 싱글턴 |
| `_stub_gcp_status()` | Monitoring Viewer | BigQuery/Vertex AI/Cloud Run 서비스 상태 |
| `_stub_vertex_metrics()` | Vertex AI Viewer | 최신 모델 Precision/Recall 평가 메트릭 |
| `_stub_feature_importance()` | BigQuery | `lifesync_curated.ai_feature_table` 컬럼별 평균/표준편차 |
| `_stub_bigquery_analytics(kind)` | BigQuery | `recommendation_mart` / `v_customer_summary` / `vip_prediction_result` 중 1종 |

**인증 방법**: `GOOGLE_APPLICATION_CREDENTIALS` 환경변수 (ADC) 또는 Workload Identity Federation.

---

## 7. Aurora 분석 헬퍼

모두 `get_db()` 호출. 실패 시 빈 list/dict 반환.

| 함수 | 쿼리 대상 테이블 | 반환 |
|------|----------------|------|
| `_aurora_recommend_trend_7day()` | `customer_recommend_history` GROUP BY DATE | 7일 `{date, recommended, clicked, purchased, ctr, cvr}` list |
| `_aurora_recommend_top10()` | `customer_recommend_history` JOIN product/category | 상품별 추천 TOP10 `{rank, product, category, recommended, ctr, cvr}` |
| `_aurora_action_code_rec_data()` | `customer_recommend_history` GROUP BY action_code | action_code별 추천 수 |
| `_aurora_pr_models()` | `ml_model_evaluation_daily` | 모델별 Precision/Recall |
| `_aurora_category_ctr_donut()` | `customer_recommend_history` JOIN product/category | 카테고리별 도넛 `{name, pct, ctr, color}` |
| `_aurora_customer_insight()` | `customer_recommend_history` 7일 집계 | 활성 고객 수 / 평균 CTR / CVR / 총 추천 건수 |
| `_stub_aurora_summary()` | customer_recommend_history + customer_dashboard_log | 9개 KPI 카드 값 |
| `_stub_aurora_history(gid)` | `customer_recommend_history` WHERE global_id | 고객별 추천 이력 50건 |
| `_stub_aurora_activity(gid)` | `customer_dashboard_log` WHERE global_id | 고객별 행동 로그 50건 |

---

## 8. DynamoDB 분석 헬퍼

Scan 호출 포함 → **운영 데이터 많아지면 비용/성능 주의**.

| 함수 | Scan 여부 | 반환 |
|------|----------|------|
| `_ddb_score_distribution()` | Scan (dynamic_score) | 0~100 10구간 히스토그램 |
| `_ddb_prob_distribution()` | Scan (vip_prob/signup_prob/rec_prob) | 3개 확률 평균 + 0.0~1.0 히스토그램 |
| `_ddb_grade_dist()` | Scan (dynamic_grade) | 등급별 분포 (count, pct, color) |
| `_ddb_score_histogram_for_ai()` | Scan (dynamic_score) | 5구간 히스토그램 (ai.html 차트용) |
| `_ddb_feature_importance()` | Scan (vip_prob/rec_prob/signup_prob) | 3개 확률 평균 → feature importance 프록시 |
| `_ddb_query_today(table)` | Query (snapshot_date = 오늘) | analytics_* 테이블 오늘자 snapshot. 없으면 3일 fallback |

---

## 9. 웨어러블 엔진 (`wearable_engine` 모듈)

- `mock_wearable_batch.json` 로드 → 메모리 내 배치 데이터
- `start_loop(interval=1.0)` — background thread, 1초마다 심박/혈압/SpO2 등 랜덤 변동
- `snapshot()` — 현재 상태 dict 반환 `{kpi:[...5], red:[...], yellow:[...], device:[...]}`

**운영 전환 시**: Kinesis consumer Lambda로 교체 예정. 현재는 mock 데이터 기반 시뮬레이션.

---

## 10. 페이지 라우트

| 경로 | 템플릿 | SSR 데이터 | JS 폴링 API |
|------|--------|-----------|------------|
| `/dashboard` | `dashboard.html` | KPI 9개 빈 값, cloud3 구조만 | `/api/dashboard/summary`, `/api/dashboard/cloud3`, `/api/s3/status`, `/api/dashboard/uploads` |
| `/users?q=` | `users.html` | consent gate → profile → 추천/활동 로그 SSR | 없음 (SSR 전체) |
| `/users/<global_id>` | `user_detail.html` | DDB + S3 consent + Aurora 이력 SSR | 없음 |
| `/ai` | `ai.html` | KPI4 + 7일 추이 + top10 + 도넛 + 등급 분포 SSR | `/api/ai/kpi4`, `/api/ai/chart/trend`, `/api/ai/chart/donut`, `/api/ai/chart/age`, `/api/ai/chart/histogram` |
| `/ops` | `ops.html` | Wearable snapshot SSR, 네트워크 카드 빈 값 | `/api/datavpc/status`, `/api/vm/platform`, `/api/vm/group`, `/api/vm/wearable`, `/api/network/tgw`, `/api/network/vpn` |

**SSR vs JS 폴링 원칙**: 5초+ 걸리는 AWS API는 SSR에서 제외, JS 폴링으로 비동기 처리. Aurora 단순 쿼리 (< 1s)는 SSR 포함.

---

## 11. API 라우트 전체 목록

### Dashboard (`/dashboard` 페이지용)
| 경로 | 함수 | 설명 |
|------|------|------|
| `/api/dashboard/summary` | `_stub_aurora_summary()` | 9개 KPI (onprem Lambda 3개 + DDB + Aurora 5개 + Redis) |
| `/api/dashboard/cloud3` | `_cloud3_from_aws()` | AWS/GCP/On-Prem 3카드 + 서비스 details |
| `/api/s3/status` | `_s3_status_cards()` | S3 적재 5카드 |
| `/api/dashboard/uploads` | `_uploads_from_s3(10)` | 최근 업로드 10건 |
| `/api/cloud/status` | `_ping_cloud_status()` + GCP | AWS+GCP 종합 |

### Customer 360 (`/users` 페이지용)
| 경로 | 설명 |
|------|------|
| `/api/customer/profile/<gid>` | onprem `get_profile` + S3 consent 스냅샷 |
| `/api/customer/ai-result/<gid>` | DDB lifesync_customer_result 최신 1건 |
| `/api/customer/recommend/<gid>` | Redis ZREVRANGE `rec:{gid}` TOP3 |
| `/api/customer/history/<gid>` | Aurora customer_recommend_history 50건 |
| `/api/customer/activity/<gid>` | Aurora customer_dashboard_log 50건 |

### AI 추천 성과 (`/ai` 페이지용)
| 경로 | 설명 |
|------|------|
| `/api/ai/kpi4` | 4개 KPI (CTR/CVR/확률 평균/DDB 대상 수) |
| `/api/ai/chart/trend` | 7일 추이 SVG fragment (Jinja2 partial) |
| `/api/ai/chart/donut` | 카테고리별 도넛 SVG fragment |
| `/api/ai/chart/age` | 연령대별 추천 성과 진행바 (onprem 2-step → DDB fallback) |
| `/api/ai/chart/histogram` | dynamic_score 5구간 히스토그램 |
| `/api/ai/summary` | AI 분포 + Vertex AI 평가 종합 |
| `/api/ai/recommend-stats` | CTR/CVR + 7일 추이 + 세그먼트 종합 |
| `/api/admin/recommend-trend` | Aurora 7일 추이 JSON |
| `/api/admin/segment-performance` | DDB analytics_segment_daily (?dim=gender 등) |
| `/api/admin/demographic-summary` | DDB analytics_demographic_daily |
| `/api/bigquery/analytics` | BQ 마트 (?kind=recommendation_mart 등) |

### 운영 모니터링 (`/ops` 페이지용)
| 경로 | 설명 |
|------|------|
| `/api/datavpc/status` | S3/Kinesis/Glue/EMR 통합 상태 (DataVPC 4종) |
| `/api/vm/platform` | Platform VPC EC2 |
| `/api/vm/group` | Group VM EC2 |
| `/api/vm/wearable` | Wearable VM + CW 메트릭 |
| `/api/kinesis/status` | Kinesis 스트림 단건 |
| `/api/emr/status` | EMR 클러스터 목록 |
| `/api/network/tgw` | Transit Gateway + attachments |
| `/api/network/vpn` | VPN 터널 상태 |
| `/api/ops/wearable` | Wearable snapshot (SSE 비대응 폴백) |
| `/stream/wearable` | Wearable SSE (1초마다 push) |

### 관리
| 경로 | 설명 |
|------|------|
| `/api/admin/applications` | customer_product_application 조회 (?status, ?gid, ?limit, ?offset) |
| `/api/admin/local-lab-status` = `/api/local/status` | onprem Lambda `local_lab_status` |

---

## 12. `/users` 페이지 데이터 흐름 상세

`?q=` 검색 시 아래 순서로 실행:

```
① 이름 검색 (q가 'G'로 시작하지 않으면)
   → _call_onprem('search_by_name', q=이름)
   → 단일 결과면 해당 global_id로 redirect

② consent gate 확인
   → _call_onprem('get_consent', global_id=q)
   → ls_user_id 없으면: consent_gate='not_registered' → 빈 프로필 표시
   → 동의 항목 0개면: consent_gate='not_consented' → 빈 프로필 표시
   → 동의 있으면: consent_gate='ok' → ③으로 진행

③ profile + PII 조회 (gate 통과 후만)
   → _call_onprem('get_profile') → vip_grade, profile, identities, status
   → _call_onprem('get_pii') → name(마스킹), mobile(마스킹), gender, birth_date, address

④ Redis TOP-N
   → _stub_redis_personalized(q) → ZREVRANGE rec:{q} 0 2 WITHSCORES
   → HIT: product_id → product_master JOIN → 상품명 표시
   → MISS: 빈 list

⑤ Cross-sell (Aurora cross_sell_rule)
   → active_flag='Y' 상위 3개 → target_category 대표 상품 이름 조회

⑥ DynamoDB 점수/등급
   → Query global_id, ScanIndexForward=False, Limit=1
   → dynamic_grade, dynamic_score, vip_prob, rec_prob, signup_prob

⑦ NBA (Next Best Action)
   → DDB dynamic_grade → _nba_action_map으로 텍스트 변환
   → vip_prob/rec_prob/signup_prob → 퍼센트 표시

⑧ 최근 추천 이력 (Aurora customer_recommend_history)
   → JOIN product_master WHERE global_id ORDER BY recommended_at DESC LIMIT 5

⑨ 최근 행동 로그 (Aurora customer_dashboard_log)
   → LEFT JOIN product_master WHERE global_id ORDER BY view_time DESC LIMIT 5
```

---

## 13. 알려진 한계 / 주의 사항

| 항목 | 현황 |
|------|------|
| Aurora DML Scan | `_ddb_*` Scan 함수들은 DDB 전체 스캔. 고객 수 증가 시 비용 증가. 운영에서는 Lambda 일배치 mart 테이블 권장 |
| GCP ADC 인증 | `GOOGLE_APPLICATION_CREDENTIALS` 없으면 GCP 카드 전부 `-` 표시. 현재 운영 환경에서 미설정 상태 |
| Lambda prefix 발견 | `LAMBDA_PREFIX_FILTER=lifesync-` prefix로 자동 발견. 함수가 많아지면 CW 호출 수 증가 |
| SSE 장기 연결 | `/stream/wearable` SSE 연결. ALB/Nginx `proxy_buffering off` 없으면 버퍼링으로 실시간 미작동 |
| Flask session | 인메모리 session. 재시작 시 로그아웃. 운영에서는 Redis session 전환 고려 |
| 커넥션 풀 없음 | 매 요청마다 Aurora 새 연결. 폴링 API 30초 주기면 문제없으나 1초 이하 폴링 시 연결 고갈 가능 |
| Analytics DDB 테이블 | `analytics_segment_performance`, `analytics_demographic_information` 테이블은 `ENABLE_ANALYTICS_DYNAMODB_TABLES=false` 기본값으로 미생성 상태. 해당 API는 빈 list 반환 |
| `_ping_next_batch()` | AWS API에 next fire time이 없어서 schedule expression만 표시 가능 |
