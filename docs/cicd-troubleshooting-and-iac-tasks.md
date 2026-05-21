# Platform CI/CD 트러블슈팅

> 작성일: 2026-05-12

---

## 트러블슈팅 요약

| 순서 | 오류 | 원인 | 해결 |
|------|------|------|------|
| 1 | `Invalid character in header content ["authorization"]` | AWS Secret Key가 `+`로 시작 → 엑셀이 `=` 붙여 41자로 오염 | GitHub Secrets 값 직접 재입력 (엑셀 사용 금지) |
| 2 | `Signature mismatch` | Secret Key 값 불일치 | 신규 IAM 액세스 키 발급 후 재등록 |
| 3 | `buildspec.yml: no such file or directory` | CodeBuild가 `deploy/buildspec.yml` 기대, 실제 루트에 위치 | `lifesync360-platform/deploy/buildspec.yml`로 이동 |
| 4 | `imagedefinitions.json not found` | buildspec이 `imageDetail.json` 생성 (Blue/Green 포맷), 파이프라인은 ECS rolling update 포맷 기대 | artifacts를 `imagedefinitions.json`으로 변경 |
| 5 | AS `register-scalable-target` exit 254 | buildspec에 클러스터명 `lifesync-cluster` 하드코딩, 실제명과 불일치 | buildspec env에 실제 클러스터/서비스명 반영 |
| 6 | `ValidationException: Unable to assume IAM role` (AS exit 254) | `lifesync-dev-codebuild-role`에 `application-autoscaling:*` 권한 없음 | IAM 인라인 정책 `codebuild-autoscaling-policy` 추가 (`docs/codebuild-role-policy.json` 참고) |
| 7 | ECS 태스크 exit code 3 (Gunicorn worker boot error) | 태스크 정의에 `JWT_SECRET` 환경변수 없음 → `os.environ['JWT_SECRET']` KeyError → 워커 크래시 | SSM `/lifesync360/jwt-secret` 생성 후 태스크 정의 `secrets` 필드에 추가, Execution Role에 `ssm:GetParameters` 권한 추가 |
| 8 | ECS 태스크 포트 불일치 / ALB 헬스체크 실패 루프 | Gunicorn이 8000으로 바인딩, ALB 타겟 그룹은 80 고정 → 헬스체크 실패 → 태스크 교체 무한 루프 | Dockerfile `EXPOSE` 및 `--bind` 포트를 80으로 수정 후 이미지 재빌드 (타겟 그룹 포트는 생성 후 변경 불가) |
| 9 | ECS 배포 stuck (`unable to stop or start tasks`) | 서비스 배포 설정 `minimumHealthyPercent=100, maximumPercent=100` → desiredCount=1 환경에서 롤링 업데이트 불가 | `minimumHealthyPercent=0, maximumPercent=200`으로 변경 |
| 10 | ECS task 부팅 시 `invalid token` (SSM SecureString fetch 실패) — 2026-05-15 | ExecutionRole에 `ssm:GetParameters`만 있고 `kms:Decrypt` 없음 → SecureString 복호화 불가 | `21-lifesync-ecs-existing-vpc.yaml` ExecutionRole inline policy에 `kms:Decrypt` (Condition: `kms:ViaService=ssm.${REGION}.amazonaws.com`) 추가 |
| 11 | SSM endpoint timeout (VPC private subnet) — 2026-05-15 | SSM/SSMMessages/EC2Messages Interface VPC Endpoint 미배포 + SG inbound 443 누락 | `01b-lifesync-vpc-endpoints.yaml` KMS endpoint 추가, `08-database.yaml` SqlOpsSsmVpceSg 에 `CidrIp: 10.0.0.0/16` 443 inbound 추가, ECR Public endpoint 제거 (region 미지원) |
| 12 | CloudFormation 06-S3 stack `EarlyValidation: bucket already exists` (732 신규 계정) — 2026-05-15 | S3 bucket 이름이 전역 unique → 354 계정 이름과 충돌 | `params/data.env` 의 `LIFESYNC_*_S3_BUCKET` 이름에 `-732264765472` suffix 추가 |
| 13 | DynamoDB `RecommendationResultTable` stack 삭제 차단 — 2026-05-15 | `DeletionPolicy: Retain` 으로 cleanup 시 dangling 발생 | 08/08b stack: DynamoDB + SqlAssetsBucket `Retain` → `Delete` (시연/테스트 환경 한정, 운영은 Retain 복귀) |
| 14 | GitHub Actions `mirror-to-codecommit` 가 354 계정으로 동작 — 2026-05-15 | GitHub Secrets `AWS_ACCESS_KEY_ID` 가 354 계정 IAM key | `.github/workflows/platform.yml` 의 `mirror-to-codecommit` job `if: false` 로 임시 비활성. 732 키로 재발급 후 복원 예정 |
| 15 | analytics_aggregator Lambda 가 customer_360_profile 1M 행을 sync invoke 로 한 번에 받으려 함 — 6MB 응답 제한 초과 (2026-05-18) | `_fetch_onprem_profile_map` 이 `action='list_profile_all'` 단일 호출. 1M × ~120 byte = 120MB → sync invoke 응답 제한 초과 | PrivateAPI `GET /internal/profile/list-all?page=N&size=10000` 페이지네이션 신설 + Lambda `list_profile_page` action + analytics_aggregator 페이지 루프 (size=10000 × ~100회) + `_profile_cache` 모듈 전역 메모이즈 (segment/demographic 단계 두 번 재호출 시 1회만 fetch). max_pages=200 안전 상한 |
| 16 | admin `_get_identities` 가 PRIVATE_API_URL 로 PrivateAPI 직접 HTTP 호출 — ECS subnet 에 VPN route 없어 동작 불가 (2026-05-18) | `LifeSyncAppPrivateRt` 의 `0.0.0.0/0` 만 NAT, 04-transitgw/05-vpn `Enable*=false` default + taskdef.json 에 PRIVATE_API_URL env 미주입 → admin 직접 호출은 항상 실패 fallback (`[]`) | A 옵션 (Lambda 경유 통일) — admin app.py 의 `_get_identities` / `PRIVATE_API_URL` 모듈 변수 / `import requests` 통째 제거. 호출처는 `_call_onprem('get_identity_map')` 로 교체. requirements.txt 에서 requests 제거. B 옵션 (직접 HTTP, ECS subnet VPN route + 보안그룹 변경) 은 운영 안정화 후 별도 검토 (3~5일 작업) |
| 17 | platform `taskdef.json` 에 REDIS_HOST env 미주입 — 운영 첫 추천 호출 500 (2026-05-18) | `get_redis()` 가 lazy init 라 부팅은 OK. `/api/recommendations` 첫 호출에서 `RuntimeError('REDIS_HOST 환경변수가 설정되지 않았습니다.')` raise → 추천 핵심 기능 깨짐 | `lifesync360-platform/taskdef.json` 의 environment 에 `{"name":"REDIS_HOST","value":"<ElastiCache cluster endpoint>"}` 추가 (운영 ElastiCache endpoint 확정 후). 평문 env 로 충분 — ElastiCache endpoint 자체는 도메인이라 보안 무관 |
| 18 | `NEW_TABLES_GUIDE.md` 의 CVR 정의 sample SQL 이 운영 코드와 불일치 (2026-05-18) | 문서 sample: `purchased / recommended × 100` (funnel 종합). handler.py: `purchased / NULLIF(SUM(clicked='Y'),0) × 100` (마케팅 표준). 두 정의 의미 다름 | 사용자 정의로 통일: **CVR = `purchased / clicked × 100`** (클릭한 건 중 구매로 이어진 비율, 마케팅 표준). `Service-DB/NEW_TABLES_GUIDE.md` 와 ls 루트 `NEW_TABLES_GUIDE.md` 두 파일에서 컬럼 표 + sample SQL 3 곳 모두 `NULLIF(SUM(clicked_flag='Y'),0)` 패턴으로 수정. handler.py 는 기존 정의 유지 (변경 없음) |
| 19 | 354 계정 IaC 적용 시 ECS 부팅은 OK 지만 런타임에서 깨질 영역 5건 (2026-05-18) | (a) Aurora v3 마이그레이션 미적용 — customer_product_application/_recommend_daily 누락 (b) PrivateAPI 미재배포 (DBUtils + 10 신규 엔드포인트) (c) Lambda 미재배포 (18 action) (d) 23 stack 미배포 (analytics_aggregator + DDB 2 + EventBridge) (e) platform REDIS_HOST env 미주입 (17 참조) | 적용 순서: ① `bash Service-DB/service-db-execution.sh` ② PrivateAPI ansible 재배포 또는 `POST /internal/deploy` 트리거 ③ `aws lambda update-function-code` (onprem_customer_query) ④ `bash docs/today-tables-2026-05-17/deploy-analytics-batch.sh` ⑤ taskdef REDIS_HOST 추가 ⑥ ECS CodePipeline 재배포 ⑦ 검증 후 EventBridge `enable-rule` |
| 20 | 21-ecs stack 에 `customer-profile-sync` Lambda invoke 권한 미정의 — platform `_resolve_global_id` 호출 시 AccessDenied (2026-05-18) | 21 stack inline policy 의 `InvokeOnpremQueryLambda` Sid 가 `lifesync-onprem-customer-query` 만 명시. `customer-profile-sync` 는 별도 Lambda 인데 권한 미정의 | **현재 즉시 영향 0** — `_resolve_global_id` 는 정의만 있고 호출처가 없는 죽은 코드. register 흐름 부활 시 21 stack `InvokeOnpremQueryLambda` Sid Resource 배열에 `customer-profile-sync` ARN 추가 필요 |
| 21 | DDB 분석 테이블명 설계서 V4 vs 인프라/코드 불일치 (2026-05-18 ③) | 설계서: `analytics_segment_daily` / `analytics_demographic_daily`. 23 stack / admin app.py / analytics_aggregator handler / taskdef / GUIDE.md: `analytics_segment_performance` / `analytics_demographic_summary` | sed 일괄 치환 — 6 파일 `*_performance` → `*_daily` / `*_summary` → `*_daily`. ast/JSON 통과. 354계정 23 stack 신규 deploy 시 새 이름으로 생성됨 |
| 22 | S3 동의 스냅샷 일배치 흐름 신설 — admin 의 온프레 동의 직접 호출 0건으로 전환 (2026-05-18 ③) | 설계서 V4 row 21-22 "S3-raw consent/" 정합. 현재 admin 이 매 customer 조회 시 PrivateAPI `_call_onprem('get_consent'/'get_all')` 호출 → VPN latency + PrivateAPI 부하 | 5 신규: ① PrivateAPI `/internal/consent/list-all?page&size` ② Lambda onprem_customer_query `list_consent_page` action ③ Lambda `consent_snapshot_aggregator` (page 루프 + ThreadPoolExecutor 100 PUT) ④ `25-consent-snapshot.yaml` (Lambda+IAM+EventBridge KST 03:00) ⑤ admin `_load_consent_from_s3()` + 호출처 2곳 교체. 적재: `s3://lifesync-raw/consent/dt=YYYY-MM-DD/{global_id}.json` (1M 객체 ≈ 10~15분) |
| 23 | Admin 운영 인스턴스 분리 결정 — Private Subnet EC2 1대 (ECS 공개 admin 폐기) (2026-05-18 ③) | admin 화면에 PII/인구통계/AI 점수 단일 고객 정보 표시 — 외부 ALB 노출 시 보안 위험 | (a) **24 stack EC2 신설** Private Subnet (Aurora/DDB/PrivateAPI 호출 가능한 SG) + SSM Session Manager 활성 + Docker / systemd 로 admin image run (b) **21 stack admin ECS service / target group / task definition 폐기** (또는 21b 로 분리) (c) **CI/CD 변경** — ECR push + SSM run-command 로 EC2 docker pull/restart (ECS update-service 대체) (d) 코드는 동일 image 사용 (`ADMIN_LEVEL` env 분기 불필요). 인프라 작업 ~1.5일 추정 |
| 24 | `users.consent_completed` 컬럼 sync 코드 부재 — 모두 'N' 고정, 설계서 SQL 무용지물 (2026-05-18 ③) | DDL `NOT NULL DEFAULT 'N'` 있지만 `auth_register` / `auth_save_consent` 가 컬럼 UPDATE 안 함. 설계서 V4 SQL `WHERE consent_completed='Y'` 결과는 항상 0 | 사용자 결정 **B 유지** — PrivateAPI `count_users_consented` 의 `users JOIN consent WHERE consent_flag='Y' AND revoke_dt IS NULL` 가 진실. 설계서 문서만 갱신하면 됨. 옵션 A 가려면 save_consent UPDATE + 일괄 백필 + `(user_status, consent_completed)` 인덱스 추가 |
| 25 | PrivateAPI `/internal/pii/{global_id}` 평문 5필드 반환 (RRN 포함) — 운영 시 admin 운영자도 평문 PII 노출 (2026-05-18 ③) | `decrypt_pii(row['rrn_enc'])` 평문 그대로 응답 → Lambda passthrough → admin → 화면. 주민번호 평문 노출은 보안 사고 | A 옵션 (PrivateAPI 단 마스킹) 권장 — `_mask_name/_mask_phone/_mask_email/_mask_address` 헬퍼 추가 + `rrn: None` 기본 응답 + `/internal/pii/{gid}/rrn` 별도 권한 엔드포인트. **결정 대기** |

---

---

## CloudShell 진단 명령어 모음

ECS/CI/CD 파이프라인 트러블슈팅 시 사용한 명령어 정리.

### IAM 역할 정책 확인

```bash
# CodeBuild 역할에 어떤 인라인 정책이 붙어있는지 확인
aws iam list-role-policies --role-name lifesync-dev-codebuild-role

# 특정 인라인 정책 내용 확인
aws iam get-role-policy --role-name lifesync-dev-codebuild-role --policy-name codebuild-autoscaling-policy
```

### ECS 클러스터 / 서비스 확인

```bash
# 계정 내 모든 ECS 클러스터 목록
aws ecs list-clusters --region ap-northeast-2 --output text

# 특정 클러스터의 서비스 목록
aws ecs list-services --cluster <클러스터명> --region ap-northeast-2 --output text

# 서비스 상태 확인 (desiredCount, runningCount, deployments)
aws ecs describe-services \
  --cluster <클러스터명> \
  --services <서비스명> \
  --region ap-northeast-2 \
  --query 'services[0].{status:status,desiredCount:desiredCount,runningCount:runningCount,events:events[0].message}'
```

### ECS 태스크 확인

```bash
# 실행 중인 태스크 목록
aws ecs list-tasks --cluster <클러스터명> --region ap-northeast-2

# 중단된 태스크 목록 (가장 최근 1개)
aws ecs list-tasks --cluster <클러스터명> --desired-status STOPPED --region ap-northeast-2 --query 'taskArns[0]' --output text

# 태스크 상세 확인 (종료 원인, exit code)
aws ecs describe-tasks \
  --cluster <클러스터명> \
  --tasks <태스크ID> \
  --region ap-northeast-2 \
  --query 'tasks[0].{taskDef:taskDefinitionArn,stoppedReason:stoppedReason,containers:containers[*].{name:name,exitCode:exitCode,reason:reason}}'

# 여러 태스크 상태 한 번에 확인
aws ecs describe-tasks \
  --cluster <클러스터명> \
  --tasks <ID1> <ID2> <ID3> \
  --region ap-northeast-2 \
  --query 'tasks[*].{id:taskArn,status:lastStatus,taskDef:taskDefinitionArn}'
```

### ECS 태스크 정의 확인 / 등록

```bash
# 태스크 정의 목록
aws ecs list-task-definitions --region ap-northeast-2 --output text

# 태스크 정의 상세 확인
aws ecs describe-task-definition \
  --task-definition <태스크정의명>:<revision> \
  --region ap-northeast-2 \
  --query 'taskDefinition.containerDefinitions[0].environment'

# 새 태스크 정의 등록 (파일 업로드 후)
aws ecs register-task-definition \
  --cli-input-json file:///home/cloudshell-user/new-taskdef.json \
  --region ap-northeast-2 \
  --query 'taskDefinition.taskDefinitionArn'
```

### CloudWatch 로그 확인

```bash
# 로그 그룹 목록
aws logs describe-log-groups --log-group-name-prefix /ecs --region ap-northeast-2 --query 'logGroups[*].logGroupName' --output text

# 최근 로그 스트리밍
aws logs tail /ecs/lifesync-platform --since 10m --region ap-northeast-2
```

### Application Auto Scaling

```bash
# AS 서비스 연결 역할 생성 (계정당 최초 1회)
aws iam create-service-linked-role --aws-service-name ecs.application-autoscaling.amazonaws.com

# AS 서비스 연결 역할 trust policy 확인
aws iam get-role \
  --role-name AWSServiceRoleForApplicationAutoScaling_ECSService \
  --query 'Role.AssumeRolePolicyDocument'

# scalable target 수동 등록 (권한 테스트용)
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/<클러스터명>/<서비스명> \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 1 --max-capacity 4 \
  --region ap-northeast-2
```

### ALB 타겟 그룹 확인

```bash
# 타겟 그룹 설정 확인 (포트, 헬스체크 경로)
aws elbv2 describe-target-groups \
  --region ap-northeast-2 \
  --query 'TargetGroups[?contains(TargetGroupName, `AppTa`)].{Name:TargetGroupName,Port:Port,HealthCheckPort:HealthCheckPort,HealthCheckPath:HealthCheckPath}'
```

### SSM Parameter Store

```bash
# SSM 파라미터 생성 (SecureString, JWT 시크릿)
aws ssm put-parameter \
  --name /lifesync360/jwt-secret \
  --value "$(openssl rand -hex 32)" \
  --type SecureString \
  --region ap-northeast-2

# Execution Role에 SSM 읽기 권한 추가
aws iam put-role-policy \
  --role-name <ExecutionRole명> \
  --policy-name ecs-ssm-secret \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["ssm:GetParameters"],"Resource":"arn:aws:ssm:ap-northeast-2:354493396671:parameter/lifesync360/*"}]}'
```

---

## GitHub Secrets 주의사항

| Secret 이름 | 설명 | 주의사항 |
|-------------|------|---------|
| `AWS_ACCESS_KEY_ID` | IAM 액세스 키 ID (20자, `AKIA`로 시작) | **엑셀로 열지 말 것** — `+` 시작 값에 `=` 자동 추가되어 오염됨 |
| `AWS_SECRET_ACCESS_KEY` | IAM 시크릿 키 (40자) | 메모장에서 직접 복사, 앞뒤 공백 없이 입력 |

---

## 세션 2026-05-22 트러블슈팅

| 순서 | 오류 | 원인 | 해결 |
|------|------|------|------|
| 21 | 시뮬레이터 EC2에서 `secretsmanager:GetSecretValue` AccessDeniedException | 온프레미스 시뮬레이터 EC2 IAM 역할(`OnpremSimRole`)에 Secrets Manager 권한 없음 | `aws iam put-role-policy`로 인라인 정책 `secrets-db-access` 추가 (`secretsmanager:GetSecretValue` on `/lifesync/dev/db/master-*`) |
| 22 | 시뮬레이터 EC2에서 `lambda:InvokeFunction` AccessDeniedException (로그인 503) | `OnpremSimRole`에 Lambda 호출 권한 없음 | `lambda-invoke-onprem` 인라인 정책 추가 (`lifesync-onprem-customer-query` 한정) |
| 23 | 시뮬레이터 EC2에서 S3 403 Forbidden (`aws s3 cp` 실패) | `OnpremSimRole`에 S3 GetObject 권한 없음 | `s3-deploy-read` 인라인 정책 추가 (`lifesync-732-raw/deploy/*`) |
| 24 | 시뮬레이터 EC2에서 DynamoDB `GetItem` ValidationException | 테이블 키 스키마가 복합키(`global_id` HASH + `update_time` RANGE)인데 `GetItem`에 HASH 키만 전달 | app.py의 `_fetch_ddb_meta`는 `Query`로 처리 — 테스트 스크립트에서 `Query` 사용으로 수정. `OnpremSimRole`에 `dynamodb-customer-result` 정책 추가 |
| 25 | Redis `WRONGTYPE Operation against a key holding the wrong kind of value` | `rec:G000000001` 키가 이전에 `zset` 타입으로 적재되어 있었음. app.py는 `setex`(string 타입)로 읽기 시도 | `redis.delete('rec:G000000001')`로 기존 키 삭제 후 재시도 |
| 26 | 시뮬레이터 EC2 → Aurora/Redis 연결 타임아웃 | Aurora SG, Redis SG 인바운드에 시뮬레이터 EC2 SG 허용 규칙 없음 (같은 VPC지만 SG 미개방) | `aws ec2 authorize-security-group-ingress`로 각각 추가: Aurora SG ← 시뮬레이터 SG (3306), Redis SG ← 시뮬레이터 SG (6379) |
| 27 | Windows PowerShell Compress-Archive로 만든 zip → Linux에서 압축 해제 실패 | Windows zip에 `\` 경로 구분자가 그대로 저장됨. Linux unzip이 경로 인식 못하고 파일명으로 처리 | `fix_extract.py` 작성: zipfile 모듈로 직접 파일별 iterate → `info.filename.replace('\', '/')` 후 대상 경로 생성 |
| 28 | lifesync360 로그인 엔드포인트 404 | 코드 라우트는 `/api/login`인데 `/api/auth/login`으로 요청 | `grep -n "@app.route" app.py`로 실제 라우트 확인 후 수정 |
| 29 | Flask 앱 재시작 시 "Address already in use" — 이전 프로세스 잔존 | `start_ls360.sh`의 `pkill` 패턴이 `python3 /opt/ls360/app.py`인데 실제 프로세스는 venv python 경로로 실행됨 → kill 실패 → 포트 충돌 | `pkill -9 -f "python.*app.py"`로 패턴 변경 |
| 30 | localStorage token 주입 후 홈 화면이 로그인으로 리다이렉트 | Playwright에서 `localStorage.setItem('access_token', token)`으로 저장했으나 앱 코드는 `localStorage.getItem('ls_token')` 사용 | `grep -n "localStorage" templates/index.html`으로 실제 키 확인 → `ls_token`으로 수정 |
| 31 | CFN 스택 24(`admin-windows-ec2`) DELETE_FAILED — AdminInstanceSg 삭제 불가 | Aurora SG, Redis SG, SSM VPCE SG 세 곳에 admin EC2 SG(`sg-05442a13d8b9a3bcb`)가 인바운드 소스로 참조되어 있음 | 세 SG에서 admin SG 참조 인바운드 규칙 모두 수동 제거 후 스택 재삭제 |
| 32 | `start_ls360.sh` Redis 엔드포인트 하드코딩 — 732 전용 | `export REDIS_HOST="lif-re-dm1gt0avdbns..."` — 354 계정에서 존재하지 않는 엔드포인트 | Secrets Manager `/lifesync/dev/db/master`에서 `REDIS_HOST` 키 함께 읽도록 변경 (DB 크레덴셜과 동일 패턴) |

