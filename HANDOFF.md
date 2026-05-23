# 인수인계 — 2026-05-23 세션 종료 시점

새 세션 시작 시 이 파일 먼저 읽고 시작할 것.

---

## 현재 브랜치 / 최신 커밋

```
branch: main
최신 커밋: 1bfb142  docs: admin/platform app.py 구조 가이드 문서 추가
```

2026-05-22 세션 2·3 및 2026-05-23 세션 변경사항(IaC 템플릿, admin-platform 코드, 설계서)은 로컬 수정 상태 — 아직 커밋 안 됨.

EC2(`i-0784a4837383967bf`) 실행 중인 `C:\admin-platform\app.py`에는 SSM base64 방식으로 패치가 직접 적용됨 — 로컬 git repo의 `admin-platform/app.py`와 내용 동일.

---

## 현재 활성 스택 (12개, 354 계정)

| 스택명 | 상태 |
|--------|------|
| lifesync-dev-01-network | CREATE_COMPLETE |
| lifesync-dev-02-security | CREATE_COMPLETE |
| lifesync-dev-06-s3 | UPDATE_COMPLETE |
| lifesync-dev-07-ecr | CREATE_COMPLETE |
| lifesync-dev-08-database | UPDATE_COMPLETE |
| lifesync-dev-09-streaming-api-lambda | CREATE_COMPLETE |
| lifesync-dev-10-data-processing | CREATE_COMPLETE |
| lifesync-dev-11-observability | CREATE_COMPLETE |
| lifesync-dev-12-ec2 | CREATE_COMPLETE |
| lifesync-dev-21-lifesync-ecs-existing-vpc-v4 | UPDATE_COMPLETE |
| lifesync-dev-22-identity-enricher-lambda | CREATE_COMPLETE |
| lifesync-dev-24-service-elasticache-lambda | CREATE_COMPLETE |

### 오늘 삭제된 스택

| 스택명 | 삭제 시각 |
|--------|-----------|
| lifesync-dev-24-admin-windows-ec2 | 2026-05-22 10:25 |
| lifesync-dev-final-gcp-tgw-vpn | 2026-05-22 10:25 |
| lifesync-dev-final-local-vm-vpn | 2026-05-22 10:22 |
| lifesync-dev-gcp-data-exchange-ssm | 2026-05-22 10:24 |
| lifesync-dev-15-cicd | 2026-05-22 10:30 |
| lifesync-dev-25-customer-profile-sync-lambda | 2026-05-22 10:31 |
| lifesync-dev-28-gcp-phz | 2026-05-22 10:14 |
| lifesync-dev-17/18/19-cicd-* | 2026-05-22 10:05~10 |
| lifesync-dev-gha-cc-* (6개) | 2026-05-22 10:06~14 |

---

## 오늘 세션에서 완료한 것

### 1. admin-platform 코드 개선 (세션 2)

| 항목 | 내용 |
|------|------|
| 죽은 코드 7개 제거 | `_ping_domain_flow`, `_ping_lambda_metrics`, `_ping_next_batch`, `_ping_vpc_peering`, `_ping_wearable_realtime`, `_ping_local_lab`, `_stub_feature_importance` |
| Management VPC EC2 분류 | `_ping_vm_status()`에 `elif 'management' in vpc_name` 분기 추가 |
| `/api/vm/management` 라우트 추가 | |
| Precision 단독 표시 | Recall 제거 — 폐쇄형 추천 UI에서 FN=0 고정으로 무의미 |
| ops.html 5 VPC | 3→5 (웨어러블·관리 추가) |
| 전체 템플릿 한글화 | CTR/CVR 병기, 건강 위험/주의, 빅쿼리 등 |
| `terms.md` 신규 | 4페이지 용어집 |

### 2. IaC 템플릿 수정 (세션 2, 미배포)

| 파일 | 변경 내용 |
|------|-----------|
| `01-network.yaml` | Management VPC admin 서브넷 10.4.20.0/24 추가, TGW 조건부 라우트 |
| `24-admin-windows-ec2.yaml` | 크로스VPC SG → CidrIp 수정, RDP 비밀번호 UserData, Task Scheduler 등록 |

### 3. 설계서 업데이트 (세션 2)

`관리자_대시보드_설계서_V5_3.xlsx` — AI KPI 재구성, CVR 공식 수정, 5 VPC 반영, 한글화 전반.

### 4. admin EC2 스택 삭제 (세션 3)

삭제 전 수동 revoke한 SG 규칙 3개:

| SG | 포트 | rule ID | 비고 |
|----|------|---------|------|
| sg-0173c5604ec575935 (Aurora) | 3306 | sgr-0b68dcf7c51272f49 | IaC 관리 |
| sg-085975aa022d5f15e (Redis) | 6379 | sgr-0fd9db477bb3e0d9e | IaC 관리 |
| sg-0f060ae1e16bfd6df (SqlOpsSsmVpceSg) | 443 | sgr-0109b205f7e0895d8 | **수동 추가된 것 — IaC 없음, 재배포 시 재생성 안 됨** |

### 5. 08-database SqlOps 리소스 제거 (세션 3)

`CreateSqlOpsMysqlEc2=false`로 스택 업데이트 → SqlOps 관련 리소스 전체 삭제:
- `SqlSsmAccessInstance` (i-0356e5ce92f132d49, 이미 terminated 상태였음)
- `SqlOpsSsmVpceSg`, `SqlSsmAccessEc2Sg`
- SSM/RDS VPC 엔드포인트 4개
- IAM Role/Profile/Policy 3개

Aurora·Redis 연결에는 영향 없음 (SqlOps는 운영자 직접 SQL 접근용 점프박스였음).

### 6. AI 대시보드 연령대별 차트 버그 수정 (2026-05-23)

**증상**: `/api/ai/chart/age` 0.3s 만에 빈 결과 반환.

**원인 추적**:

| 단계 | 내용 |
|------|------|
| 1차 | `_call_onprem('list_by_age_band')` 호출 → `_ROUTES` 딕셔너리에 `list_by_age_band` 없음 → 즉시 `{}` 반환 |
| 2차 | 온프레미스 API에 `list_by_age_band` 엔드포인트 자체 없음 (openapi.json 확인) |
| 3차 | Lambda 경로도 막힘: `ONPREM_QUERY_LAMBDA` 환경변수 미설정 |
| 4차 | DDB fallback: `analytics_segment_performance` 테이블 0행 → 빈 결과 |

**수정**: `_ai_age_perf_2step()` 완전 재작성 (`admin-platform/app.py` 로컬 + EC2 양쪽 적용)
- OLD: `_call_onprem('list_by_age_band')`
- NEW: 온프레미스 `/internal/profile/list-all?size=500&after=<cursor>` 직접 페이지네이션
  - cursor 필드: `next_after` (응답 JSON 확인 완료)
  - max 10 pages, timeout=2s/call (온프레미스 종료 시 빠른 실패)
  - 실패 시 DDB `analytics_segment_performance` age_band# fallback 유지

**현재 상태**: 코드 수정됨. 단, 온프레미스 종료 + DDB 0행이어서 차트 여전히 빈 상태 (인프라 문제).

### 7. 리소스 현황 파악 (2026-05-23)

| 리소스 | 상태 | 영향 |
|--------|------|------|
| Aurora `auroracluster-db-writer` | **deleting** (삭제 중) | kpi4 CTR/CVR, trend 차트, TOP10, 도넛 모두 빈 결과 |
| 온프레미스 | **종료됨** (사용자 명시적 종료) | 연령대별 차트 DDB fallback → 0행이라 빈 차트 |
| DynamoDB `lifesync_customer_result` | 정상 (58,637 items) | histogram, 배치 고객 수, 마지막 갱신 정상 |
| `analytics_segment_performance` DDB | **0행** | age_band fallback 데이터 없음 |
| `customer-profile-sync` Lambda | **존재하지 않음** (ResourceNotFoundException) | - |
| `customer_recommend_history` / `customer_recommend_daily` | 시드 데이터 (패턴 기반 생성, 실제 클릭/구매 아님) | CTR/CVR 수치가 실제 사용자 행동 반영 안 함 |

### 8. 설계서 업데이트 (2026-05-23)

`관리자_대시보드_설계서_V5_3.xlsx` — AI 추천 시트 수정:

| 항목 | 변경 내용 |
|------|-----------|
| `카테고리별 도넛` 테이블/객체 | `category_master` → `customer_recommend_history JOIN product_master JOIN category_master cat` |
| `연령대별 추천 성과` 데이터 소스 | `On-Prem Lambda (1순위)` → `On-Prem /internal/profile/list-all 직접 HTTP (1순위)` |
| `연령대별 추천 성과` 테이블/객체 | `list_by_age_band action →` → `/internal/profile/list-all?size=500&after=<cursor> →` |
| `연령대별 추천 성과` 컬럼/비고 | 페이지네이션 상세 (cursor, size, max pages, timeout) 반영 |
| API 테이블 누락 4개 추가 | `GET /api/ai/chart/trend` · `donut` · `age` · `histogram` (server-rendered SVG fragment) |

---

## 남은 작업 (이월)

### IaC 재배포

| 항목 | 비고 |
|------|------|
| `24-admin-windows-ec2` 스택 재배포 | 현재 삭제된 상태. 재배포 전 아래 "Admin EC2 스택 삭제 시 주의사항" 숙지 필요 |
| `01-network.yaml` 스택 업데이트 | Management VPC admin 서브넷 10.4.20.0/24 생성 (템플릿 수정됨, 스택 미적용) |

### 코드

| 항목 | 비고 |
|------|------|
| `/api/me` name/grade 연동 | onprem Lambda `get_pii` 검증 필요 |
| Aurora `users_ref` 동기화 | 어드민 `/users` 이름/이메일 표시용 |
| `analytics_segment_performance` 시드 투입 | 연령대별 차트 DDB fallback 데이터 공급용. `seed_analytics_scratch.py` 참고 |
| 온프레미스 재시작 후 연령대별 차트 검증 | `/internal/profile/list-all` 페이지네이션 → Aurora JOIN 경로 end-to-end 확인 |

---

## Admin EC2 스택 삭제 시 주의사항

`24-admin-windows-ec2` 스택 삭제 전 아래 2개 SG 규칙을 먼저 수동 revoke해야 함 (IaC가 만드는 것).

```bash
# 재배포 후 새 admin SG ID 확인
NEW_ADMIN_SG=$(aws cloudformation describe-stack-resources \
  --stack-name lifesync-dev-24-admin-windows-ec2 \
  --query "StackResources[?LogicalResourceId=='AdminInstanceSg'].PhysicalResourceId" \
  --output text)

# 해당 SG를 참조하는 SG 전체 확인 (혹시 수동 추가된 게 있으면 여기서 잡힘)
aws ec2 describe-security-groups \
  --filters "Name=ip-permission.group-id,Values=$NEW_ADMIN_SG" \
  --query "SecurityGroups[*].[GroupId,GroupName]" --output table

# IaC 관리 규칙 revoke (rule ID는 재배포 후 바뀜 — describe로 재확인)
# Aurora SG → TCP 3306
# Redis SG  → TCP 6379
```

> **SqlOpsSsmVpceSg TCP 443 규칙은 수동 추가였음 — 재배포 시 재생성 안 됨.**
> `08-database.yaml` 확인 완료. 다음 삭제 때는 Aurora/Redis 2개만 처리하면 됨.

---

## 인프라 현황 (354 계정 기준)

### 온프레미스 시뮬레이터
- EC2 `i-0c36936f6ca95f664` (Linux, `/opt/ls360/`)
- 재시작: `start_ls360.sh` (Secrets Manager 자동 로드)
- 로그: `/opt/ls360.log`

### 어드민 대시보드
- EC2: **현재 없음** (스택 삭제됨)
- 재배포: `24-admin-windows-ec2.yaml` 스택 올리면 됨
- RDP 비밀번호: `admin123` (UserData에서 자동 설정)
- 포트: 5001, Task Scheduler "AdminApp" 자동 시작

### AWS (354 계정 `354493396671`)
- Aurora MySQL: Secrets Manager `/lifesync/dev/db/master`
- DynamoDB: `lifesync_customer_result` (global_id HASH + update_time RANGE)
- ElastiCache Redis: 동일 Secrets Manager
- S3 raw bucket: `lifesync-354-raw`
- Management VPC: `10.4.0.0/16`, admin subnet 예정: `10.4.20.0/24` (IaC 미적용)

---

## 핵심 파일 위치

| 파일 | 역할 |
|------|------|
| `admin-platform/app.py` | 관리자 대시보드 Flask 앱 (포트 5001) |
| `admin-platform/mockup_data.py` | 5 VPC 목업 + AI 모델 목업 |
| `admin-platform/terms.md` | 대시보드 전체 용어집 |
| `Aws_iac/Aws_iac/templates/01-network.yaml` | VPC/서브넷 IaC (Management subnet 추가됨, 미배포) |
| `Aws_iac/Aws_iac/templates/24-admin-windows-ec2.yaml` | Admin EC2 IaC (CidrIp 수정 + UserData 완성) |
| `Aws_iac/Aws_iac/templates/08-database.yaml` | DB IaC (CreateSqlOpsMysqlEc2=false로 운영 중) |
| `docs/admin-platform-app-guide.md` | 어드민 app.py 구조/API 문서 |
| `docs/cicd-troubleshooting-and-iac-tasks.md` | 트러블슈팅 #1~#32 누적 |
| `project-progress.md` | 전체 진행 기록 |
| `관리자_대시보드_설계서_V5_3.xlsx` | 최신 설계서 |

---

## 주요 알려진 이슈

| 이슈 | 내용 |
|------|------|
| **Aurora deleting** | `auroracluster-db-writer` 삭제 중 → kpi4 CTR/CVR, trend, donut, TOP10 빈 결과 (2026-05-23 확인) |
| **온프레미스 종료** | 사용자 명시적 종료 → 연령대별 차트 DDB fallback (0행이라 빈 상태) (2026-05-23 확인) |
| **analytics_segment_performance 0행** | DDB fallback 데이터 없음 → 연령대별 차트 빈 결과 지속 |
| Redis 타입 불일치 | 플랫폼 app `SETEX`(string) vs 어드민 app `ZREVRANGE`(zset) → 어드민 TOP-N 항상 miss |
| GCP ADC 미설정 | `GOOGLE_APPLICATION_CREDENTIALS` 없음 → GCP 카드 전부 `-` 표시 |
| Aurora users_ref 없음 | 어드민 `/users` 이름/이메일 `-` 표시 |
| Admin EC2 없음 | 스택 삭제됨. `24-admin-windows-ec2` 재배포 필요 |
| Management subnet 미생성 | `01-network.yaml` 수정됐으나 스택 업데이트 미실행 |
