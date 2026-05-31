# Control Node 배포 가이드 (14a / 14b / 14c)

> 최종 수정: 2026-05-12

## 구조

```
로컬 PC
  ↓ aws ssm start-session
Ansible Control Node EC2 (Management VPC private subnet)
  ↓ SSH over VPN 터널
ls-api  (브리지 IP — VPN 엔드포인트)
  ↓ ProxyJump
ls-db / ls-token  (Host-Only IP)
```

---

## 스택 구성

| 스택 파일 | 스택명 | 역할 |
|----------|--------|------|
| `14a-ansible-iam.yaml` | `lifesync-dev-ansible-iam` | IAM 롤 + 인스턴스 프로파일 |
| `14b-ansible-ec2.yaml` | `lifesync-dev-ansible-ec2` | EC2 + UserData (venv, SSH 키, git clone) |
| `14c-ansible-key-publish.yaml` | `lifesync-dev-ansible-key-publish` | SSM Association: 공개키 SSM 등록 + 온프레미스 푸시 |

---

## 배포 순서

### 사전 조건

- VPN 터널 ESTABLISHED 상태 (`sudo ipsec status` on ls-api)
- 로컬 IAM 자격증명에 CloudFormation, EC2, SSM 권한
- Session Manager Plugin 설치 (`SessionManagerPluginSetup.exe`)
- CodeCommit 레포 생성 완료 (`onprem-prod-repo`)

---

### 1단계 — 14a: IAM

```bash
aws cloudformation deploy \
  --template-file 14a-ansible-iam.yaml \
  --stack-name lifesync-dev-ansible-iam \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-2

# 출력 확인 (14b에 필요)
PROFILE_NAME=$(aws cloudformation describe-stacks \
  --stack-name lifesync-dev-ansible-iam \
  --query 'Stacks[0].Outputs[?OutputKey==`AnsibleControlNodeInstanceProfileName`].OutputValue' \
  --output text --region ap-northeast-2)
echo "Profile: $PROFILE_NAME"
```

---

### 2단계 — 14b: EC2 + UserData

파라미터 확인:

| 파라미터 | 확인 방법 |
|----------|----------|
| `AmiId` | EC2 콘솔 → AMI Catalog → AL2023 최신 |
| `ManagementSubnetId` | VPC 콘솔 → Management VPC private subnet |
| `ManagementSgId` | VPC 콘솔 → SG (아웃바운드 443 허용 필요) |
| `AnsibleControlNodeInstanceProfileName` | 1단계 `$PROFILE_NAME` |

```bash
aws cloudformation deploy \
  --template-file 14b-ansible-ec2.yaml \
  --stack-name lifesync-dev-ansible-ec2 \
  --parameter-overrides \
    AmiId=<AL2023 AMI ID> \
    InstanceType=t3.small \
    ManagementSubnetId=<Management VPC private subnet ID> \
    ManagementSgId=<Management VPC SG ID> \
    AnsibleControlNodeInstanceProfileName=$PROFILE_NAME \
  --region ap-northeast-2

# 출력 확인 (14c에 필요)
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name lifesync-dev-ansible-ec2 \
  --query 'Stacks[0].Outputs[?OutputKey==`AnsibleControlInstanceId`].OutputValue' \
  --output text --region ap-northeast-2)
echo "Instance ID: $INSTANCE_ID"
```

UserData 실행 순서 (14b 내부):
```
ansible 유저 생성 → sudoers → 패키지 설치(dnf/apt/yum) → ansible-core venv
→ SSH 키 생성 (/home/ansible/.ssh/id_rsa) → CodeCommit git clone → hosts.yaml
→ (선택) VPN 점검 wait_for
```

완료까지 약 5~15분. 로그: `/var/log/ansible-bootstrap.log`

---

### 3단계 — 14c: SSM Association

```bash
aws cloudformation deploy \
  --template-file 14c-ansible-key-publish.yaml \
  --stack-name lifesync-dev-ansible-key-publish \
  --parameter-overrides \
    AnsibleControlInstanceId=$INSTANCE_ID \
  --region ap-northeast-2
```

14c가 하는 일:
1. EC2에서 `/home/ansible/.ssh/id_rsa.pub` 읽기 (최대 15분 대기)
2. `aws ssm put-parameter` → `/lifesync/dev/ansible/public-key` 등록
3. (선택) `SsmAppendAnsiblePublicKey=true`면 타깃 EC2 authorized_keys에 SSM SendCommand로 추가
4. (선택) `VpnPushOnpremHost` 지정 시 VPN SSH로 온프레미스 authorized_keys에 직접 푸시

---

## 배포 후 검증

### 로컬 PC에서

```bash
# SSM 접속
aws ssm start-session --target $INSTANCE_ID --region ap-northeast-2

# 공개키 SSM Parameter Store 등록 확인
aws ssm get-parameter \
  --name /lifesync/dev/ansible/public-key \
  --region ap-northeast-2 \
  --query Parameter.Value --output text
# → ssh-rsa AAAA... 출력되면 정상
```

### EC2 내부에서

```bash
# UserData 완료 로그 확인
sudo tail -100 /var/log/ansible-bootstrap.log
# 마지막 줄: "[bootstrap] 14b 완료: venv·키·hosts.yaml..."

# SSH 키 확인
ls -la /home/ansible/.ssh/
# id_rsa (600), id_rsa.pub (644) 모두 존재해야 함

# Ansible 버전 확인
/opt/ansible-venv/bin/ansible --version

# CodeCommit 레포 클론 확인
ls /opt/ansible/onprem-prod-repo/

# VPN 연결 상태에서 온프레미스 VM ping
ansible all -m ping \
  -i /opt/ansible/onprem-prod-repo/ansible/inventory/hosts.yml \
  --vault-password-file ~/.vault_pass
```

---

## 문제 해결

### SSH 키 미생성

증상: `ls /home/ansible/.ssh/id_rsa.pub` → No such file

원인 1 — git clone 실패로 UserData 중단 (`set -euo pipefail`):
```bash
# 로그에서 git clone 에러 확인
sudo grep -i "error\|failed\|clone" /var/log/ansible-bootstrap.log
```

원인 2 — sudo PATH 문제 (`env: 'git': No such file or directory`):
- 14b에서 이미 `/usr/bin/git` 전체 경로로 수정 완료

수동 복구:
```bash
sudo install -d -m 0700 -o ansible -g ansible /home/ansible/.ssh
sudo -u ansible ssh-keygen -t rsa -b 4096 -N "" -f /home/ansible/.ssh/id_rsa -q
sudo chown -R ansible:ansible /home/ansible/.ssh
```

---

### SSM start-session 오류

| 에러 | 원인 | 해결 |
|------|------|------|
| `Could not connect to endpoint URL: ssm.ap-northease-2...` | 리전명 오타 | `aws configure set region ap-northeast-2` |
| `403 Forbidden` | IAM에 `ssm:StartSession` 없음 | IAM 정책 추가 또는 admin 프로파일 사용 |
| `Session Manager plugin not found` | Plugin 미설치 | SessionManagerPluginSetup.exe 설치 후 터미널 재시작 |

---

### git clone 실패 (CodeCommit)

```bash
# EC2에서 IAM 권한 확인
aws sts get-caller-identity
aws codecommit get-repository --repository-name onprem-prod-repo

# credential helper 확인
sudo -u ansible git config --global --list | grep credential
```

NAT GW 있으면 퍼블릭 CodeCommit 엔드포인트로 접근 가능.
없으면 `01c-management-vpc-endpoints.yaml`로 CodeCommit VPC Endpoint 추가 (선택).

---

### 스택 재배포

14b만 재배포 시 EC2가 교체됨 → 14c도 새 INSTANCE_ID로 재배포 필요:

```bash
# 14b 재배포
aws cloudformation deploy --template-file 14b-ansible-ec2.yaml \
  --stack-name lifesync-dev-ansible-ec2 ...

# 새 INSTANCE_ID 조회
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=lifesync-dev-management-ec2-ansible" \
            "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text --region ap-northeast-2)

# 14c 재배포
aws cloudformation deploy --template-file 14c-ansible-key-publish.yaml \
  --stack-name lifesync-dev-ansible-key-publish \
  --parameter-overrides AnsibleControlInstanceId=$INSTANCE_ID \
  --region ap-northeast-2
```

---

## 로컬 스크립트

```bash
bash scripts/deploy-control-node.sh
```

스크립트가 하는 일:
1. VPN 터널 연결 여부 확인 (연결 안 됐으면 `update-vpn-tunnel.sh` 실행)
2. EC2 Name 태그(`lifesync-dev-management-ec2-ansible`)로 InstanceId + PrivateIp 조회
3. SSM Agent Online 대기 (최대 5분)
4. SSM SendCommand로 `/home/ansible/.ssh/id_rsa.pub` 존재 확인 (UserData 완료 여부)

---

## 주요 경로

| 항목 | 값 |
|------|----|
| UserData 로그 | `/var/log/ansible-bootstrap.log` |
| SSH 키 (ansible 유저) | `/home/ansible/.ssh/id_rsa` |
| Ansible venv | `/opt/ansible-venv/bin/ansible` |
| Ansible 소스 | `/opt/ansible/onprem-prod-repo` |
| SSM 공개키 파라미터 | `/lifesync/dev/ansible/public-key` |
| EC2 Name 태그 | `lifesync-dev-management-ec2-ansible` |
