# 인수인계 — 2026-05-25 세션 종료 시점

새 세션 시작 시 이 파일 먼저 읽고 시작할 것.

---

## 현재 브랜치 / 최신 커밋

```
branch: main
최신 커밋: 94f4523  merge: origin/main 병합 (원격 12개 커밋 통합)
```

2026-05-22~25 세션 변경사항(IaC 템플릿, admin-platform 코드, 설계서, docs/iac-handoff-2026-05-24.md, 보완 가이드 등)은 로컬 수정 상태 — 아직 커밋 안 됨.

EC2(`i-0784a4837383967bf`) 실행 중인 `C:\admin-platform\app.py`에는 SSM base64 방식으로 패치 직접 적용됨 — 단, 2026-05-24 CVR fix와 raw count 표시는 EC2 미적용 (클라우드 작업 불가 상태).

---

## 작업 환경 — 원본 ls + Desktop\ls-copy 분리

| 위치 | 용도 | 계정 |
|------|------|------|
| `C:\Users\campus3S026\ls\` | 원본 작업 폴더 | **354** (`354493396671`) |
| `C:\Users\campus3S026\Desktop\ls-copy\` | 격리 복사본 (`.git` 포함) | **732** (`732264765472`) |

계정 전환 시 시간 절약 목적. 코드/IaC 동일, 계정 ID/bucket 이름만 변환됨.

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

### 삭제된 스택 (2026-05-22)

| 스택명 | 비고 |
|--------|------|
| lifesync-dev-24-admin-windows-ec2 | admin EC2 (재배포 필요) |
| lifesync-dev-final-gcp-tgw-vpn | - |
| lifesync-dev-final-local-vm-vpn | - |
| lifesync-dev-gcp-data-exchange-ssm | - |
| lifesync-dev-15-cicd | - |
| lifesync-dev-25-customer-profile-sync-lambda | - |
| lifesync-dev-28-gcp-phz | - |
| lifesync-dev-17/18/19-cicd-* | - |
| lifesync-dev-gha-cc-* (6개) | - |

---

## 이번 세션(2026-05-22~25)에서 완료한 것

### 1. admin-platform 코드 개선

| 항목 | 내용 |
|------|------|
| 죽은 코드 7개 제거 | `_ping_domain_flow`, `_ping_lambda_metrics`, `_ping_next_batch`, `_ping_vpc_peering`, `_ping_wearable_realtime`, `_ping_local_lab`, `_stub_feature_importance` |
| Management VPC EC2 분류 | `_ping_vm_status()`에 `elif 'management' in vpc_name` 분기 + `/api/vm/management` 라우트 |
| Precision 단독 표시 | Recall 제거 (폐쇄형 UI에서 FN=0 고정으로 무의미) |
| ops.html 5 VPC | 3→5 (Wearable·Management 추가) |
| 전체 템플릿 한글화 + CTR/CVR 병기 | 건강 위험/주의, 빅쿼리 등 |
| terms.md 신규 | 4페이지 용어집 |
| 연령대별 차트 수정 | `_ai_age_perf_2step()` 완전 재작성 — On-Prem `/internal/profile/list-all` 페이지네이션 (next_after cursor, size=500, max 10 pages, timeout 2s/call) + DDB fallback |
| **CVR 공식 버그 fix** (2026-05-24 audit) | `app.py:2006` 분모를 `clk` → `rec`로 변경. 다른 차트/설계서/terms.md와 통일 |
| **AI 차트 raw count 표시 추가** (2026-05-24) | CTR/CVR 옆에 `(clicked/recommended)` 표기. 9 위치 (app.py 3 + templates 6) |

### 2. IaC 템플릿 수정 (미배포)

| 파일 | 변경 내용 |
|------|----------|
| `01-network.yaml` | Management VPC admin 서브넷 `10.4.20.0/24` 추가, TGW 조건부 라우트 |
| `24-admin-windows-ec2.yaml` | 크로스VPC SG → CidrIp 수정, RDP 비밀번호 UserData, Task Scheduler 등록 |

### 3. 설계서 V5_3 업데이트

`관리자_대시보드_설계서_V5_3.xlsx` — AI KPI 재구성, CVR 공식 수정, 5 VPC 반영, 한글화 전반, 카테고리 도넛 JOIN 3개, 연령대별 데이터 소스 변경, API 4개 추가.

### 4. admin EC2 스택 삭제 (2026-05-22)

수동 revoke한 SG 규칙 3개:

| SG | 포트 | rule ID | 비고 |
|----|------|---------|------|
| sg-0173c5604ec575935 (Aurora) | 3306 | sgr-0b68dcf7c51272f49 | IaC 관리 |
| sg-085975aa022d5f15e (Redis) | 6379 | sgr-0fd9db477bb3e0d9e | IaC 관리 |
| sg-0f060ae1e16bfd6df (SqlOpsSsmVpceSg) | 443 | sgr-0109b205f7e0895d8 | **수동 추가 — IaC 없음, 재배포 시 재생성 안 됨** |

### 5. 08-database SqlOps 리소스 제거

`CreateSqlOpsMysqlEc2=false` 스택 업데이트로 SqlOps 관련 리소스 전체 삭제:
- `SqlSsmAccessInstance`, `SqlOpsSsmVpceSg`, `SqlSsmAccessEc2Sg`
- SSM/RDS VPC 엔드포인트 4개
- IAM Role/Profile/Policy 3개

Aurora·Redis 연결 영향 없음 (SqlOps는 점프박스용).

### 6. IaC 변경/추가 정리 문서 (2026-05-24)

`docs/iac-handoff-2026-05-24.md` 신규 — IaC 담당자 전달용:
- **modified 5개** (commit 후 배포): 01b, 08, 08b, 19-cicd-service-platform, 21
- **untracked 신규 적용 필요 3개**: 01-network, 24-admin-windows-ec2, 27-onprem-simulator
- **권한 이슈 IaC 미반영 5건** (수동 해결 → 재배포 시 깨짐):
  - #10 ECS ExecutionRole `kms:Decrypt` (Condition: ViaService=ssm.${REGION}.amazonaws.com)
  - #11 VPC KMS Interface Endpoint
  - #22 OnpremSimRole `lambda:InvokeFunction`
  - #24 OnpremSimRole DynamoDB Query/GetItem/Scan
  - #26 Aurora/Redis SG 인바운드에 OnpremSim SG 미허용
- **보안 audit**: `admin123` 하드코딩 → Secrets Manager 분리 권장

### 7. 작업 환경 정리 (2026-05-24~25)

- ls/ 디스크 회복: **43.4 GB** (44.68 GB → 1.32 GB)
  - 잔여물 정리 (zip 14개 — 그 중 `admin-platform-patch2.zip` 단일 43GB) + `.venv` + `__pycache__` + `ssm_*.json` 35개 + `*.txt` dump 40개 + 디버그/체크 스크립트 27개
  - outer `Aws_iac/` (옛 354 사본) + AWS CLI 인스톨러 잔여물 (`Aws_iac/Aws_iac/aws/` + `awscliv2.zip`)
- Desktop `ls-copy/` 생성 — 1.32 GB, 7,996 파일, robocopy `/E /MT:8` 5.8초
- `ls-copy/` 354 → 732 계정 치환 — 16 파일 45건 (account ID + bucket 이름)
- 원본 ls/는 354 그대로 보존 (검증 완료)

---

## 남은 작업 (이월)

### IaC 재배포 / 신규 적용 (담당자 측)

| 항목 | 비고 |
|------|------|
| **modified 5개 commit/배포** | 01b · 08 · 08b · 19-cicd-service-platform · 21 — `docs/iac-handoff-2026-05-24.md` 참고 |
| **untracked 3개 신규 add** | 01-network · 24-admin-windows-ec2 · 27-onprem-simulator |
| **권한 패치 5건 IaC 반영** | kms:Decrypt · KMS endpoint · lambda invoke · DDB query · Aurora/Redis SG 인바운드 |
| **admin123 → Secrets Manager** | 24-admin-windows-ec2 보안 보완 |

### 코드 / 데이터

| 항목 | 비고 |
|------|------|
| `/api/me` name/grade 연동 | onprem Lambda `get_pii` 검증 필요 |
| Aurora `users_ref` 동기화 | 어드민 `/users` 이름/이메일 표시용 |
| `analytics_segment_performance` 시드 투입 | 연령대별 차트 DDB fallback 데이터 공급 — `seed_analytics_scratch.py` 활용 |
| `ml_model_evaluation_daily` 시드 투입 | Precision 카드 데이터 공급 — `seed_ml_evaluation.py` 활용 |
| Aurora 복구 후 검증 | kpi4 CTR/CVR · 7일 추이 · 도넛 · TOP10 정상 노출 확인 |
| 온프레미스 재시작 후 검증 | `/internal/profile/list-all` 페이지네이션 + Aurora JOIN end-to-end |
| EC2 `C:\admin-platform\app.py` 패치 적용 | 2026-05-24 변경분 (CVR fix + raw count 표시) SSM base64 패치 |

### 코드 개선 권장 (audit 결과)

| 항목 | 비고 |
|------|------|
| INNER JOIN → LEFT JOIN 검토 | `_aurora_recommend_top10`, `_aurora_category_ctr_donut` — 시드 정합 깨질 때 silent empty 회피 |
| 차트 실패 시 진단 메시지 | "Aurora 연결 실패" / "On-Prem 미응답" 등 구분 표시 |
| 7일 추이 customer_recommend_daily KPI 카드에 raw count | `customer_recommend_daily` 테이블 스키마 확인 후 적용 |

---

## Admin EC2 스택 삭제 시 주의사항

`24-admin-windows-ec2` 재삭제 시 아래 2개 SG 규칙을 먼저 수동 revoke (IaC가 만드는 것).

```bash
NEW_ADMIN_SG=$(aws cloudformation describe-stack-resources \
  --stack-name lifesync-dev-24-admin-windows-ec2 \
  --query "StackResources[?LogicalResourceId=='AdminInstanceSg'].PhysicalResourceId" \
  --output text)

aws ec2 describe-security-groups \
  --filters "Name=ip-permission.group-id,Values=$NEW_ADMIN_SG" \
  --query "SecurityGroups[*].[GroupId,GroupName]" --output table

# IaC 관리 규칙 revoke (rule ID는 재배포 후 바뀜)
# Aurora SG → TCP 3306
# Redis SG  → TCP 6379
```

> **SqlOpsSsmVpceSg TCP 443 규칙은 수동 추가였음 — 재배포 시 재생성 안 됨.** 다음 삭제 때는 Aurora/Redis 2개만 처리하면 됨.

---

## On-Prem IP 변경 추적

> 현재 IP: `192.168.45.157` (브리지 어댑터, 2026-05-23 변경)

IP 또는 서브넷 변경 시 동기화 필요 5곳:

| # | 위치 | 변경 방법 |
|---|------|----------|
| 1 | `admin-platform/app.py:104` `ONPREM_BASE_URL` 기본값 | 코드 수정 후 SSM patch 배포 |
| 2 | Lambda `lifesync-onprem-customer-query` 환경변수 `PRIVATE_API_URL` | `aws lambda update-function-configuration` |
| 3 | TGW route table `tgw-rtb-05da340fa6bc057c7` static 라우트 | delete + create |
| 4 | Management VPC private RT `rtb-005a802a3c7f28634` | delete + create |
| 5 | lifesync-vpc app-private-rt `rtb-06d02c5c017083ac4` | delete + create |

IP만 바뀌고 서브넷(/24) 그대로면 1, 2번만 처리하면 됨. 상세 명령은 `project-progress.md` Step IP 변경 추적 섹션 참고.

---

## 인프라 현황 (354 계정 기준 `354493396671`)

### 온프레미스 시뮬레이터
- EC2 `i-0c36936f6ca95f664` (Linux, `/opt/ls360/`)
- 재시작: `start_ls360.sh` (Secrets Manager 자동 로드)
- 로그: `/opt/ls360.log`

### 어드민 대시보드
- EC2: **현재 없음** (24 스택 삭제됨)
- 재배포: `24-admin-windows-ec2.yaml` 스택
- RDP 비밀번호: `admin123` (UserData에서 자동 설정 — Secrets Manager 분리 권장)
- 포트: 5001, Task Scheduler "AdminApp" 자동 시작

### AWS
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
| `admin-platform/templates/` | ai.html, ops.html, dashboard.html, users.html + 차트 partial 4개 |
| `Aws_iac/Aws_iac/templates/01-network.yaml` | VPC/서브넷 IaC (Management subnet 추가됨, 미배포) |
| `Aws_iac/Aws_iac/templates/24-admin-windows-ec2.yaml` | Admin EC2 IaC (CidrIp 수정 + UserData 완성) |
| `Aws_iac/Aws_iac/templates/08-database.yaml` | DB IaC (CreateSqlOpsMysqlEc2=false 운영 중) |
| `docs/iac-handoff-2026-05-24.md` | **IaC 담당자 전달용** (5 modified + 3 untracked + 권한 패치 5건 + 보안) |
| `docs/admin-platform-app-guide.md` | 어드민 app.py 구조/API 문서 |
| `docs/cicd-troubleshooting-and-iac-tasks.md` | 트러블슈팅 #1~#32 누적 |
| `project-progress.md` | 전체 진행 기록 (2026-05-25 세션까지 누적) |
| `관리자_대시보드_설계서_V5_3.xlsx` | 최신 설계서 |
| `seed_analytics_scratch.py` / `seed_ml_evaluation.py` / `seed_ddb_grades.py` / `seed_segment_today.py` | 시드 스크립트 (인프라 복구 후 실행 대기) |

---

## 주요 알려진 이슈

| 이슈 | 내용 |
|------|------|
| **Aurora deleting** | `auroracluster-db-writer` 삭제 중 → kpi4 CTR/CVR, trend, donut, TOP10 빈 결과 (2026-05-23 확인) |
| **온프레미스 종료** | 사용자 종료 → 연령대별 차트 DDB fallback (0행이라 빈 상태) (2026-05-23 확인) |
| **analytics_segment_performance 0행** | DDB fallback 데이터 없음 → 연령대별 차트 빈 결과 지속 |
| **ml_model_evaluation_daily 0행** | Precision 카드 빈 결과 |
| **권한 이슈 5건 IaC 미반영** | 재배포 시 수동 추가 권한이 사라짐 — `docs/iac-handoff-2026-05-24.md` 권한 패치 5건 적용 필수 |
| **EC2 admin app CVR fix 미적용** | 클라우드 작업 불가 상태라 SSM base64 패치 보류. 로컬 코드만 수정됨 |
| Redis 타입 불일치 | 플랫폼 app `SETEX`(string) vs 어드민 app `ZREVRANGE`(zset) → 어드민 TOP-N 항상 miss |
| GCP ADC 미설정 | `GOOGLE_APPLICATION_CREDENTIALS` 없음 → GCP 카드 전부 `-` 표시 |
| Aurora users_ref 없음 | 어드민 `/users` 이름/이메일 `-` 표시 |
| Admin EC2 없음 | 스택 삭제됨. `24-admin-windows-ec2` 재배포 필요 |
| Management subnet 미생성 | `01-network.yaml` 수정됐으나 스택 업데이트 미실행 |
| INNER JOIN 시드 부정합 risk | `customer_recommend_history × product_master × category_master` — 매칭 깨지면 silently empty (개선: LEFT JOIN 검토) |
