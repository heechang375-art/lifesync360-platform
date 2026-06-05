# 클라우드 배포 절차

프로젝트: LifeSync360 | 리전: ap-northeast-2

---

## 사전 준비

- AWS 계정 ID 확인
- AWS CLI 설정 (`aws configure`)
- CloudFormation 배포 권한 확인 (AdministratorAccess 권장)

---

## 1단계 — CloudFormation 스택 배포

순서 엄수. 각 스택 배포 완료 후 다음 단계 진행.

```bash
# 배포 명령 공통 형식
aws cloudformation deploy \
  --template-file <파일경로> \
  --stack-name <스택명> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-2
```

### 네트워크

| 순서 | 파일 | 스택명 |
|------|------|--------|
| 1 | infra/network/vpc.yaml | lifesync-vpc |
| 2 | infra/network/subnets.yaml | lifesync-subnets |
| 3 | infra/network/igw.yaml | lifesync-igw |
| 4 | infra/network/nat-gateway.yaml | lifesync-nat |
| 5 | infra/network/route-tables.yaml | lifesync-rt |

### 보안 / IAM

| 순서 | 파일 | 스택명 |
|------|------|--------|
| 6 | infra/sg.yaml | lifesync-sg |
| 7 | infra/iam.yaml | lifesync-iam |

### 데이터

| 순서 | 파일 | 스택명 |
|------|------|--------|
| 8 | infra/data/s3.yaml | lifesync-s3 |
| 9 | infra/data/secrets-manager.yaml | lifesync-secrets |
| 10 | infra/data/dynamodb.yaml | lifesync-dynamodb |
| 11 | infra/data/aurora.yaml | lifesync-aurora |
| 12 | infra/data/elasticache.yaml | lifesync-elasticache |

> **9번 배포 후 반드시 멈추고 Secrets Manager 값 입력 후 11~12번 진행**
> (아래 2단계 참고)

### 컴퓨트

| 순서 | 파일 | 스택명 |
|------|------|--------|
| 13 | infra/compute/ecr.yaml | lifesync-ecr |
| 14 | infra/compute/alb.yaml | lifesync-alb |
| 15 | infra/compute/ecs-cluster.yaml | lifesync-ecs-cluster |
| 16 | infra/compute/sqs.yaml | lifesync-sqs |
| 17 | infra/compute/lambda.yaml | lifesync-lambda |
| 18 | infra/compute/api-gateway.yaml | lifesync-apigw |
| 19 | infra/compute/ecs-platform.yaml | lifesync-ecs-platform |
| 20 | infra/compute/ecs-admin.yaml | lifesync-ecs-admin |

> **19~20번 전에 ECR에 이미지 푸시 필요** (아래 3단계 참고)

### 파이프라인

| 순서 | 파일 | 스택명 |
|------|------|--------|
| 21 | infra/pipeline/codecommit.yaml | lifesync-codecommit |
| 22 | infra/pipeline/codebuild.yaml | lifesync-codebuild |
| 23 | infra/pipeline/codepipeline.yaml | lifesync-codepipeline |

### 모니터링

| 순서 | 파일 | 스택명 |
|------|------|--------|
| 24 | infra/observability/cloudwatch-logs.yaml | lifesync-logs |
| 25 | infra/observability/sns.yaml | lifesync-sns |
| 26 | infra/observability/cloudwatch-alarms.yaml | lifesync-alarms |

SNS 스택 배포 시 이메일 파라미터 필요:
```bash
aws cloudformation deploy \
  --template-file infra/observability/sns.yaml \
  --stack-name lifesync-sns \
  --parameter-overrides AlertEmail=heechang375@gmail.com \
  --region ap-northeast-2
```

### 온프레미스 연결 (VPN 구성 시)

| 순서 | 파일 | 스택명 |
|------|------|--------|
| 27 | infra/optional/vpn.yaml | lifesync-vpn |
| 28 | infra/compute/control-node.yaml | lifesync-control-node |
| 29 | infra/optional/vpc-endpoints.yaml | lifesync-vpc-endpoints |

```bash
# 27. VPN
aws cloudformation deploy \
  --template-file infra/optional/vpn.yaml \
  --stack-name lifesync-vpn \
  --parameter-overrides \
    OnPremPublicIp=<온프레미스_공인IP> \
    OnPremCidr=192.168.56.0/24 \
  --region ap-northeast-2

# 28. Control Node (VPN 배포 완료 후)
VPC_ID=$(aws cloudformation list-exports \
  --query "Exports[?Name=='lifesync-vpc-VpcId'].Value" \
  --output text --region ap-northeast-2)

SUBNET_ID=$(aws cloudformation list-exports \
  --query "Exports[?Name=='lifesync-subnets-AppSubnet1Id'].Value" \
  --output text --region ap-northeast-2)

aws cloudformation deploy \
  --template-file infra/compute/control-node.yaml \
  --stack-name lifesync-control-node \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    VpcId=$VPC_ID \
    SubnetId=$SUBNET_ID \
  --region ap-northeast-2
```

> **28번 배포 전에 반드시 Secrets Manager ansible 관련 3개 값 입력 완료**
> (아래 2단계 ansible 항목 참고)

---

## 2단계 — Secrets Manager 값 입력

9번 스택 배포 후 Aurora/ECS 배포 전에 실행.

```bash
# Aurora DB 자격증명
aws secretsmanager put-secret-value \
  --secret-id lifesync/aurora \
  --secret-string '{"host":"(11번 배포 후 입력)","user":"lifesync_app","password":"<강력한_패스워드>"}' \
  --region ap-northeast-2

# JWT 시크릿
aws secretsmanager put-secret-value \
  --secret-id lifesync/jwt \
  --secret-string '{"secret":"<32바이트_이상_랜덤문자열>"}' \
  --region ap-northeast-2

# Redis 호스트
aws secretsmanager put-secret-value \
  --secret-id lifesync/redis \
  --secret-string '{"host":"(12번 배포 후 입력)"}' \
  --region ap-northeast-2

# Admin 자격증명
aws secretsmanager put-secret-value \
  --secret-id lifesync/admin \
  --secret-string '{"user":"admin","password":"<강력한_패스워드>","secret_key":"<32바이트_랜덤>"}' \
  --region ap-northeast-2

# 온프레미스 DB 자격증명 (토큰서버용)
aws secretsmanager put-secret-value \
  --secret-id lifesync/onprem-db \
  --secret-string '{"host":"<온프레미스_DB_IP>","username":"lifesync","password":"<DB_패스워드>","root_password":"<ROOT_패스워드>"}' \
  --region ap-northeast-2

# Control Node 관련 (28번 스택 배포 전 필수)
aws secretsmanager put-secret-value \
  --secret-id lifesync/ansible-vm \
  --secret-string '{"password":"<온프레미스_ansible_유저_패스워드>"}' \
  --region ap-northeast-2

aws secretsmanager put-secret-value \
  --secret-id lifesync/ansible-vault \
  --secret-string '{"password":"<Ansible_Vault_패스워드>"}' \
  --region ap-northeast-2

aws secretsmanager put-secret-value \
  --secret-id lifesync/deploy-token \
  --secret-string '{"token":"<임의_토큰_문자열>"}' \
  --region ap-northeast-2
```

Aurora 엔드포인트는 11번 스택 배포 후:
```bash
aws cloudformation describe-stacks \
  --stack-name lifesync-aurora \
  --query "Stacks[0].Outputs[?OutputKey=='ClusterEndpoint'].OutputValue" \
  --output text
```

---

## 3단계 — ECR 부트스트랩

별도 이미지 푸시 불필요.

ECS Task Definition 초기값은 `public.ecr.aws/docker/library/python:3.11-slim`을 직접 참조하므로
Private ECR이 비어 있어도 CloudFormation 배포가 정상 완료된다.
서비스는 `DesiredCount: 0`으로 생성되므로 이미지 pull은 발생하지 않는다.

첫 CI/CD 파이프라인 실행 시 실제 앱 이미지로 자동 교체되고 서비스가 기동된다.

---

## 4단계 — 온프레미스 Ansible Control Node EC2 설정

VPN 터널 구성 완료 후 진행.

### EC2 인스턴스 요구사항
- AMI: Ubuntu 22.04
- Tag: `Name=ansible-control-node`
- IAM Role: SSM + CodeCommit + SSM SendCommand 권한
- SSH 키: `lifesync360-onprem.pem`

### EC2 초기 설정

```bash
# Ansible 설치
sudo apt update
sudo apt install -y ansible python3-pip awscli git

# CodeCommit HTTPS 자격증명 헬퍼 설정
git config --global credential.helper '!aws codecommit credential-helper $@'
git config --global credential.UseHttpPath true

# SSH 키 배포
mkdir -p ~/.ssh
# lifesync360-onprem.pem 업로드 후
chmod 600 ~/.ssh/lifesync360-onprem.pem

# 레포 클론
git clone https://git-codecommit.ap-northeast-2.amazonaws.com/v1/repos/onprem-prod-repo /opt/ansible/onprem-prod-repo
```

### SSM Agent 확인
```bash
sudo systemctl status amazon-ssm-agent
```

---

## 5단계 — 온프레미스 인벤토리 IP 변경

`onprem-prod-repo/ansible/inventory/hosts.yml`에서 로컬 VirtualBox IP → 실제 온프레미스 IP로 변경:

```yaml
ls-db:
  ansible_host: <실제_DB_서버_IP>
ls-token:
  ansible_host: <실제_토큰_서버_IP>
  mysql_vm_ip: <실제_DB_서버_IP>
ls-api:
  ansible_host: <실제_API_서버_IP>
```

변경 후 CodeCommit에 푸시 → EC2 control node에서 ansible-pull로 배포.

---

## 6단계 — 초기 온프레미스 배포

EC2 control node에서:

```bash
cd /opt/ansible/onprem-prod-repo
ansible-playbook ansible/site.yml -i ansible/inventory/hosts.yml
```

---

## 7단계 — 검증

```bash
# ALB 헬스체크
curl http://<ALB_DNS>/health

# 온프레미스 토큰서버
curl http://<토큰서버_IP>:8000/health

# 온프레미스 API 서버
curl http://<API서버_IP>/health

# Lambda → API Gateway
curl -X POST https://<APIGW_ID>.execute-api.ap-northeast-2.amazonaws.com/v1/ingest \
  -H "x-api-key: <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

---

## 선택 배포 (필요 시)

| 상황 | 파일 | 스택명 |
|------|------|--------|
| Aurora 동시요청 증가 | infra/optional/rds-proxy.yaml | lifesync-rdsproxy |
| 멀티VPC 확장 | infra/optional/tgw.yaml | lifesync-tgw |
