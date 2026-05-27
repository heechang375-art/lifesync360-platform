# 인수인계 — 2026-05-26 세션 종료 시점

새 세션 시작 시 이 파일 먼저 읽고 시작할 것.

---

## 현재 브랜치 / 최신 커밋

```
branch: main
최신 커밋: d43027d  docs(platform): 설계서 V3 xlsx 재생성 (전체 시트 반영본)
```

2026-05-26 이번 세션 platform 서비스 관련 14개 commit (0015bd7 ~ d43027d) 모두 origin/main 푸시 완료. CI/CD 자동 트리거 (이번 PRIMARY rev=151, image ef99e6e6).

이전 세션 (2026-05-22~25) admin-platform 관련 로컬 변경 / EC2 SSM patch 미적용 건은 이월 (아래 admin 섹션 참조).

---

## 이번 세션(2026-05-26) — platform 서비스

### 운영 ECS 안정화

- **PRIMARY revision**: `:151` (image `ef99e6e6`)
- **ALB DNS (현)**: `lifesy-AppLo-J6LliXisfjNY-1279025200.ap-northeast-2.elb.amazonaws.com` ← 이전 HANDOFF 의 `pLuKs8ilCNwf` 는 deleted 상태
- base taskdef 정합화 (수동 register `:134`) 후 Pipeline 자동 deploy 도 정상화. Pipeline 의 ECS Deploy stage 는 현재 service taskdef 를 base 로 image 만 교체하기 때문에 base 가 한 번 망가지면 stale 자동 전파 — 수동 `register-task-definition + update-service` 한 번이 필수 (memory: `platform-pipeline-base-taskdef`)

### 주요 변경 (commit 흐름)

| commit | 내용 |
|---|---|
| `2fd70ee` | taskdef DB master secret ARN suffix `master-2Q28JC` → `master-o1Xcxo` 정합 |
| `417a6b5` | CONSENTS key 영문 LONG (INSURANCE/SECURITIES/HEALTHCARE/...) → 라이브 SHORT (INS/SEC/HLT/HOS/ONINS/WBL) 정합 — settings 동의 체크박스 매칭 정상화 |
| `7c359e9` | `docs/codebuild-role-policy.json` 실 IAM 동기화 + role inline policy 에 `ecs:RegisterTaskDefinition` / `ecs:DescribeTaskDefinition` 추가 (이 권한 누락으로 직전 빌드 실패) |
| `cda776b` | `start_ls360.sh` 평문 JWT 제거 → Secrets Manager `ecs-jwt-signing` jwt key 로드 |
| `b818bd6` | `start_ls360.sh` master secret key 매핑 정합 (host/username/password) + Redis 별도 secret 분리 |
| `75b8514` | taskdef REDIS_HOST 를 실 ElastiCache endpoint `lif-re-viqx38lwzx6o` 로 정합 (taskdef + Secrets Manager 둘 다 통일) |
| `b708a10` `62fe5af` | 상품 옵션 라벨 영문 → 한글 (43개) + 카테고리별 분기 (interest_rate/monthly_premium). 값 포맷팅 (Y/N → 예/아니오, `650000 KRW` → `650,000원`) |
| `dc9e0e8` | `_fetch_products` cache hit 분기에도 consent 필터 적용 — G000291135 같은 미동의자가 stale rec cache 의 보험 상품 보던 증상 차단 |
| `3db1812` | Dockerfile base image `python:3.11-slim` → ECR Public mirror `public.ecr.aws/docker/library/python:3.11-slim` (Docker Hub unauthenticated rate limit 429 회피) |
| `ac0618e` `ada9e0c` | NBA UI 카드 + 표시 JS + reason 의 `NBA "..." 매칭` 문구 → `AI 추천 매칭` 으로 자연어화. 백엔드 NBA 정렬 가중치는 그대로 |
| `19341c9` `c6b7922` `83669b3` `d43027d` | platform 설계서 V3 갱신: NBA 텍스트 제거 + JWT 위치 정합 + demo/시연 흔적 제거 + 추천 흐름 7단계 (② 동의 조회 신규, ⑥ 동의 필터 명시) |

### 검증 완료
- G000261829 (BANK/CARD/HLT/HOS/INS/SEC 동의) → settings 체크박스 HLT/INS/SEC 정상 표시
- G000291135 (INS/ONINS 미동의) → 보험 상품 추천 제외 SQL 단에서 차단

---

## 인프라 현황 (platform 서비스, 354 계정)

### ECS
| 자원 | 식별자 |
|---|---|
| 클러스터 | `lifesync-service-ecs` |
| 서비스 | `lifesync-dev-21-lifesync-ecs-existing-vpc-v4-svc` |
| Task Def family | `lifesync-dev-21-lifesync-ecs-existing-vpc-v4-td` |
| 현재 PRIMARY | `:151` (image `ef99e6e6`) |
| ECR | `354493396671.dkr.ecr.ap-northeast-2.amazonaws.com/lifesync-dev-lifesync-service` |
| ALB DNS | `lifesy-AppLo-J6LliXisfjNY-1279025200.ap-northeast-2.elb.amazonaws.com` |
| ECS task SG | `sg-0d5719d8a23e3313c` |

### Task Def 환경/시크릿 (정합 후)

env:
- `USE_MOCK=false`, `AWS_REGION=ap-northeast-2`
- `DB_NAME=lifesync360`, `DYNAMO_TABLE=lifesync_customer_result`
- `REDIS_HOST=lif-re-viqx38lwzx6o.lkjrak.0001.apn2.cache.amazonaws.com`, `REDIS_PORT=6379`
- `ONPREM_QUERY_LAMBDA=lifesync-onprem-customer-query`, `PROFILE_SYNC_LAMBDA=customer-profile-sync`

secrets (valueFrom):
- `JWT_SECRET` ← `arn:aws:secretsmanager:...:secret:ecs-jwt-signing-QpgPth:jwt::`
- `DB_USER` / `DB_PASS` / `AURORA_HOST` ← `arn:aws:secretsmanager:...:secret:/lifesync/dev/db/master-o1Xcxo:{username|password|host}::`

### Secrets Manager 진실 (suffix 자주 outdated 됨 — 작업 시 list-secrets 로 직접 조회 권장)

| Secret | 현재 suffix | JSON shape |
|---|---|---|
| `ecs-jwt-signing` | `-QpgPth` | `{"jwt": "<64-hex>"}` |
| `/lifesync/dev/db/master` | `-o1Xcxo` | `{username, password, host, port, dbname, engine}` |
| `lifesync/dev/redis` | `-6hwssH` | `{host, port}` — start_ls360.sh 가 참조 |

### ElastiCache Redis
- 실 cluster: `lif-re-viqx38lwzx6o` (endpoint `:6379`)
- Redis SG `sg-059bfe6ac28dd959e` inbound 6379 에 ECS task SG `sg-0d5719d8a23e3313c` 허용됨
- CurrItems ≈ 58K — **외부 batch 가 pre-warm 함** (어디서/언제 도는지 미규명)

### CodeBuild role `lifesync-dev-svcplt-codebuild-role`
- inline policy 9 statements — 실 IAM = `docs/codebuild-role-policy.json`
- 이번 세션에 `ecs:RegisterTaskDefinition` / `ecs:DescribeTaskDefinition` 추가

---

## 알려진 이슈 / 미해결 (platform)

| 이슈 | 상태 / 다음 액션 |
|---|---|
| **`rec:{gid}` cache pre-warm batch 미규명** | Redis CurrItems 58K — 외부 batch process 가 채움. consent gate 없을 가능성 → cache hit 분기에 SQL 단 consent 필터 (`dc9e0e8`) 로 일단 방어. 근본 fix 는 batch 찾아서 consent gate 적용 |
| **ECS Exec 비활성** | service `enableExecuteCommand=false` + task role 에 `ssmmessages:*` 없음. 컨테이너 내부 진단 필요할 때 권한 추가 + force-new-deploy 필요 |
| **ECS → Redis 자연 트래픽 검증 미완** | 통일 후 NewConnections=0 길게 유지. 자연 트래픽 시점에 CurrConnections/NewConnections 모니터링으로 검증 가능 |
| **start_ls360.sh 사용처 미명확** | 어떤 EC2/VM 에서 실행되는지 모름. 운영 ECS 와 별개 환경 추정 |
| **HANDOFF / docs / 주석의 인프라 식별자 outdated 잦음** | ALB DNS, secret ARN suffix, cluster ID 등 운영 변경에 따라 자주 바뀜. 작업 전 AWS 직접 조회 |

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

### On-Prem VPN 재구성 후 필수 작업 (우선순위 1)

VPN 재구성 완료되면 아래 순서대로 처리:

```bash
# 1. Lambda PRIVATE_API_URL 업데이트 (현재 172.16.1.73 → 실제 IP)
aws lambda update-function-configuration \
  --function-name lifesync-onprem-customer-query \
  --environment "Variables={PRIVATE_API_URL=http://<새IP>}"

# 2. TGW 스태틱 라우트 추가 (AcceptedRouteCount=0 상태)
aws ec2 create-vpn-connection-route \
  --vpn-connection-id vpn-06b4f730ddfd17bc4 \
  --destination-cidr-block <온프렘서브넷>/24
```

```powershell
# 3. EC2 start-admin.ps1 수정 (SSM으로)
# - $env:ONPREM_BASE_URL = "http://172.16.1.73"  ← 이 줄 제거
# - $env:ONPREM_QUERY_LAMBDA = "lifesync-onprem-customer-query"  ← 추가
# 수정 후 Flask 재시작:
# Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Hidden -File C:/start-admin.ps1'
```

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
- EC2: `i-0e9ff040046f8c1ca` (Windows, **실행 중**)
- 실행 경로: `C:/admin-platform/` — `C:/start-admin.ps1`이 여기서 Flask 기동
- 배포 스크립트: `admin-platform/deploy_to_ec2.ps1` (S3 경유 SSM, app.py + templates + static + wearable_engine.py)
- 프로세스 재시작: `Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Hidden -File C:/start-admin.ps1'`
- Task Scheduler "AdminApp"은 부팅 시에만 자동 시작 (프로세스 사망 시 자동 재시작 없음)
- Flask `debug=True` — app.py 변경 시 자동 리로드, 단 프로세스 강제종료 시엔 위 명령으로 재시작 필요
- 포트: 5001 / S3 배포 키: `s3://lifesync-raw/deploy/app_deploy.zip`

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
| **온프레미스 VPN 재구성 중** | VPN 삭제 후 재설정 진행 중 (2026-05-26). 완료 후 아래 on-prem 후속 작업 필수 |
| **온프레미스 화면 미표시** | `ONPREM_BASE_URL=http://172.16.1.73`이 EC2에서 직접 호출 → 연결 불가. VPN 재구성 완료 후 `start-admin.ps1` 수정 필요 (아래 참고) |
| **Lambda PRIVATE_API_URL 구IP** | `lifesync-onprem-customer-query`의 `PRIVATE_API_URL=http://172.16.1.73:80` — 현재 on-prem IP는 `192.168.45.157`. VPN 재구성 후 업데이트 필요 |
| **analytics_segment_performance 0행** | DDB fallback 데이터 없음 → 연령대별 차트 빈 결과 지속 |
| **ml_model_evaluation_daily 0행** | Precision 카드 빈 결과 |
| **권한 이슈 5건 IaC 미반영** | 재배포 시 수동 추가 권한이 사라짐 — `docs/iac-handoff-2026-05-24.md` 권한 패치 5건 적용 필수 |
| Redis 타입 불일치 | 플랫폼 app `SETEX`(string) vs 어드민 app `ZREVRANGE`(zset) → 어드민 TOP-N 항상 miss |
| Aurora users_ref 없음 | 어드민 `/users` 이름/이메일 `-` 표시 |
| Management subnet 미생성 | `01-network.yaml` 수정됐으나 스택 업데이트 미실행 |
| INNER JOIN 시드 부정합 risk | `customer_recommend_history × product_master × category_master` — 매칭 깨지면 silently empty (개선: LEFT JOIN 검토) |
