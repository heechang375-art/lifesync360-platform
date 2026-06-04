# 클라우드 인프라 구축 시 처리 목록

---

## 1. 로컬 테스트 코드 → 클라우드 환경 변경 사항

로컬에서 동작하도록 설정된 값들로, 클라우드 배포 시 반드시 변경해야 함.

### 환경변수 / 시크릿

| 항목 | 로컬 기본값 | 클라우드 처리 방법 |
|------|------------|------------------|
| `USE_MOCK` | `true` | ECS 태스크 정의에서 `false`로 설정 |
| `JWT_SECRET` | `dev-jwt-secret-lifesync360-32bytes!!` | Secrets Manager: `lifesync/jwt` |
| `ADMIN_USER` | `admin` | Secrets Manager 또는 ECS 환경변수 |
| `ADMIN_PASSWORD` | `admin1234` | Secrets Manager: `lifesync/admin` |
| `SECRET_KEY` (admin Flask 세션) | `admin-dev-secret-32bytes-lifesync!!` | Secrets Manager: `lifesync/admin-secret` |
| `AURORA_HOST` | 미설정 (USE_MOCK=true 시 불필요) | RDS 엔드포인트 |
| `REDIS_HOST` | 미설정 | ElastiCache 엔드포인트 |
| `DYNAMO_TABLE` | `lifesync-scores` (기본값) | Terraform 출력값으로 주입 |

### taskdef.json (platform)
- `ACCOUNT_ID` 플레이스홀더 4곳 → 실제 AWS 계정 ID로 치환
- `REDIS_HOST` secretsManager ARN → 실제 ARN 확인 후 수정

> **admin-platform은 ECS가 아니라 Windows EC2 + CodeDeploy로 배포 확정(2026-05-27, Task Scheduler 직접 구동) → taskdef.json·Dockerfile 해당 없음.**

### Dockerfile (platform)
- 현재 Dockerfile도 개발 서버 사용 여부 확인 후 gunicorn 전환

---

## 2. 클라우드에서 신규 구축이 필요한 것

### 2-1. Lambda: API Gateway 인증 (보안 필수)
**현재 상태:** `POST /ingest` 엔드포인트가 완전 공개. 누구나 호출 가능.  
**해결 방법:**
- API Gateway Usage Plan + API Key 생성
- GCP Cloud Run에서 AWS Secrets Manager에 API Key 저장 후 호출 시 `x-api-key` 헤더 전송
- Lambda 함수 URL 방식으로 전환 시 IAM 인증 사용 가능

**작업 위치:** Terraform (API GW 리소스) + GCP Cloud Run 환경변수

---

### 2-2. Lambda: DLQ (Dead Letter Queue)
**현재 상태:** Lambda 실패 시 데이터 유실. DynamoDB PUT / Aurora UPDATE 중 하나라도 실패하면 GCP 분석 결과 손실.  
**해결 방법:**
- SQS 큐 1개 생성 (`lifesync-ingest-dlq`)
- Lambda 함수 설정에서 DLQ 연결
- DLQ에 쌓인 메시지 재처리용 Lambda 또는 운영 알람 연결

**작업 위치:** Terraform (SQS + Lambda DLQ 설정)

---

### 2-3. Aurora: 커넥션 풀링
**현재 상태:** 요청마다 `pymysql.connect()` 신규 생성/종료. 동시 요청 증가 시 Aurora max_connections 한계 도달 가능.  
**해결 방법 (권장):** RDS Proxy 앞에 두기 (코드 변경 없음, 엔드포인트만 RDS Proxy로 변경)  
**대안:** SQLAlchemy `create_engine(pool_size=5, pool_pre_ping=True)`으로 코드 변경

**작업 위치:** Terraform (RDS Proxy 리소스) 또는 app.py 수정

---

### 2-4. CloudWatch 알람
구축 후 최소한 아래 알람은 설정 필요:

| 알람 | 기준 | 액션 |
|------|------|------|
| Lambda 오류율 | 5분간 오류 3회 이상 | SNS → 슬랙/이메일 |
| ECS 메모리 사용률 | 85% 이상 | SNS 알림 |
| Aurora CPU | 80% 이상 | SNS 알림 |
| API Gateway 5xx | 1분간 10회 이상 | SNS 알림 |

**작업 위치:** Terraform (CloudWatch Alarm 리소스)

---

### 2-5. API Gateway: Throttling
**현재 상태:** Lambda 과호출 방지 장치 없음.  
**해결 방법:** API Gateway Stage에 Rate limit 설정
- 기본: 1000 req/s, Burst: 2000
- `/ingest` 엔드포인트: 100 req/s (GCP 호출 빈도 기준으로 조정)

**작업 위치:** Terraform (API GW Stage 설정)

---

### 2-6. admin-platform 배포 구성 — ✅ 완료 (2026-05-27)
EC2 직접 배포 + CodeDeploy 파이프라인으로 확정·구성 완료. 상세는 HANDOFF.md / project-progress.md 참고.

---

### 2-7. CI/CD: admin-platform deploy job — ✅ 완료 (2026-05-27)
admin CI/CD deploy job(CodeDeploy 파이프라인) 구성 완료. 상세는 HANDOFF.md 참고.

---

### 2-8. Secrets Manager 사전 생성 목록

| Secret 이름 | 내용 | 사용처 |
|-------------|------|--------|
| `lifesync/aurora` | `{"host":"...","user":"...","password":"..."}` | platform, admin, Lambda |
| `lifesync/jwt` | `{"secret":"..."}` | platform |
| `lifesync/redis` | `{"host":"..."}` | platform |
| `lifesync/admin` | `{"user":"...","password":"...","secret_key":"..."}` | admin |
| `lifesync/ingest-api-key` | `{"key":"..."}` | Lambda API GW (2-1 구축 후) |

---

## 3. 온프레미스 관련

### VPN 터널 구축 후 처리
- Ansible Control Node EC2 프로비저닝 (로컬 VM 아님)
- 온프레미스 VM 실제 배포 (현재는 로컬 VirtualBox VM 대상)
- `onprem-prod-repo/ansible/` Playbook의 inventory 파일에서 로컬 IP(192.168.56.x) → 실제 온프레미스 IP로 변경

### 크로스VM 토크나이제이션 호출 테스트 (로컬 완료 후)
- ls-token VM 기동 확인 후 `/tokenize` 엔드포인트 실제 호출 검증
- `local-test-remaining.md` 잔여 테스트 케이스 3개 처리
