# LifeSync360 프로젝트 진행 기록

---

## On-Prem IP 변경 추적 (재변경 시 여기 참고)

> 온프레미스 VM 브리지 IP가 바뀔 때마다 아래 위치를 모두 동기화해야 한다.

**현재 IP: `192.168.45.157`** (브리지 어댑터, 2026-05-23 변경)
이전 IP: `172.16.1.73`

> **2026-05-26 주의**: VPN 재구성 중. 현재 EC2 `start-admin.ps1`에 `ONPREM_BASE_URL=http://172.16.1.73` 설정됨 (구IP). Lambda `PRIVATE_API_URL`도 `172.16.1.73`. VPN 완료 후 1·2번 항목 반드시 업데이트 필요.
> VPN 연결 상태: `vpn-06b4f730ddfd17bc4` / TGW attach `tgw-attach-07d70236bcd767f75` — AcceptedRouteCount=0 (스태틱 라우트 미추가 상태)

### 변경 필요 위치 (총 5곳)

| # | 위치 | 변경 방법 | 현재 값 |
|---|------|-----------|---------|
| 1 | `admin-platform/app.py` line 104 `ONPREM_BASE_URL` 기본값 | 코드 수정 후 patch 배포 | `http://192.168.45.157` |
| 2 | Lambda `lifesync-onprem-customer-query` 환경변수 `PRIVATE_API_URL` | `aws lambda update-function-configuration --function-name lifesync-onprem-customer-query --environment "Variables={PRIVATE_API_URL=http://<새IP>}"` | `http://192.168.45.157` |
| 3 | TGW route table `tgw-rtb-05da340fa6bc057c7` static 라우트 | 기존 삭제 후 신규 CIDR 추가: `aws ec2 delete-transit-gateway-route --transit-gateway-route-table-id tgw-rtb-05da340fa6bc057c7 --destination-cidr-block 192.168.45.0/24` → `aws ec2 create-transit-gateway-route ... --destination-cidr-block <새CIDR>/24 --transit-gateway-attachment-id tgw-attach-0fb3c66d992387f40` | `192.168.45.0/24 → tgw-attach-0fb3c66d992387f40` |
| 4 | Management VPC private RT `rtb-005a802a3c7f28634` | `aws ec2 delete-route --route-table-id rtb-005a802a3c7f28634 --destination-cidr-block 192.168.45.0/24` → `aws ec2 create-route --route-table-id rtb-005a802a3c7f28634 --destination-cidr-block <새CIDR>/24 --transit-gateway-id tgw-07aff02d25c808e1f` | `192.168.45.0/24 → TGW` |
| 5 | lifesync-vpc app-private-rt `rtb-06d02c5c017083ac4` | 위 4번과 동일 방식 (`--route-table-id rtb-06d02c5c017083ac4`) | `192.168.45.0/24 → TGW` |

### IP만 바뀌고 서브넷(/24)은 그대로일 때 (가장 흔한 케이스)

```bash
NEW_IP=<새IP>  # 예: 192.168.45.200

# 1. app.py 수정 (line 104 ONPREM_BASE_URL 기본값) → patch 배포

# 2. Lambda 환경변수
aws lambda update-function-configuration \
  --function-name lifesync-onprem-customer-query \
  --environment "Variables={PRIVATE_API_URL=http://$NEW_IP}"

# 서브넷이 같으면 라우팅(3~5)은 건드릴 필요 없음
```

### 서브넷까지 바뀔 때 (예: 192.168.45.0/24 → 192.168.46.0/24)

```bash
OLD_CIDR=192.168.45.0/24
NEW_CIDR=192.168.46.0/24
TGW_ID=tgw-07aff02d25c808e1f
VPN_ATTACH=tgw-attach-0fb3c66d992387f40

# TGW route table
aws ec2 delete-transit-gateway-route --transit-gateway-route-table-id tgw-rtb-05da340fa6bc057c7 --destination-cidr-block $OLD_CIDR
aws ec2 create-transit-gateway-route --transit-gateway-route-table-id tgw-rtb-05da340fa6bc057c7 --destination-cidr-block $NEW_CIDR --transit-gateway-attachment-id $VPN_ATTACH

# Management VPC RT
aws ec2 delete-route --route-table-id rtb-005a802a3c7f28634 --destination-cidr-block $OLD_CIDR
aws ec2 create-route --route-table-id rtb-005a802a3c7f28634 --destination-cidr-block $NEW_CIDR --transit-gateway-id $TGW_ID

# lifesync-vpc app-private-rt
aws ec2 delete-route --route-table-id rtb-06d02c5c017083ac4 --destination-cidr-block $OLD_CIDR
aws ec2 create-route --route-table-id rtb-06d02c5c017083ac4 --destination-cidr-block $NEW_CIDR --transit-gateway-id $TGW_ID
```

### 온프레미스 VM (ls-api) ipsec.conf도 확인

CGW(VPN 터미네이션) 설정에 `rightsubnet`이 있으면 서브넷 변경 시 함께 수정 필요.
현재 CGW IP: `175.114.128.81` / Tunnel 2 (UP): peer `43.201.181.136`

---

## Admin EC2 앱 배포 경로 (중요) — 2026-05-26 확정

> 현재 EC2: `i-0e9ff040046f8c1ca` (Windows)

| 경로 | 용도 |
|------|------|
| `C:/admin-platform/` | **실제 실행 경로** — `C:/start-admin.ps1`이 여기서 Flask 실행 |

**배포 방법**: 로컬 `admin-platform/deploy_to_ec2.ps1` 실행 — S3(`lifesync-raw/deploy/app_deploy.zip`) 경유 SSM으로 `C:/admin-platform/`에 직접 복사.

실행 환경 변수: `C:/start-admin.ps1` 에서 설정 (SECRET_KEY, ADMIN_USER, ADMIN_PASSWORD, ONPREM_BASE_URL 등)
로그: `C:/admin-platform/app.log`
Flask `debug=True` 모드 — app.py 변경 감지 시 자동 리로드. 프로세스 강제종료 시 수동 재시작 필요:
```powershell
Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Hidden -File C:/start-admin.ps1'
```

---

## 전체 현황 (빠른 확인)

### 온프레미스

| 항목 | 상태 |
|------|------|
| VM 4대 생성 및 네트워크 구성 | ✅ |
| Ansible 초기 배포 (mysql / tokenization / private_api) | ✅ |
| 크로스 VM 연결 및 서비스 검증 | ✅ |
| 초기 데이터 적재 (master_customer 100만 / identity_map 349만 / profile 100만) | ✅ |
| PII 암호화 (representative_name, birth_dt) | ✅ |
| Ansible Vault encrypt 실행 | ✅ |
| private_api DB 접속 환경변수 방식 전환 | ✅ |
| schema.sql 아키텍처 ERD 기준 전면 재작성 | ✅ |
| 실서버 스키마 마이그레이션 (컬럼 RENAME/DROP 적용) | ⏳ |

### Lambda

| 항목 | 상태 |
|------|------|
| gcp_result_ingest — GRADE_MAP / SQL / DB 연결 수정 | ✅ |
| customer_profile_sync — on-prem 연결 전환 / 컬럼명 수정 | ✅ |
| consent_filter — 신규 작성 (동의 고객 S3 추출) | ✅ |
| consent_filter — IaC 배포 (Lambda / SG / IAM / EventBridge) | ⏳ IaC 담당 |
| onprem_customer_query Lambda — 신규 작성 (Platform VPC 직접 VPN) | ✅ |
| onprem_customer_query Lambda — IaC 배포 (Platform VPC 서브넷 / SG / 환경변수) | ⏳ IaC 담당 |

### 플랫폼 / 어드민

| 항목 | 상태 |
|------|------|
| lifesync360-platform — Mock 코드 전체 제거 (mock_data.py 삭제, USE_MOCK 분기 제거) | ✅ |
| lifesync360-platform — Aurora/DynamoDB/Redis 연동 코드 | ✅ |
| lifesync360-platform — 아키텍처 기준 컬럼명 전면 통일 | ✅ |
| lifesync360-platform — 온프레미스 인증/동의 Lambda 연동 (_call_onprem) | ✅ |
| lifesync360-platform — 로컬 테스트 JWT 발급 환경 (make_token.py) | ✅ |
| lifesync360-platform — 포인트 기능 제거 (Aurora 테이블 없음, 화면 미노출) | ✅ |
| lifesync360-platform — Service-DB 스키마 기준 쿼리 정합성 검증 완료 | ✅ |
| lifesync360-platform — 온프레미스 시뮬레이터 EC2 실 데이터 테스트 완료 | ✅ |
| private_api — 아키텍처 기준 컬럼명/파라미터명 전면 통일 | ✅ |
| global_customer_id → global_id 전환 (schema.sql 2개 / lambda handler 2개) | ✅ |
| admin-platform — Mock 전체 기능 | ✅ |
| admin-platform — Mock 데이터 실제 스키마 기준 정합 (domain/consent_flag/clicked_flag 등) | ✅ |
| admin-platform — Aurora 쿼리 전면 수정 (캠페인/추천이력/퍼널/dashboard log) | ✅ |
| admin-platform — DynamoDB 기반 등급분포/유저목록 전환 | ✅ |
| admin-platform — 온프레미스 Lambda 헬퍼 (_call_onprem) 추가 | ✅ |
| admin-platform — user_detail URL global_id 기반 전환 | ✅ |
| admin-platform — AI 4개 섹션 + DataVPC 통합 상태 표시 수정 | ✅ |
| admin-platform — mem_used_percent (LifeSync/EC2) Network 페이지 VM 행 표시 | ✅ 2026-05-26 |
| admin-platform — 8개 VPC 카드 전체 표시 (pf/we/dt/gvm/mgmt/cn/gcp/on) | ✅ 2026-05-26 |
| admin-platform — GCP 카드 정상 표시 (BigQuery·Vertex AI·Cloud Run) | ✅ 2026-05-26 |
| admin-platform — 배포 경로 확정 및 deploy_to_ec2.ps1 생성 | ✅ 2026-05-26 |
| GitHub → CodeCommit 미러 CI | ✅ |
| taskdef.json / buildspec.yml / appspec.yaml (platform + admin) | ✅ |
| IaC / 코드 354 계정 기준 정리 (data.env, taskdef.json, app.py, start_ls360.sh) | ✅ |
| 732 계정 CloudFormation 스택 14개 전체 삭제 + 별도 추가 리소스 정리 | ✅ |
| /api/me name/grade 연동 (PII 복호화 + DynamoDB grade) | ⏳ |
| Aurora users_ref 동기화 테이블 설계 및 구축 (어드민 유저목록 이름/이메일 표시) | ⏳ |

### 클라우드 인프라

| 항목 | 상태 |
|------|------|
| CloudFormation 전체 YAML 작성 | ✅ |
| ECS Blue/Green (CODE_DEPLOY, Green TG, TestListener) | ✅ |
| CodeDeploy / CodePipeline IaC | ✅ |
| ECS 부트스트랩 (DesiredCount=0, public 이미지 직접 참조) | ✅ |
| Site-to-Site VPN Static 라우팅 전환 (BGP → Static) | ✅ |
| taskdef.json ACCOUNT_ID 치환 | ✅ |
| EC2 Control Node IaC (infra/compute/control-node.yaml) | ✅ |
| Deploy Server 구축 (Flask 9000, systemd, setup-ssh-keys.sh) | ✅ |
| DEPLOY_TOKEN Secrets Manager 분리 (/etc/deploy-server/env) | ✅ |
| hosts.yml ProxyJump 설정 (ls-db / ls-token → ls-api 경유) | ✅ |
| Secrets Manager 값 입력 (lifesync/* 전체) | ⏳ 배포 시점 |
| CloudFormation 스택 실제 배포 | ⏳ |

---

## 온프레미스 구축 Runbook

처음부터 다시 구성할 때 이 순서대로 실행.

---

### Step 1 — VirtualBox VM 생성 및 네트워크 구성

**Host-Only 어댑터 생성 (VirtualBox GUI)**
```
VirtualBox → 파일 → 호스트 네트워크 관리자 → 만들기
  IP: 192.168.56.1 / 서브넷마스크: 255.255.255.0
  DHCP 서버: 비활성화
```

**VM 4대 생성**

| VM 이름 | IP | 역할 | 메모리 | 디스크 |
|---------|-----|------|--------|--------|
| ls-vpngw | 192.168.56.10 | VPN Gateway (초기 구축 시 임시 Ansible Control Node 겸용) | 1GB | 20GB |
| ls-db    | 192.168.56.11 | MySQL | 2GB | 50GB |
| ls-token | 192.168.56.12 | Tokenization Service | 1GB | 20GB |
| ls-api   | 192.168.56.13 | Private API + Cron | 1GB | 20GB |

> **Note**: Ansible Control Node 역할은 Step 11에서 EC2로 이전. ls-vpngw는 VPN 터널 유지 전용으로 남음.

공통 설정: Ubuntu 22.04 / 어댑터1=NAT / 어댑터2=Host-Only(192.168.56.x 고정 IP)

> **ls-api 전용 추가 설정**: VPN 터널용 브리지 어댑터 필요.
> `VirtualBox → ls-api VM → 설정 → 네트워크 → 어댑터3 → 브리지 어댑터 → 실제 NIC 선택 (Wi-Fi 또는 이더넷)`

---

### Step 2 — VM 공통 초기 설정 (각 VM에서)

```bash
# ansible 유저 생성
sudo useradd -m -s /bin/bash ansible
sudo usermod -aG sudo ansible
echo "ansible ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/ansible

# Host-Only 어댑터 고정 IP 설정 (ls-db 예시, IP만 VM마다 변경)
sudo tee /etc/netplan/01-netcfg.yaml << 'EOF'
network:
  version: 2
  ethernets:
    enp0s8:
      dhcp4: no
      addresses: [192.168.56.11/24]
EOF
sudo netplan apply

# 설정 확인
ip addr show enp0s8
# → 192.168.56.x/24 확인
```

VirtualBox 공유 폴더(Step 7) 사용을 위한 Guest Additions 설치 (ls-db에서):
```bash
sudo apt install -y virtualbox-guest-utils
sudo usermod -aG vboxsf ansible
sudo reboot
```

---

### Step 3 — SSH 키 생성 및 배포

> 개발 PC(VirtualBox 호스트) 또는 ls-vpngw에서 실행. 3개 VM에 직접 접근 가능한 환경 기준.
> EC2 Control Node에서 배포할 경우 → Step 12의 `setup-ssh-keys.sh` 사용.

```bash
# SSH 키 생성 (최초 1회, ~/.ssh 없으면 먼저 생성)
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keygen -t rsa -b 4096 -f ~/.ssh/lifesync360-onprem.pem -N ""

# 각 VM에 공개키 등록 (3개 VM 직접 접근 가능한 환경에서)
ssh-copy-id -i ~/.ssh/lifesync360-onprem.pem.pub ansible@192.168.56.11
ssh-copy-id -i ~/.ssh/lifesync360-onprem.pem.pub ansible@192.168.56.12
ssh-copy-id -i ~/.ssh/lifesync360-onprem.pem.pub ansible@192.168.56.13

# 확인
ssh -i ~/.ssh/lifesync360-onprem.pem ansible@192.168.56.13 "echo ok"
```

---

### Step 4 — Ansible 초기 설정 및 연결 확인 (초기 구축 전용)

> **이 단계는 초기 온프레미스 구축 시 ls-vpngw를 임시 Control Node로 쓸 때만 필요.**
> EC2 Control Node가 준비되면 Step 11~12로 대체됨.

```bash
ssh ansible@192.168.56.10

# Ansible 설치
sudo apt update && sudo apt install -y ansible python3-pip

# 레포 클론
git clone <repo_url> /opt/ansible/onprem-prod-repo
cd /opt/ansible/onprem-prod-repo

# SSH 키 복사 (개발 PC → ls-vpngw는 공유 폴더 또는 scp 이용)
mkdir -p ~/.ssh && chmod 700 ~/.ssh
cp /mnt/downloads/lifesync360-onprem.pem ~/.ssh/
chmod 600 ~/.ssh/lifesync360-onprem.pem

# 연결 확인 — 3개 VM 모두 pong 이면 정상
ansible all -m ping -i ansible/inventory/hosts.yml
# ls-vpngw는 3개 VM 직접 접근 가능하므로 ProxyJump 불필요
```

---

### Step 5 — Ansible 첫 배포

> Vault 암호화 전이면 `--ask-vault-pass` 없이 실행. Step 9 이후엔 vault-pass 필요.

```bash
# ls-vpngw 또는 개발 PC에서 (초기 구축 시)
cd /opt/ansible/onprem-prod-repo

# Vault 암호화 전
ansible-playbook ansible/site.yml -i ansible/inventory/hosts.yml

# Vault 암호화 후 (Step 9 완료 시)
ansible-playbook ansible/site.yml -i ansible/inventory/hosts.yml \
  --vault-password-file ~/.vault_pass
# 또는 패스워드 직접 입력
ansible-playbook ansible/site.yml -i ansible/inventory/hosts.yml --ask-vault-pass
```

배포 후 서비스 상태 확인:
```bash
ssh -i ~/.ssh/lifesync360-onprem.pem ansible@192.168.56.11 "sudo systemctl status mysql"
ssh -i ~/.ssh/lifesync360-onprem.pem ansible@192.168.56.12 "sudo systemctl status tokenization"
ssh -i ~/.ssh/lifesync360-onprem.pem ansible@192.168.56.13 "sudo systemctl status private-api nginx"
```

---

### Step 5-1 — AWS Site-to-Site VPN 설정 (ls-api ↔ AWS TGW)

> 상세 내용 및 트러블슈팅은 `aws-vpn-setup.md` 참고.

**① ls-api에 StrongSwan 설치**
```bash
ssh ansible@192.168.56.13
sudo apt update && sudo apt install -y strongswan strongswan-pki libcharon-extra-plugins
```

**② 브리지 어댑터 IP 및 공인 IP 확인**
```bash
# 브리지 어댑터 IP (enp0s9, left= 값)
ip addr show enp0s9 | grep 'inet '
# → 예: 172.16.1.73

# 공유기 공인 IP (leftid= 값, AWS Customer Gateway에 등록할 IP)
curl ifconfig.me
```

**③ AWS 콘솔 — Customer Gateway 및 VPN Connection 생성**
```
VPC → Customer Gateways → Create
  IP Address: ②의 공인 IP
  BGP ASN: 65000

VPC → Site-to-Site VPN → Create
  Customer Gateway: 위에서 생성한 것
  Transit Gateway 선택
  Routing: Static
  Static IP Prefixes: <브리지 어댑터 IP>/32  (예: 172.16.1.73/32)

생성 후 → Download Configuration → Vendor: Generic
  → 파일에서 터널 IP(Outside IP)와 PSK 값 확인
```

**④ /etc/ipsec.conf 설정**
```bash
sudo tee /etc/ipsec.conf << 'EOF'
config setup
    charondebug="ike 2, knl 2, cfg 2"

conn aws-vpn
    authby=secret
    left=<브리지 어댑터 IP>
    leftid=<공유기 공인 IP>
    leftsubnet=<브리지 어댑터 IP>/32
    right=<AWS VPN 터널 IP>
    rightsubnet=<Management VPC CIDR>
    ike=aes256-sha256-modp2048
    esp=aes256-sha256
    keyingtries=%forever
    keyexchange=ikev2
    forceencaps=yes
    auto=start
EOF
```

**⑤ /etc/ipsec.secrets 설정**
```bash
sudo tee /etc/ipsec.secrets << 'EOF'
<공유기 공인 IP> <AWS VPN 터널 IP> : PSK "<다운로드한 PSK값>"
EOF
sudo chmod 600 /etc/ipsec.secrets
```

**⑥ IP 포워딩 및 StrongSwan 시작**
```bash
echo "net.ipv4.ip_forward = 1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

sudo systemctl enable strongswan-starter
sudo systemctl restart strongswan-starter
```

**⑦ 연결 확인**
```bash
sudo ipsec status
# → aws-vpn[1]: ESTABLISHED ... 확인
# → aws-vpn{1}: INSTALLED, TUNNEL 확인

# EC2 Control Node까지 통신 확인 (VPN 연결 후)
ping <EC2 Private IP>
```

---

### Step 6 — 서비스 검증

```bash
# ls-api health (Nginx 경유 80포트)
curl http://192.168.56.13/health
# → {"status":"ok"}

# ls-token health
curl http://192.168.56.12:8000/health
# → {"status":"ok"}

# tokenize 정상 호출
curl -X POST http://192.168.56.12:8000/tokenize \
  -H "Content-Type: application/json" \
  -d '{"field": "phone_number", "value": "01012345678"}'
# → {"token_id": "xxxx-xxxx-xxxx-xxxx"}

# dedup — 같은 값 두 번 호출 → token_id 동일해야 함
curl -X POST http://192.168.56.12:8000/tokenize \
  -H "Content-Type: application/json" \
  -d '{"field": "phone_number", "value": "01099999999"}'
# (두 번 실행 후 token_id 비교)

# 허용되지 않은 필드 → 400
curl -X POST http://192.168.56.12:8000/tokenize \
  -H "Content-Type: application/json" \
  -d '{"field": "address", "value": "서울시 강남구"}'
# → HTTP 400 {"detail":"Field 'address' not in allowed fields"}

# 없는 token_id detokenize → 404
curl http://192.168.56.12:8000/detokenize/00000000-0000-0000-0000-000000000000
# → HTTP 404

# 크로스 VM MySQL 연결 (ls-db)
ssh ansible@192.168.56.11
mysql -u lifesync -p lifesync_onprem -e "SHOW TABLES;"
```

---

### Step 7 — 초기 데이터 적재

**파일 전송 — VirtualBox 공유 폴더**
```
VirtualBox GUI → ls-db VM → 설정 → 공유 폴더 → 추가
  호스트 경로: C:\Users\campus3S026\Downloads
  폴더 이름: downloads
  자동 마운트: 체크 / 영구: 체크
→ VM 재기동
```

**ls-db VM에서 마운트 및 파일 복사**
```bash
ssh ansible@192.168.56.11
sudo mkdir -p /mnt/downloads
sudo mount -t vboxsf downloads /mnt/downloads
ls /mnt/downloads/*.csv

# MySQL secure_file_priv 경로로 복사
sudo cp /mnt/downloads/customer_master.csv      /var/lib/mysql-files/
sudo cp /mnt/downloads/customer_identity_map.csv /var/lib/mysql-files/
sudo cp /mnt/downloads/customer_profile.csv      /var/lib/mysql-files/
```

**스키마 적용 (데이터 적재 전 필수)**
```bash
mysql -u root -p lifesync_onprem < /mnt/downloads/onprem_schema.sql
```

**데이터 적재**
```bash
mysql -u root -p lifesync_onprem
```

```sql
USE lifesync_onprem;

-- ① master_customer (100만건)
LOAD DATA INFILE '/var/lib/mysql-files/customer_master.csv'
INTO TABLE master_customer
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(global_id, representative_name, birth_dt, gender, nationality);

-- ② customer_identity_map (349만건)
LOAD DATA INFILE '/var/lib/mysql-files/customer_identity_map.csv'
INTO TABLE customer_identity_map
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(global_id, company_id, affiliate_customer_id);

-- ③ customer_360_profile (100만건 — global_id만 적재, 나머지 38컬럼 @변수로 버림)
LOAD DATA INFILE '/var/lib/mysql-files/customer_profile.csv'
INTO TABLE customer_360_profile
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(
  @global_id,
  @고객유형, @나이, @성별, @소득구간, @건강상태, @신용등급, @라이프스타일, @시나리오,
  @가입계열사수, @은행가입, @카드가입, @보험가입, @인터넷보험가입, @병원가입,
  @헬스케어가입, @증권가입, @웨어러블가입,
  @은행ID, @카드ID, @보험ID, @인터넷보험ID, @병원ID, @헬스케어ID, @증권ID, @웨어러블ID,
  @은행동의, @카드동의, @보험동의, @인터넷보험동의, @병원동의, @헬스케어동의, @증권동의, @웨어러블동의,
  @혈당, @지질, @간기능, @신장기능
)
SET global_id = @global_id, grade = 'BASIC';
```

**적재 결과 확인**
```sql
SELECT COUNT(*) FROM master_customer;         -- 1,000,000
SELECT COUNT(*) FROM customer_identity_map;   -- 3,498,623
SELECT COUNT(*) FROM customer_360_profile;    -- 1,000,000
SELECT * FROM master_customer LIMIT 3;
SELECT * FROM customer_identity_map WHERE global_id = 'G000000001';
```

---

### Step 8 — PII 암호화

> 상세 내용은 `pii-encryption-guide.md` 참고. 핵심 실행 순서만 아래 정리.

**① 암호화 키 생성 (ls-vpngw에서)**
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 출력된 키를 복사해둘 것 — 잃어버리면 복호화 불가
```

**② Vault 파일에 키 등록**
```bash
cd /opt/ansible/onprem-prod-repo
cat > ansible/inventory/group_vars/private_api/vault.yml << 'EOF'
vault_pii_aes_key: "<①에서 생성한 키>"
EOF
```

**③ ls-db 컬럼 타입 변경**
```bash
ssh ansible@192.168.56.11
mysql -u root -p lifesync_onprem
```
```sql
ALTER TABLE master_customer
  MODIFY representative_name VARCHAR(300),
  MODIFY birth_dt VARCHAR(100);
EXIT;
```

**④ 마이그레이션 스크립트 실행 (ls-vpngw에서, 약 5~10분)**
```bash
pip3 install cryptography pymysql --break-system-packages

export PII_AES_KEY=<①에서 생성한 키>
export DB_HOST=192.168.56.11
export DB_USER=lifesync
export DB_PASS=<MySQL lifesync 패스워드>
python3 /opt/ansible/onprem-prod-repo/db/migrate_pii_encrypt.py
```

**⑤ 암호화 확인**
```bash
ssh ansible@192.168.56.11
mysql -u root -p lifesync_onprem -e \
  "SELECT global_id, representative_name FROM master_customer LIMIT 3;"
# representative_name 값이 'gAAAAAB...' 형태면 정상
```

**⑥ ls-api 재배포 및 복호화 검증**
```bash
# ls-vpngw에서
cd /opt/ansible/onprem-prod-repo
ansible-playbook ansible/site.yml -i ansible/inventory/hosts.yml \
  --limit ls-api --ask-vault-pass

# 복호화 확인 — 한글 이름이 정상 출력되면 성공
curl http://192.168.56.13/internal/customer/G000000001
```

---

### Step 9 — Ansible Vault 암호화

```bash
# ls-vpngw에서
# vault 패스워드 파일 생성 (Ansible 실행 시 자동 참조)
echo "<vault 패스워드>" > ~/.vault_pass
chmod 600 ~/.vault_pass

cd /opt/ansible/onprem-prod-repo

# tokenization vault
ansible-vault encrypt ansible/inventory/group_vars/tokenization/vault.yml
git add ansible/inventory/group_vars/tokenization/vault.yml
git commit -m "feat(vault): tokenization vault 암호화 적용"

# private_api vault (Step 8 완료 후)
ansible-vault encrypt ansible/inventory/group_vars/private_api/vault.yml
git add ansible/inventory/group_vars/private_api/
git commit -m "feat(vault): private_api vault 암호화 적용"

git push
```

이후 Ansible 실행 시:
```bash
ansible-playbook ansible/site.yml -i ansible/inventory/hosts.yml --ask-vault-pass
```

---

### Step 10 — Secrets Manager 등록

CloudFormation 스택 배포 전에 아래 시크릿을 모두 등록해야 함.
Aurora/Redis 엔드포인트는 스택 배포 후 확정되므로 플레이스홀더로 먼저 생성 후 업데이트.

```bash
# ── 플랫폼 / 어드민 ──────────────────────────────
aws secretsmanager create-secret \
  --name lifesync/aurora \
  --secret-string '{"host":"<Aurora 엔드포인트>","user":"<DB 유저>","password":"<DB 패스워드>"}' \
  --region ap-northeast-2

aws secretsmanager create-secret \
  --name lifesync/jwt \
  --secret-string '{"secret":"<JWT 서명 키>"}' \
  --region ap-northeast-2

aws secretsmanager create-secret \
  --name lifesync/redis \
  --secret-string '{"host":"<ElastiCache 엔드포인트>"}' \
  --region ap-northeast-2

aws secretsmanager create-secret \
  --name lifesync/admin \
  --secret-string '{"username":"<관리자 계정>","password":"<관리자 패스워드>","secret_key":"<Flask 세션 키>"}' \
  --region ap-northeast-2

# ── EC2 Control Node (아래 3개는 CloudFormation UserData가 참조 — 배포 전 필수) ──
aws secretsmanager create-secret \
  --name lifesync/ansible-vault \
  --secret-string '{"password":"<Ansible Vault 패스워드>"}' \
  --region ap-northeast-2

aws secretsmanager create-secret \
  --name lifesync/ansible-vm \
  --secret-string '{"password":"<온프레미스 ansible 계정 패스워드>"}' \
  --region ap-northeast-2

aws secretsmanager create-secret \
  --name lifesync/deploy-token \
  --secret-string '{"token":"<X-Deploy-Token 값>"}' \
  --region ap-northeast-2
```

Aurora/Redis 엔드포인트 확정 후 값 업데이트:
```bash
aws secretsmanager update-secret \
  --secret-id lifesync/aurora \
  --secret-string '{"host":"<확정된 Aurora 엔드포인트>","user":"<DB 유저>","password":"<DB 패스워드>"}' \
  --region ap-northeast-2

aws secretsmanager update-secret \
  --secret-id lifesync/redis \
  --secret-string '{"host":"<확정된 ElastiCache 엔드포인트>"}' \
  --region ap-northeast-2
```

---

### Step 11 — EC2 Control Node CloudFormation 배포 (14a → 14b → 14c)

> IAM(14a) → EC2(14b) → SSM Association(14c) 순서로 배포. 14b 출력을 14c에 넘겨야 하므로 반드시 순서 지킬 것.

```bash
# ── 14a: IAM 롤 + 인스턴스 프로파일 ──────────────────────────────
aws cloudformation deploy \
  --template-file 14a-ansible-iam.yaml \
  --stack-name lifesync-dev-ansible-iam \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-2

# 14a 출력 확인 (14b 파라미터에 사용)
PROFILE_NAME=$(aws cloudformation describe-stacks \
  --stack-name lifesync-dev-ansible-iam \
  --query 'Stacks[0].Outputs[?OutputKey==`AnsibleControlNodeInstanceProfileName`].OutputValue' \
  --output text --region ap-northeast-2)
echo "Profile: $PROFILE_NAME"

# ── 14b: EC2 + UserData ───────────────────────────────────────────
# AmiId: EC2 콘솔에서 AL2023 최신 AMI ID 확인
# ManagementSubnetId: Management VPC private subnet ID
# ManagementSgId: Management VPC SG ID (SSM 아웃바운드 443 허용 필요)
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

# 14b 출력 확인 (14c 파라미터에 사용)
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name lifesync-dev-ansible-ec2 \
  --query 'Stacks[0].Outputs[?OutputKey==`AnsibleControlInstanceId`].OutputValue' \
  --output text --region ap-northeast-2)
echo "Instance ID: $INSTANCE_ID"

# ── 14c: SSM Association (공개키 SSM 등록 + 온프레미스 푸시) ──────
aws cloudformation deploy \
  --template-file 14c-ansible-key-publish.yaml \
  --stack-name lifesync-dev-ansible-key-publish \
  --parameter-overrides \
    AnsibleControlInstanceId=$INSTANCE_ID \
  --region ap-northeast-2
```

---

### Step 12 — Control Node 초기화 확인 및 연결 테스트

UserData 완료까지 약 5~15분 소요 (ansible-core venv 설치 포함). SSM Session Manager로 접속해서 확인.

```bash
# SSM으로 접속 (SSH 키 없이)
aws ssm start-session --target <AnsibleControlInstanceId> --region ap-northeast-2

# ── EC2 내부에서 확인 ──────────────────────────────────────────
# UserData 로그 (14b 완료 시 마지막 줄에 "14b 완료:" 포함됨)
sudo tail -100 /var/log/ansible-bootstrap.log

# SSH 키 생성 확인
ls -la /home/ansible/.ssh/
# → id_rsa (600), id_rsa.pub (644) 존재해야 함

# Ansible venv 확인
/opt/ansible-venv/bin/ansible --version

# Ansible 연결 확인 (VPN 연결 상태에서만 성공)
ansible all -m ping \
  -i /opt/ansible/onprem-prod-repo/ansible/inventory/hosts.yml \
  --vault-password-file ~/.vault_pass
# → ls-api: pong, ls-db: pong, ls-token: pong 확인
```

14c SSM Association 결과 확인 (로컬 PC에서):
```bash
# 공개키가 SSM Parameter Store에 올라갔는지 확인
aws ssm get-parameter \
  --name /lifesync/dev/ansible/public-key \
  --region ap-northeast-2 \
  --query Parameter.Value --output text
# → ssh-rsa AAAA... 형태면 정상
```

SSH 키 미생성 시 수동 복구 (SSM 세션 내부에서):
```bash
sudo install -d -m 0700 -o ansible -g ansible /home/ansible/.ssh
sudo -u ansible ssh-keygen -t rsa -b 4096 -N "" -f /home/ansible/.ssh/id_rsa -q
sudo chown -R ansible:ansible /home/ansible/.ssh
```

---

### Step 13 — vars.yml control_node_url 업데이트 및 재배포

EC2 Control Node Private IP를 확인 후 레포 업데이트.

```yaml
# onprem-prod-repo/ansible/inventory/group_vars/private_api/vars.yml
deploy_token: "lifesync-deploy-token-2026"
control_node_url: "http://<EC2-Private-IP>:9000"   # ← 실제 IP로 변경
```

```bash
git add ansible/inventory/group_vars/private_api/vars.yml
git commit -m "chore: control_node_url EC2 Private IP 반영"
git push

# EC2 Control Node에서 레포 최신화 후 ls-api 재배포
cd /opt/ansible/onprem-prod-repo
git pull
ansible-playbook ansible/site.yml \
  -i ansible/inventory/hosts.yml \
  --vault-password-file ~/.vault_pass \
  --limit ls-api
```

---

### Step 14 — CI/CD 트리거 전체 흐름 테스트

ls-api VM에서 배포 트리거 → EC2 Control Node → ansible-playbook 실행까지 확인.

```bash
# ls-api VM에서
TOKEN=$(sudo grep DEPLOY_TOKEN /etc/systemd/system/private-api.service | cut -d= -f3-)

curl -X POST http://localhost:8000/internal/deploy \
  -H "X-Deploy-Token: ${TOKEN}"
# → {"status": "triggered"}

# EC2 Control Node에서 로그 확인
tail -f /var/log/ansible-deploy.log
# ansible-playbook 실행 로그 확인
```

---

## 매일 아침 운영 절차 (IaC 재배포 후)

매일 9AM IaC가 VPN Connection을 재생성하므로 AWS 터널 IP가 바뀜.
VirtualBox와 VM을 먼저 켠 후 아래 순서로 진행.

### 1단계 — VPN 터널 재연결 (로컬 PC에서)

```bash
# AWS CLI 인증 확인
aws sts get-caller-identity

# 터널 IP 자동 갱신 및 StrongSwan 재시작
# PSK를 Secrets Manager에 등록한 경우 (lifesync/vpn-psk)
bash scripts/update-vpn-tunnel.sh

# PSK를 직접 지정할 경우 (SM 미등록 시)
VPN_PSK="<PSK값>" bash scripts/update-vpn-tunnel.sh

# VPN Name 태그 모를 경우 Connection ID 직접 지정
VPN_CONNECTION_ID=vpn-xxxxxxxxx bash scripts/update-vpn-tunnel.sh
```

출력에 `ESTABLISHED` 확인되면 VPN 연결 완료.
연결 실패 시 → `local-test-troubleshooting.md` "IaC 재배포 후 VPN 터널 끊김" 항목 참고.

### 2단계 — EC2 Control Node 접속 (Control Node 재생성 시 InstanceId 갱신)

```bash
# Control Node 재생성 시 새 InstanceId 조회 (EC2 Name 태그 기준)
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=lifesync-dev-management-ec2-ansible" \
            "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text --region ap-northeast-2)

# 또는 CF Output에서 조회
# INSTANCE_ID=$(aws cloudformation describe-stacks \
#   --stack-name lifesync-dev-ansible-ec2 \
#   --query 'Stacks[0].Outputs[?OutputKey==`AnsibleControlInstanceId`].OutputValue' \
#   --output text --region ap-northeast-2)

# SSM으로 EC2 접속
aws ssm start-session --target $INSTANCE_ID --region ap-northeast-2

# 온프레미스 VM 연결 확인
ansible all -m ping \
  -i /opt/ansible/onprem-prod-repo/ansible/inventory/hosts.yml \
  --vault-password-file ~/.vault_pass
# ls-api / ls-db / ls-token 모두 pong 이어야 함
```

---

## 플랫폼 / 어드민 개발 이력 (참고)

### 2026-05-22

**코드 클린업 + VPN 안정화**

| 구분 | 변경 |
|------|------|
| mock 코드 전체 제거 | `mock_data.py` 삭제. `lifesync360-platform/app.py` 에서 모든 `USE_MOCK` 분기, `_recommendations_mock()`, `_mock_user` fallback 제거. `admin-platform/app.py` 에서 사용되지 않는 `import random` / `import threading` / `from collections import deque` 제거 |
| 죽은 코드 제거 (platform app.py) | `import hashlib` (mock 비밀번호 검증용), `PROFILE_SYNC_LAMBDA` 환경변수 (`_resolve_global_id()` 삭제로 고아), `import uuid`, `COMPANIES` 리스트, `_resolve_global_id()` 함수 |
| 버그 수정 | `api_consent()` NoneGuard — `request.get_json()` None 시 AttributeError 방지. `api_product_apply()` DB 에러 메시지 노출 → `app.logger.exception` + 제네릭 메시지로 교체 |
| Lambda 클린업 | `analytics_aggregator/handler.py` — 미사용 `date` import 제거 |
| VPN SA lifetime 설정 (ls-api) | `ikelifetime=7800s` / `lifetime=3300s` / `margintime=300s` 추가. 간헐적 끊김의 근본 원인(SA 만료 시점 재협상 없음) 해결. StrongSwan 재시작 후 ESTABLISHED 확인 |
| 문서 중복 제거 | 루트 `NEW_TABLES_GUIDE.md` 삭제 (Service-DB/ 하위 파일과 100% 동일). `docs/iac-ecs-taskdef-spec.md` 에서 platform 태스크 정의의 `USE_MOCK` / `PROFILE_SYNC_LAMBDA` env 및 `customer-profile-sync` Lambda IAM 제거 |

### 2026-05-20

**admin 자동 갱신 도입 — 화면 깜빡임 없는 JS 폴링**

| 변경 | 내용 |
|---|---|
| `static/js/auto-refresh.js` 신설 | `AutoRefresh.register({interval, fetches[]})` — `Promise.allSettled` + `document.hidden` 감지 + inflight 가드 |
| `base.html` | `auto-refresh.js` defer 로드 (모든 페이지 공통) |
| `dashboard.html` | KPI 9 + Cloud 3 + S3 5 + uploads 표 → 60s 폴링 (`/api/dashboard/summary` · `/api/dashboard/cloud3` · `/api/s3/status` · `/api/dashboard/uploads`) |
| `ai.html` | 상단 4 KPI → 300s 폴링 (`/api/ai/kpi4`) — 차트는 SVG 그대로 |
| `admin-platform/app.py` | 신설 라우트 — `/api/dashboard/cloud3` · `/api/dashboard/uploads` · `/api/ai/kpi4` |
| `docs/admin-data-flow.md` §6 | 6 소절 → 표 중심 6 소절로 압축 (한눈에 보이게) + 자동 갱신 구현 반영 |

**깜빡임 방지 핵심**

- `textContent !== next` 비교 후 다를 때만 setText → DOM mutation 0
- 페이지 백그라운드 (`document.hidden=true`) 일 때 폴링 즉시 중지
- 응답 에러는 `Promise.allSettled` 로 묶어 무시 — 사용자 화면 노출 X
- 첫 화면은 SSR 그대로 (자동 갱신은 로드 후 적용)

→ users.html 은 사용자 검색 입력 페이지라 자동 갱신 제외.
→ SVG 차트 5종은 Jinja2 좌표 계산이라 자동 갱신 대상 X (Phase 3 에서 Chart.js 도입 시 처리).

---

**ops Wearable 재설계 — SSE 3s push + AHA/WHO 의학 기준 분류**

기존 6 KPI (평균 심박/혈압/산소 등) 는 운영자가 액션 못 함 → 이상/이상 가능성 대상자만 추려서 노출로 재설계.

| 변경 | 내용 |
|---|---|
| `admin-platform/wearable_engine.py` 신설 | 메모리 엔진 — `load_initial / tick / classify / snapshot / start_loop`. 운영 단계 Kinesis consumer + DynamoDB 로 교체 포인트 명시 |
| `admin-platform/mock_wearable_batch.json` 신설 | Kinesis `wearable_batch_v1` 실 샘플 (100 records, ~31KB) |
| `admin-platform/app.py` | wearable_engine 부팅 + 3s tick 백그라운드 thread + `/api/ops/wearable` (폴백) + `/stream/wearable` (SSE) + 기존 `/api/ops/wearable6` 제거 + ops() 핸들러 변경 + `threaded=True` |
| `admin-platform/templates/ops.html` | 평균 KPI 6 제거 → KPI 5 (활성/송신율/RED/YELLOW/디바이스) + 표 3개 (건강 RED · 건강 YELLOW · 디바이스 배터리). SSE 구독 — 깜빡임 0 |
| `static/js/auto-refresh.js` | `AutoRefresh.subscribe(url, handler)` SSE 헬퍼 추가 — visibilitychange 시 자동 disconnect/reconnect |

**의학 기준 (`wearable_engine.classify`)**

| 지표 | 정상 | YELLOW | RED | 근거 |
|---|---|---|---|---|
| heart_rate | 60-100 | 50-59 / 101-119 | <50 또는 ≥120 | AHA + ACC/AHA/HRS |
| spo2_pct | ≥95% | 90-94% | <90% | WHO 임상 알람 |
| stress_score | 0-50 | 51-75 | ≥76 | Garmin Firstbeat |
| battery_pct | ≥30% | 15-29% | <15% | Fitrockr (별도 디바이스 알람) |

**PII 마스킹** — admin 도 풀네임/풀 ID 안 보임
- global_id → `G00023***` (앞 5자리 + 마스킹)
- 이름 → `김**` (성씨는 global_id 끝자리로 결정적 매핑, 10개 성씨 round-robin)

**운영 단계 교체 포인트** (`wearable_engine.py` docstring 명시)
- `load_initial(json)` → Kinesis Stream consumer
- `_state['latest']` 메모리 dict → DynamoDB `wearable_latest{global_id}` get_item
- `_state['red/yellow/device']` deque → DynamoDB `anomaly_event` query 최근 N
- `tick()` noise → 실 Kinesis 이벤트 수신 핸들러
- `classify()` 는 그대로 사용 가능 (또는 Vertex AI risk_score 로 교체)

---

**admin USE_MOCK=false 실 AWS 연동 — 354 계정 (354493396671)**

`USE_MOCK=false` + envar 세팅으로 boto3 호출 활성화. 작동 가능 영역만 실 데이터, 나머지 mock fallback.

| 항목 | 변경 |
|---|---|
| dashboard `dashboard()` 핸들러 | USE_MOCK 분기 추가 — 첫 SSR 부터 `_stub_aurora_summary` / `_cloud3_from_aws` / `_s3_status_cards` / `_uploads_from_s3` 결과 사용 (다른 페이지 갔다 와도 mock 안 보임) |
| ai `ai()` 핸들러 | `kpi4 = MOCKUP_AI_KPI4 if USE_MOCK else _ai_kpi4_from_aws()` |
| `auto-refresh.js` `register` | 시작 즉시 1회 tick → interval 첫 tick 까지 60초 대기 X |
| `/api/dashboard/cloud3` | USE_MOCK 분기 + `_cloud3_from_aws` — AWS 7 영역 (RDS/DDB/EC/ECS/ALB/S3/Lambda) + EC2 Tag Project=lifesync |
| `/api/dashboard/uploads` | USE_MOCK 분기 + `_uploads_from_s3(limit=5)` — 도메인 8 × `Prefix={d}/dt={today}/` MaxKeys 10 (KST 기준 오늘) |
| `/api/ai/kpi4` | USE_MOCK 분기 + Lambda CloudWatch 1h invocations (recommendation / ingest) |
| `_ping_s3_ingestion` | lifesync-* 다중 버킷 합산 — CloudWatch `NumberOfObjects` / `BucketSizeBytes` metric + 오늘 dt KeyCount (KST 기준) |
| KST 시간 표시 | uploads / S3 last_upload / Wearable SSE event_time 모두 `Asia/Seoul +09:00` (UTC `astimezone`) |
| ops Wearable 디바이스 배터리 제거 | KPI 5→4 (활성/송신율/RED/YELLOW), 표 3→2. `wearable_engine.classify` 의 device 반환 + `_state['device']` deque 제거 |
| 갱신 시각 표시 | 각 섹션 헤더 우측에 `갱신: HH:MM:SS` (`AutoRefresh.stampNow`). dashboard 4영역 + ai 1영역 + ops Wearable 3영역 |
| Flask reloader 끔 | `debug=False, use_reloader=False` — SSE 연결 끊김 + 코드 수정 시 admin 재기동 안정 |

**필요 envar** (USE_MOCK=false 시):
```
ADMIN_PASSWORD=admin123
USE_MOCK=false
AWS_REGION=ap-northeast-2
LIFESYNC_RAW_S3_BUCKET=lifesync-raw
DYNAMO_TABLE=lifesync_customer_result
GLUE_JOB_PHYSICAL_NAME=lifesync-etl
ONPREM_QUERY_LAMBDA=lifesync-onprem-customer-query
```

**작동 안 하는 영역 (Aurora private + DDB key 등 — 의도적 mock fallback)**
- KPI 9 (`/api/dashboard/summary`) — Aurora 자격증명 + private subnet → mock baseline 유지
- C360 점수 / 추천이력 — DDB HASH+RANGE 키 / Aurora SQL → API 500 → JS Promise.allSettled 무시
- ai 차트 (7일 추이 / 도넛 등) — Aurora SQL 의존

→ Aurora 자격증명: SSM Parameter Store 에는 없음 (`/lifesync/*` 다 확인). 평문 `Aws_iac/params/security.env` 의 `ChangeMe123!`. **다만 Aurora 가 `PubliclyAccessible=False` + SG inbound 가 특정 SG 만 허용 → 로컬 PC 에서 직접 connect 불가**. Phase 3 에서 SSM port forwarding / Bastion EC2 도입 시 활용.

다음 라운드 후보:
- C360 wearable 박스 신설
- KPI #9 `Redis Cache 수` → CloudWatch `AWS/ElastiCache CurrItems` metric
- ops VPC 카드 → 실 VPC CIDR + EC2 PrivateIp 표시
- Cloud3 의 EC2 표시 0개 이슈 — EC2 Tag 키 확인 후 정정 (`aws:cloudformation:stack-name` 등)

### 2026-05-19

**lifesync360-platform 정리 (대규모 surgical refactor)**

| 구분 | 변경 |
|---|---|
| 회원가입 흐름 제거 | `/api/register` + `/register` + `register.html` + `_resolve_global_id` + `PROFILE_SYNC_LAMBDA` 환경변수 |
| JWT 발급 시크릿 SSM 화 | SSM `/lifesync360/jwt-secret` (HS256 대칭키) 만 사용 — secret 으로 platform 이 토큰 직접 발급/검증. `/lifesync360/jwt-token` 별도 안 만듦 (2026-05-20 정정) |
| 죽은 API 제거 (Group 1) ✅ 완료 (2026-05-20, commit a6cfd58) | `/api/upgrade-actions` + `/api/my-products` + `MOCK_MY_PRODUCTS` + `MOCK_CONSENTED_KEYS` + `upgrade_actions_engine.py` 통째 |
| 캠페인 복원 | `/api/campaigns` + `MOCK_CAMPAIGNS_BY_GRADE` 다시 살림 (홈 탭 캠페인 배너 표시 위해) |
| 추천 top10 제한 | `_fetch_products` LIMIT 20 → 10, `_recommendations_mock` flat[:20] → flat[:10] |
| ETL 책임 분리 | `_enrich_and_record` 가중치 계산 (`recommendation_score / grade_bonus / nba_bonus / cross_bonus`) 제거 — 정렬은 Aurora `priority_rank` 단일 출처 |
| NBA 고객 노출 제거 | `/api/dashboard` + `/api/recommendations` 응답에서 `next_best_action` 제거, reason 의 "NBA \"...\" 매칭" / "cross_sell 보강" / "VIP 후보" 내부 용어 제거. 정렬은 내부에서만 사용 |
| 홈 탭 재구성 | 추천 미리보기 (`home-rec-section`) 제거 → 등급별 캠페인 배너 영역 신설 |
| 죽은 코드 청소 | `switchToRecommendTab()` JS 함수, `.home-rec-*` CSS 4개 클래스, `MOCKUP_*` 의 `next_best_action` 필드 등 |

→ 결과: 17 API → 10 API + 6 페이지 (유령 API 0건, 모든 라우트가 화면 또는 ALB 연결).

**설계서 V3 + spec 갱신**

| 산출물 | 내용 |
|---|---|
| `lifesync360-platform 설계서 V3.xlsx` | admin V4 동일 스타일 (5컬럼 + 섹션 헤더 D9E1F2 + 컬럼 헤더 FFF2CC + 맑은 고딕 12pt). 6 시트 (인증 / 홈·점수·캠페인 / 추천·상품 / 이벤트·신청 / 동의·설정 / 인프라). 각 시트 하단에 admin V4 형식 API 호출 섹션 추가 |
| `docs/build_platform_xlsx.py` | xlsx 빌드 스크립트 — SHEETS / API_SECTIONS dict 만 수정하면 재빌드. 행 높이 자동 계산 (한글 가중치 2, ASCII 1, 컬럼 너비 ×1.7) |
| `docs/platform-api-spec.md` | V2 → V3 (655 → 558 lines). 매트릭스 / JWT 모델 (Parameter Store) / 6 도메인 상세 / 변경 이력 / 시연 시나리오 |

**참조**: `docs/admin-data-flow.md §7` (실시간성 + 차트 구현 분석)

### 2026-04 초중순
- LifeSync360 RFP v7, 아키텍처 설계 v2.8, 데이터셋 정의서 v9
- lifesync360-platform Flask 초기 버전 (로그인/동의/홈/상품/설정)
- Ansible 레포 초기 구성 (mysql / tokenization / private_api role)

### 2026-05-04
- platform Aurora 연동 코드 (register/login/me/consent)
- templates 수정 (login 리다이렉트, consent 전체선택, settings 동의상태 로드)
- buildspec.yml IMAGE_TAG 누락 버그 수정 / taskdef.json 리소스 조정

### 2026-05-05
- platform DynamoDB 연동 (dashboard 점수), Redis 연동 (추천 캐시)
- admin-platform 신규 구축 (overview / users / user_detail, 포트 5001)
- lambda/gcp_result_ingest build.sh

### 2026-05-06
- Site-to-Site VPN 연결 (TGW ↔ ls-api)
- ls-token 자격증명 영속성 수정 (systemd 템플릿 환경변수 주입)
- taskdef.json 컨테이너명 / 패밀리명 정합성 수정 (platform)
- admin-platform gunicorn 전환 / CI 완성 / taskdef.json + buildspec.yml + appspec.yaml 신규
- lambda/customer_profile_sync 작성 (로그인 시 global_id 조회)
- GitHub Actions Monorepo 통합 (루트 .github/workflows/)
- 보안 감사 — 하드코딩 민감정보 5건 제거 / Ansible Vault 패턴 구성

### 2026-05-07
- platform UI: 건강점수 모달, 지표 pills, MY탭 세그먼트, 계열사 보유상품 드릴다운
- 업그레이드 액션 개인화 엔진 (upgrade_actions_engine.py)
- 동의 기반 접근 제어 (/api/my-products 403)
- Mock 3명 유저 (PLATINUM/GOLD/SILVER) + 계정별 동의 범위
- ECR/ECS IaC 전면 수정 (레포명, Blue/Green 전환, DesiredCount=0)
- ALB Green TG + TestListener 추가
- CodeDeploy Blue/Green / CodePipeline CodeDeployToECS 전환
- buildspec.yml imageDetail.json 전환 (CodeDeployToECS 포맷)
- 초기 데이터 3종 적재 완료 (→ Step 7)

### 2026-05-08
- PII 암호화 설계 및 가이드 작성 (→ pii-encryption-guide.md)
- PII 암호화 구현 완료 — app.py, service.j2, tasks/main.yml, hosts.yml, onprem_schema.sql 5개 파일 수정
- master_customer 100만 건 Fernet 암호화 마이그레이션 완료 (representative_name, birth_dt)
- private_api DB 접속 방식 변경 — Secrets Manager → 환경변수 (DB_HOST, DB_USER, DB_PASS)
- Ansible Vault 암호화 완료 (private_api, tokenization)
- onprem-prod-repo README 최신화
- MySQL root 비밀번호 재설정 (skip-grant-tables 복구)
- Site-to-Site VPN BGP → Static 라우팅 전환 (→ aws-vpn-setup.md 문제3 참고)

### 2026-05-13 (2차)

- **consent_filter Lambda 신규 작성** (`lambda/consent_filter/`)
  - 역할: Glue/EMR 실행 전 온프레미스 MySQL `consent` 테이블 조회 → 동의 고객 gzip CSV를 S3에 저장
  - `handler.py`, `requirements.txt`(pymysql==1.1.1), `build.sh` 작성
  - 도메인별 동의 피벗 SQL (`MAX(CASE WHEN domain = ... AND consent_flag = 'Y')`)
  - `SSDictCursor` 서버사이드 커서로 스트리밍 처리 — 100만 건 이상도 Lambda 메모리 초과 없음
  - Glue Job 트리거(`--consent_s3_path`, `--job_date` 인자 전달) + EMR Step 추가 선택 지원
  - 출력 S3 경로: `s3://<OUTPUT_BUCKET>/consent-filter/<YYYYMMDD>/consented_customers.csv.gz`

- **IaC/Glue 전달 문서 작성**
  - `docs/iac-consent-filter-lambda.md`: Lambda 설정, 환경변수, VPC/SG, IAM, EventBridge Scheduler, 배포 절차, 체크리스트
  - `docs/glue-emr-consent-spec.md`: 실행 흐름, S3 파일 스펙, 컬럼 구조, PySpark 코드 예시, EMR 연동, 장애 대응

- **아키텍처 다이어그램(17페이지) ERD 검토 → 온프레미스 스키마/코드 불일치 발견**
  - 실제 배포 schema.sql vs 아키텍처 다이어그램 차이 비교
  - 주요 불일치: `consent_key`→`domain`, `consent_yn`→`consent_flag`, `global_id`→`global_customer_id`, 도메인 값(INS/ONINS/SEC/HLT→INSURANCE/SECURITIES/HEALTHCARE), HOSPITAL 추가, ONINS 제거
  - `gcp_result_ingest`: GRADE_MAP PLATINUM/BRONZE 없는 등급 사용, recommend_rule SQL 컬럼 전체 오류, UPDATE users를 Aurora로 연결하는 버그

- **온프레미스 schema.sql 전면 재작성** (`onprem-prod-repo/ansible/roles/mysql/files/schema.sql`)

  | 테이블 | 변경 내용 |
  |--------|-----------|
  | `users` | `id`→`user_id`, `global_id`→`global_customer_id`, `email`→`login_email`, `name`/`grade` 제거, `mobile`/`user_status`/`consent_completed`/`last_login_dt` 추가 |
  | `master_customer` | `global_id`→`global_customer_id`, `representative_name`/`birth_dt`/`gender`/`nationality` 제거, `customer_status`/`vip_grade`/`customer_type` 추가 |
  | `consent` | `global_id`→`global_customer_id`, `consent_key`→`domain`, `consent_yn`→`consent_flag`, `consent_version`/`revoke_dt` 추가 |
  | `customer_identity_map` | `global_id`→`global_customer_id`, `company_id`→`domain`, `affiliate_customer_id`→`source_customer_id`, `match_type`/`active_flag` 추가 |
  | `customer_360_profile` | `global_id`→`global_customer_id`, `grade` 제거, `gender`/`age_band`/`region`/`income_grade`/`asset_grade`/`wearable_flag`/`health_score`/`finance_score`/`asset_score` 추가 |
  | `customer_pii_secure` | `pii_type`/`encrypted_val` 구조 → `customer_name_enc`/`ssn_enc`/`mobile_enc`/`email_enc`/`address_enc` 필드별 암호화 컬럼으로 재설계 |
  | `matching_audit_log` | `id`/`action_type`/`action_detail` → `audit_id`/`request_id`/`match_rule`/`result`/`match_score`/`consent_dt`/`request_dt` 등 전면 재설계 |
  | `token_map` | `global_id`→`global_customer_id` |

- **코드 전면 수정 (아키텍처 기준 컬럼명 통일)**

  - **`consent_filter/handler.py`**
    - `CONSENT_KEYS`: `INS/ONINS/SEC/HLT/wearable` → `SECURITIES/INSURANCE/HEALTHCARE/HOSPITAL/WEARABLE`
    - SQL: `consent_key`→`domain`, `consent_yn`→`consent_flag`, `global_id`→`global_customer_id AS global_id` (Glue CSV 호환)

  - **`lifesync360-platform/app.py`**
    - `COMPANIES`/`CONSENTS`: 도메인 값 전체 변경, ONINS 제거, HOSPITAL 추가, wearable→WEARABLE
    - consent INSERT: `consent_key`→`domain`, `consent_yn`→`consent_flag`, `global_id`→`global_customer_id`
    - register: `master_customer`/`users` INSERT 컬럼명 통일 (`login_email`, `global_customer_id`, `name`/`grade` 제거)
    - login: `WHERE email` → `WHERE login_email`, `global_id` → `global_customer_id`
    - me: `SELECT` 컬럼명 통일, `name`/`grade`는 NULL 반환 (PII/DynamoDB에서 별도 조회 필요)

  - **`private_api/app.py`**
    - 전체 엔드포인트: `global_id`→`global_customer_id`, `consent_key`→`domain`, `consent_yn`→`consent_flag`
    - `company_id`→`domain`, `affiliate_customer_id`→`source_customer_id`
    - `MatchRequest` 모델 필드명 통일, matching_audit_log INSERT 컬럼명 통일

  - **`gcp_result_ingest/handler.py`**
    - `GRADE_MAP`: VIP→PLATINUM 제거, BRONZE 제거, CARE 추가 (VIP/GOLD/SILVER/BASIC/CARE 1:1 매핑)
    - `GRADE_LEVELS` 전체 제거
    - `_fetch_recommended_ids` SQL: `recommend_rule → category_master → product_master` JOIN 경로로 전면 수정 (`active_flag='Y'`, `target_grade=%s`, `priority_rank` 정렬)
    - `UPDATE users SET grade` 단계 제거 (users에 grade 컬럼 없음, grade는 DynamoDB `dynamic_grade`로 관리)

  - **`customer_profile_sync/handler.py`**
    - DB 연결: `AURORA_HOST` → `AUTH_DB_HOST` (on-prem MySQL)
    - `DB_NAME`: `lifesync` → `lifesync_onprem`
    - 컬럼명: `global_id`→`global_customer_id`
    - Private API 쿼리 파라미터: `company_id` → `domain`
    - 기본값: `DEFAULT_COMPANY='bank'` → `DEFAULT_DOMAIN='BANK'`

- **온프레미스 실서버 마이그레이션 스크립트**

  > `CREATE TABLE IF NOT EXISTS`는 기존 테이블을 변경하지 않음 — Ansible 재배포만으로는 컬럼명이 바뀌지 않는다. 아래 ALTER TABLE 스크립트를 ls-db에서 직접 실행해야 함.
  > 실행 전 필수 백업: `mysqldump -u root -p lifesync_onprem > /backup/pre_migration_$(date +%Y%m%d).sql`

  ```sql
  USE lifesync_onprem;

  -- ① users: id→user_id, global_id→global_customer_id, email→login_email, name/grade 제거, 신규 컬럼 추가
  ALTER TABLE users
    RENAME COLUMN id TO user_id,
    RENAME COLUMN global_id TO global_customer_id,
    RENAME COLUMN email TO login_email,
    DROP COLUMN name,
    DROP COLUMN grade,
    ADD COLUMN mobile VARCHAR(20) NULL,
    ADD COLUMN user_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    ADD COLUMN consent_completed CHAR(1) NOT NULL DEFAULT 'N',
    ADD COLUMN last_login_dt TIMESTAMP NULL;

  -- ② master_customer: global_id→global_customer_id, PII 컬럼 제거(customer_pii_secure로 분리), 신규 컬럼 추가
  ALTER TABLE master_customer
    RENAME COLUMN global_id TO global_customer_id,
    DROP COLUMN representative_name,
    DROP COLUMN birth_dt,
    DROP COLUMN gender,
    DROP COLUMN nationality,
    ADD COLUMN customer_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    ADD COLUMN vip_grade VARCHAR(10) NOT NULL DEFAULT 'NORMAL',
    ADD COLUMN customer_type VARCHAR(20) NOT NULL DEFAULT 'INDIVIDUAL',
    CHANGE COLUMN created_dt first_created_dt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN last_updated_dt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

  -- ③ consent: global_id→global_customer_id, consent_key→domain, consent_yn→consent_flag, 신규 컬럼 추가
  ALTER TABLE consent
    RENAME COLUMN global_id TO global_customer_id,
    RENAME COLUMN consent_key TO domain,
    RENAME COLUMN consent_yn TO consent_flag,
    ADD COLUMN consent_version VARCHAR(10) NOT NULL DEFAULT 'v1.0',
    ADD COLUMN revoke_dt TIMESTAMP NULL;

  -- ④ customer_identity_map: global_id→global_customer_id, company_id→domain, affiliate_customer_id→source_customer_id
  ALTER TABLE customer_identity_map
    RENAME COLUMN global_id TO global_customer_id,
    RENAME COLUMN company_id TO domain,
    RENAME COLUMN affiliate_customer_id TO source_customer_id,
    ADD COLUMN match_type VARCHAR(10) NOT NULL DEFAULT 'EXACT',
    ADD COLUMN active_flag CHAR(1) NOT NULL DEFAULT 'Y';

  -- ⑤ customer_360_profile: global_id→global_customer_id, grade 제거, 신규 컬럼 추가
  ALTER TABLE customer_360_profile
    RENAME COLUMN global_id TO global_customer_id,
    DROP COLUMN grade,
    ADD COLUMN gender CHAR(1) NULL,
    ADD COLUMN age_band VARCHAR(10) NULL,
    ADD COLUMN region VARCHAR(50) NULL,
    ADD COLUMN income_grade VARCHAR(10) NULL,
    ADD COLUMN asset_grade VARCHAR(10) NULL,
    ADD COLUMN wearable_flag CHAR(1) NOT NULL DEFAULT 'N',
    ADD COLUMN health_score DECIMAL(5,1) NULL,
    ADD COLUMN finance_score DECIMAL(5,1) NULL,
    ADD COLUMN asset_score DECIMAL(5,1) NULL,
    ADD COLUMN lifesync_score DECIMAL(5,1) NULL;

  -- ⑥ token_map: global_id→global_customer_id
  ALTER TABLE token_map
    RENAME COLUMN global_id TO global_customer_id;

  -- ⑦ consent 도메인값 마이그레이션 (구 값 → 신 값)
  UPDATE consent SET domain = 'INSURANCE'  WHERE domain = 'INS';
  UPDATE consent SET domain = 'SECURITIES' WHERE domain = 'SEC';
  UPDATE consent SET domain = 'HEALTHCARE' WHERE domain = 'HLT';
  UPDATE consent SET domain = 'WEARABLE'   WHERE domain = 'wearable';
  DELETE FROM consent WHERE domain = 'ONINS';

  -- ⑧ customer_identity_map 도메인값 마이그레이션
  UPDATE customer_identity_map SET domain = 'INSURANCE'  WHERE domain = 'INS';
  UPDATE customer_identity_map SET domain = 'SECURITIES' WHERE domain = 'SEC';
  UPDATE customer_identity_map SET domain = 'HEALTHCARE' WHERE domain = 'HLT';
  UPDATE customer_identity_map SET domain = 'WEARABLE'   WHERE domain = 'wearable';

  -- ⑨ customer_pii_secure: 구 구조(pii_type/encrypted_val)에서 필드별 컬럼 구조로 재설계
  --    기존 데이터가 없다면 DROP 후 schema.sql 재적용, 있다면 별도 마이그레이션 스크립트 필요
  DROP TABLE IF EXISTS customer_pii_secure;
  CREATE TABLE customer_pii_secure (
      pii_token            VARCHAR(36)  NOT NULL PRIMARY KEY,
      global_customer_id   VARCHAR(30)  NOT NULL,
      customer_name_enc    TEXT,
      ssn_enc              TEXT,
      mobile_enc           TEXT,
      email_enc            TEXT,
      address_enc          TEXT,
      created_dt           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
      updated_dt           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX idx_global (global_customer_id),
      CONSTRAINT fk_pii_customer FOREIGN KEY (global_customer_id)
          REFERENCES master_customer(global_customer_id)
  );
  ```

  > `RENAME COLUMN` 문법은 MySQL 8.0+ 전용. Ubuntu 22.04 기본 MySQL이 8.0이므로 정상 동작.
  > 마이그레이션 완료 후 `SHOW COLUMNS FROM users;` 등으로 컬럼명 확인 필수.

- **로컬 테스트 환경 정비**

  - `lifesync360-platform/app.py` 에서 `JWT_SECRET` 라인이 주석처리된 것 발견
    ```python
    # 기존 (주석처리됨 → 변수 미정의 상태 → 로컬 실행 불가)
    # JWT_SECRET = os.environ['JWT_SECRET']

    # 수정 후 (로컬 fallback + 운영 환경 변수 주입 공존)
    JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-jwt-secret-lifesync360-32bytes!!')
    ```
  - `lifesync360-platform/make_token.py` 신규 작성 — 로컬 테스트용 JWT 토큰 발급
    ```python
    import jwt
    import datetime
    from datetime import timezone

    JWT_SECRET = 'dev-jwt-secret-lifesync360-32bytes!!'

    token = jwt.encode({
        'sub': 'LS-AABBCC11-000001',
        'gid': 'G000000001',
        'exp': datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=24),
    }, JWT_SECRET, algorithm='HS256')

    print(token)
    ```
  - `.env.local`은 이미 `JWT_SECRET=dev-jwt-secret-lifesync360-32bytes!!` 포함 → 수정 불필요
  - 로컬 테스트 실행 방법:
    ```bash
    cd lifesync360-platform

    # 토큰 발급
    python make_token.py
    # 출력 예: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

    # 앱 실행 (Mock 모드)
    USE_MOCK=true JWT_SECRET=dev-jwt-secret-lifesync360-32bytes!! python app.py

    # API 호출 테스트
    curl http://localhost:5000/api/me \
      -H "Authorization: Bearer <위에서 발급한 토큰>"
    ```

- **미완료 / 추후 작업 필요**
  - `/api/me` 응답의 `name`: `customer_pii_secure` 복호화 연동 필요
  - `/api/me` 응답의 `grade`: DynamoDB `dynamic_grade` 조회 연동 필요
  - 온프레미스 실서버에 schema.sql 변경사항 마이그레이션 적용 필요 (위 ALTER TABLE 스크립트 실행)

---

### 2026-05-14 (2차)

- **lifesync360-platform 포인트 기능 완전 제거**
  - Aurora에 `points` / `point_history` 테이블 없음 → 기능 삭제 결정
  - `app.py`: `MOCK_POINTS`, `MOCK_POINT_HISTORY` import 제거, `settings()` 라우트 단순화 (포인트 변수 전달 제거)
  - `templates/settings.html`: 포인트 탭 버튼(`.stab-bar`), 포인트 잔액 카드, 포인트 이력 테이블 전체 삭제, `switchStab()` JS 함수 제거
  - 등급 정보는 DynamoDB에서 조회 — `settings.html` grade 표시 영역 유지

- **admin-platform Aurora 쿼리 전면 재작성 (실제 Service-DB 스키마 기준)**
  - `overview()` 비Mock 블록:
    - `active_campaigns`: `campaign_master WHERE end_date >= CURDATE()` (컬럼명 `start_date`/`end_date` 반영)
    - `recent_recommends`: `customer_recommend_history` JOIN `product_master` (`clicked_flag`/`purchased_flag` CHAR(1) 방식)
    - `product_funnel`: `customer_recommend_history` JOIN `product_master` + `company_master`, `SUM(clicked_flag="Y")` 집계
    - `top_viewed`: `customer_dashboard_log` JOIN `product_master` WHERE `product_click='Y'` (존재하지 않는 `customer_event_log` 대체)
    - `tab_clicks`: `customer_dashboard_log GROUP BY page_type`
  - `users()` 비Mock: DynamoDB scan 기반 목록 — Aurora `users_ref` 동기화 전까지 `name`/`email`은 `'-'` 표시
  - `user_detail()` 비Mock: DynamoDB(점수/등급) + Lambda(_call_onprem 'get_consent') + Aurora(추천 이력) + Private API(제휴사 매핑)
  - 등급 분포 집계: DynamoDB scan → `dynamic_grade` 기준 집계 (Aurora users.grade 컬럼 없음)

- **admin-platform Mock 데이터 실제 스키마 기준 전면 정합**
  - `MOCK_CONSENTS`: `consent_key`→`domain`, `consent_yn`→`consent_flag`, 모든 도메인 키 대문자 통일
  - `MOCK_RECOMMEND_HISTORY` / `MOCK_RECENT_RECOMMENDS`: `clicked_at`/`purchased_at` DATETIME → `clicked_flag`/`purchased_flag` CHAR(1) 'Y'/'N'
  - `MOCK_CAMPAIGNS`: `start_dt`/`end_dt` → `start_date`/`end_date`
  - `MOCK_USERS`: `PLATINUM`→`VIP`, `BRONZE`→`BASIC` (실제 등급 체계 반영)
  - `MOCK_PRODUCT_FUNNEL`: `affiliate` 값 대문자 통일 (`'insurance'`→`'INSURANCE'` 등)
  - `MOCK_TAB_CLICKS`: `'포인트'` 항목 제거

- **admin-platform 템플릿 컬럼명 수정**
  - `overview.html`: `url_for('user_detail', ls_user_id=...)` → `global_id=...`, `c.start_dt`/`c.end_dt` → `c.start_date`/`c.end_date`, `r.purchased_at`/`r.clicked_at` → `r.purchased_flag == 'Y'`/`r.clicked_flag == 'Y'`
  - `user_detail.html`: `c.consent_key`→`c.domain`, `c.consent_yn == 'Y'`→`c.consent_flag == 'Y'`, 추천이력 플래그 동일 변경
  - `users.html`: `url_for('user_detail', ls_user_id=...)` → `global_id=...`

- **온프레미스 대량 조회 아키텍처 결정**
  - 유저 목록/검색(bulk) → Lambda round-trip 부적합, 응답 지연 + 비용 문제
  - 단기: DynamoDB 기반 유저 목록 (`name`/`email`은 `-` 표시)
  - 장기: Aurora `users_ref` 동기화 테이블 구축 — 온프레미스 `users` 테이블의 비PII 필드 (`global_id`, `ls_user_id`, `login_email`, `user_status`)를 주기적으로 Aurora에 동기화
  - 개별 유저 조회(user_detail) → Lambda OK (per-user action, 지연 허용)

- **미완료 / 추후 작업 필요**
  - Aurora `users_ref` 동기화 테이블 설계 및 구현 (어드민 유저목록 이름/이메일 표시, total_users 정확도)
  - consent_rate 어드민 overview 현재 0 하드코딩 → `users_ref` 동기화 후 구현
  - `/api/me` name 복호화 (`customer_pii_secure` KMS/AES 방식 확정 필요)
  - `/api/me` grade DynamoDB 연동

---

### 2026-05-14 (1차)

- **온프레미스 고객 데이터 조회 Lambda 신규 작성** (`lambda/onprem_customer_query/`)
  - 역할: Platform VPC → Site-to-Site VPN → 온프레미스 Private API 직접 호출 (Control Node 미경유)
  - 지원 액션: `login` / `register` / `get_user` / `get_consent` / `save_consent` / `get_profile` / `get_all`
  - stdlib(urllib)만 사용, 외부 의존성 없음 (`requirements.txt` 비어있음)
  - 환경변수: `PRIVATE_API_URL=http://172.16.1.73` (VPN 경유 on-prem API 주소)
  - 엔드포인트 매핑:

    | action | HTTP | 경로 |
    |--------|------|------|
    | login | POST | `/internal/auth/login` |
    | register | POST | `/internal/auth/register` |
    | get_user | GET | `/internal/auth/user/{ls_user_id}` |
    | get_consent | GET | `/internal/consent/{global_id}` |
    | save_consent | POST | `/internal/auth/consent` |
    | get_profile | GET | `/internal/customer/{global_id}` |
    | get_all | GET ×2 | customer + consent 순차 조회 후 병합 |

- **private_api/app.py — 인증 엔드포인트 4개 신규 추가**
  - `POST /internal/auth/login`: `login_email` 기준 사용자 조회 + `check_password_hash` 검증 (werkzeug)
  - `POST /internal/auth/register`: `master_customer` + `users` 동시 INSERT
  - `GET /internal/auth/user/{ls_user_id}`: 사용자 조회
  - `POST /internal/auth/consent`: `consent` 테이블 UPSERT (`INSERT ... ON DUPLICATE KEY UPDATE`)
  - 전체 필드명 `global_customer_id` → `global_id` 전환 (팀 합의 반영)
  - `ansible/roles/private_api/tasks/main.yml` pip 목록에 `werkzeug` 추가

- **lifesync360-platform/app.py — 온프레미스 Lambda 연동 전환**
  - `get_auth_db()` 직접 연결 제거 → `_call_onprem(action, **kwargs)` Lambda 호출 헬퍼로 대체
  - `ONPREM_QUERY_LAMBDA = os.environ.get('ONPREM_QUERY_LAMBDA', '')` 환경변수로 함수명 주입
  - register / login / me / consent 라우트 모두 Lambda 경유로 전환
  - `taskdef.json`에 `{ "name": "ONPREM_QUERY_LAMBDA", "value": "lifesync-onprem-customer-query" }` 추가
  - `taskdef.json`에 `AUTH_DB_HOST` 환경변수 없음 → Lambda 전환으로 해소

- **Control Node deploy_webhook — PRIVATE_API_URL 추가 및 `/query` 엔드포인트**
  - `deploy_webhook.service`에 `Environment=PRIVATE_API_URL=http://172.16.1.73` 추가
  - `deploy_webhook.py`에 `/query` 엔드포인트 추가 (Option B 백업 경로 — Lambda는 직접 VPN 사용)

- **멀티 VPC IPSec 설계 확인**
  - StrongSwan `rightsubnet`에 여러 CIDR 콤마 구분 지원 확인
  - Platform VPC + Data VPC CIDR 추가 시 기존 Management VPC 터널 영향 없음
  - On-prem ipsec.conf 수정 필요 (IaC 배포 전 온프레미스 담당자 작업):
    ```
    rightsubnet=<Management VPC CIDR>,<Platform VPC CIDR>,<Data VPC CIDR>
    ```
    수정 후: `sudo systemctl restart strongswan-starter`

- **미완료 / 추후 작업 필요**
  - Lambda IaC 배포: Platform VPC 서브넷 지정, SG outbound 172.16.1.73:80, env `PRIVATE_API_URL`
  - ECS Task Role (`lifesync-EcsPlatformTaskRole`) — `lambda:InvokeFunction` 권한 추가 필요
  - On-prem ipsec.conf `rightsubnet` Platform VPC CIDR 추가 + StrongSwan 재시작
  - `schema.sql` 및 기존 수정 파일(consent_filter, customer_profile_sync 등)의 `global_customer_id` → `global_id` 전환 (팀 합의 기준으로 불일치 상태)
  - Platform VPC TGW Attachment IaC (현재 Management VPC만 TGW 연결됨)

---

### 2026-05-13 (1차)

- **Service-DB 분석 및 aurora_schema.sql 정리**
  - `.tmp_extract/Service-DB/` 압축 해제 후 SQL 파일 8개 분석 완료
  - Service-DB 구조 파악: `company_master`(6개) × `category_master`(15개) × `base_product_pool`(120) × `product_variant`(10) → `product_master` 1,200건 자동생성
  - `recommend_rule`(score 기반 36+건), `cross_sell_rule`(53건), `campaign_master`(110건)
  - grade 체계 변경 확인: BASIC/BRONZE/SILVER/GOLD/PLATINUM → VIP(90)/GOLD(80)/SILVER(70)/BASIC(60)/CARE(0)
  - `clicked_flag`/`purchased_flag` CHAR(1) 방식 확인 (DATETIME 아님)
  - aurora_schema.sql에 잘못 포함됐던 `users`/`consent` 테이블 위치 파악
    - 아키텍처 14페이지 기준: users/consent는 온프레미스 전용 → Service-DB(aurora)에 없는 게 맞음

- **lifesync360-platform 클라우드 전환 (app.py 전면 재작성)**
  - 기존 mock 파일 백업: `mock_backup.zip` (app.py + mock_data.py)
  - `get_db()` → `lifesync360` Service-DB 연결 (AURORA_HOST/DB_USER/DB_PASS/DB_NAME)
  - `get_auth_db()` 신규 추가 → 온프레미스 auth DB 연결 (AUTH_DB_* 환경변수)
  - `GRADE_SCORE_MAP`: VIP(90)/GOLD(80)/SILVER(70)/BASIC(60)/CARE(0) 반영
  - `GRADE_BENEFITS`: BRONZE/PLATINUM 제거, VIP/GOLD/SILVER/BASIC/CARE 전환
  - `COMPANIES`: 기존 키 → BANK/CARD/INS/ONINS/SEC/HLT (Service-DB company_code 일치)
  - `api_recommendations`: DynamoDB `dynamic_grade` 기준 grade 조회, `min_score` 필터, `customer_recommend_history` INSERT
  - `api_event`: `clicked_at=NOW()` → `clicked_flag='Y'` / `purchased_flag='Y'`
  - `product/<product_code>`: product_code VARCHAR 조회, company_master + category_master + product_option JOIN
  - `api_my_products`: `purchased_flag='Y'` 기준 조회
  - 인증 라우트(register/login/me/consent) 전체 `get_auth_db()` 사용으로 전환
  - `.env.example` 업데이트 (AUTH_DB_* 항목 추가)

- **온프레미스 스키마 누락 버그 수정**
  - `db/onprem_schema.sql`: users 테이블에 `global_id`/`grade` 컬럼 누락 → 추가
  - `onprem-prod-repo/ansible/roles/mysql/files/schema.sql`: users 테이블 자체가 없었음 → 추가 (실제 배포 파일)
  - 아키텍처 구성도 14페이지 확인 후 수정 — 초기 구성 시 참조 누락이 원인

- **회원가입 flow 버그 3건 수정 (api_register)**
  1. `global_id` NULL 유지 버그 → `G-{uuid.hex[:12].upper()}` 생성 코드 추가
  2. `master_customer` INSERT 누락 → 회원가입 시 `representative_name`과 함께 INSERT
  3. JWT `gid` 클레임에 `ls_user_id` 오입력 → 실제 `global_id` 사용으로 수정

- **register.html 유효성 검사 추가**
  - name/email/password input에 `required` 속성 추가
  - password input에 `minlength="8"` 추가
  - 클라이언트 JS 검증: 필수 항목 빈값 체크 + 8자 미만 체크
  - phone/rrn 필드는 PII 암호화 파이프라인용으로 유지 (제거 안 함)

### 2026-05-12

- Platform CI/CD 파이프라인 전체 트러블슈팅 및 정상화
  - GitHub Secrets 오염 (Excel `+`→`=` 변환) 수정, IAM 액세스 키 재발급
  - buildspec 경로 `deploy/buildspec.yml`로 이동, `imagedefinitions.json` 포맷 수정
  - CodeBuild Role SSM/AS/CloudWatch 권한 추가 (`docs/codebuild-role-policy.json`)
  - CodePipeline Role S3 아티팩트 권한 추가
  - buildspec env에 실제 클러스터/서비스명 하드코딩 수정
  - Application Auto Scaling post_build 등록 (CPU 70% scale-out / 30% scale-in, min 1 / max 4)
  - ECS 태스크 exit 3 원인: `JWT_SECRET` 미설정 → SSM `/lifesync360/jwt-secret` 생성, 태스크 정의 revision 6 등록 (JWT_SECRET secret, USE_MOCK=true, CloudWatch 로그 설정)
  - ECS Execution Role SSM 권한 추가
  - 포트 불일치 수정: ALB 타겟 그룹이 80 고정이라 Dockerfile Gunicorn 바인딩 포트를 8000 → 80으로 수정
  - ECS 배포 설정 `minimumHealthyPercent=0, maximumPercent=200` 수정 (롤링 업데이트 가능하도록)
  - 트러블슈팅 문서: `docs/cicd-troubleshooting-and-iac-tasks.md`
  - IaC 전달 항목: `docs/iac-tasks.md` (Execution Role, SSM, 태스크 정의, Log Group, 배포 설정)
- update-vpn-tunnel.sh 버그 수정 3건
  - **Windows CRLF `\r` 버그 (IP 미반영 근본 원인)**: Windows AWS CLI가 CRLF로 출력 → `$()` substitution이 `\n`은 제거하지만 `\r`은 남김 → TUNNEL_IP에 `\r` 포함 → sed가 ipsec.conf에 `right=IP\r` 기록 → StrongSwan 파싱 실패. `tr -d '\r'` 추가 (TUNNEL_IP 2곳, PSK SM 조회 1곳)
  - **PSK 조회 로직 재설계**: 기존 ipsec.secrets에서 sed로 PSK 추출하는 방식 제거 → VPN_PSK 환경변수(우선순위 1) / Secrets Manager(우선순위 2) / 없으면 exit 1
  - **ipsec.secrets 업데이트 방식 변경**: sed 패턴 매칭 → printf+tee 전체 교체 (sed는 매칭 실패 시 exit 0 반환으로 오류 감지 불가)
- docs/control-node-deploy-guide.md 최초 작성 완료 (14a/14b/14c 3단계 배포 가이드, 트러블슈팅, 주요 경로 표)

### 2026-05-11
- admin-platform 대시보드 사이드바 탭 네비게이션 개편 (overview 4탭, user_detail 5탭)
- admin-platform 동의현황 / 추천이력 / 제휴사매핑 / 활성캠페인 / 최근추천 섹션 추가
- EC2 Control Node CloudFormation IaC 작성 (infra/compute/control-node.yaml)
  - IAM Role: Secrets Manager + CodeCommit + SSM
  - UserData: 패키지 설치 → CodeCommit 클론 → vault 패스워드 → Deploy Server → SSH 키 배포
- Deploy Server 구축 (infra/deploy-server/)
  - Flask 9000포트, /health + /deploy 엔드포인트, X-Deploy-Token 인증
  - DEPLOY_TOKEN 하드코딩 → Secrets Manager(lifesync/deploy-token) → /etc/deploy-server/env 분리
- setup-ssh-keys.sh: mkdir -p ~/.ssh 누락 수정, ~/.vault_pass 없을 때 안전 처리
- hosts.yml: ls-db / ls-token에 ansible_ssh_common_args ProxyJump(via ls-api) 추가
- Ansible 14a/14b/14c IaC 분석 — SSH 키 미생성 원인 파악
  - 14b UserData 실행 순서: git clone → SSH 키 생성. set -euo pipefail + git clone 실패 시 exit 1 → SSH 키 생성 미실행
  - git clone 실패 원인: Management VPC private subnet에서 CodeCommit 퍼블릭 엔드포인트 접근 불가 (NAT GW 없음)
  - 14a IAM: codecommit:GitPush 불필요 (Ansible이 CodeCommit에 push하는 케이스 없음) — 제거 권고
  - deploy-control-node.sh 불일치 항목 확인: CF Output 키(`InstanceId` → `AnsibleControlInstanceId`), 완료 확인 파일(`/tmp/control-node-ready` — 14b에 없음)
- Management VPC 네트워크 경로 분석
  - TGW→VPN은 온프레미스↔AWS 경로, Ansible EC2→CodeCommit 경로와 무관
  - 기존 01b-lifesync-vpc-endpoints.yaml: LifeSync VPC(ECS)용, CodeCommit/SSM 엔드포인트 없음
  - Management VPC는 별도 VPC → 전용 VPC Endpoints 파일 신규 작성 필요
- 01c-management-vpc-endpoints.yaml 작성 완료
  - S3 Gateway(무료) + SSM×3 + CodeCommit×2 인터페이스 엔드포인트
  - 예상 비용 ~$36/월 (1 AZ) / NAT GW 있으면 선택사항
- Ansible 14a/14b/14c IaC 수정 완료
  - 14a: codecommit:GitPush 제거
  - 14b: SSH 키 생성 블록을 git clone 앞으로 이동 (순서 역전 버그 수정)
  - 14b: sudo -u ansible git → sudo -u ansible /usr/bin/git 전체 경로 지정 (sudo env_reset PATH 문제 해결)
  - 14b: ManagementSubnetId 파라미터 설명 NAT GW → VPC Endpoints 참조로 업데이트
  - 14c: aws sts get-caller-identity 사전 체크 제거 (STS VPC Endpoint 없이도 동작)
- 재배포 순서: 14a → 14b → 14b 출력(AnsibleControlInstanceId) 확인 → 14c

---

## 트러블슈팅

### Ansible Control Node SSH 키 미생성 (2026-05-11)

**증상**
- `/home/ansible/.ssh/id_rsa` 파일이 생성되지 않음
- 14c SSM Association이 공개키를 SSM Parameter Store에 올리지 못함

**원인 1 — 14b UserData 실행 순서 버그**
- 원래 순서: `git clone` → `SSH 키 생성`
- `set -euo pipefail` 상태에서 git clone 실패 시 `exit 1` → SSH 키 생성 코드 미실행
- 수정: SSH 키 생성 블록을 git clone **앞으로** 이동

**원인 2 — sudo env_reset으로 인한 git PATH 문제**
- UserData에서 `sudo -u ansible git clone ...` 실행 시 sudo가 PATH 초기화
- git이 `/usr/bin/git`에 설치돼 있어도 초기화된 PATH에서 못 찾아 `env: 'git': No such file or directory` 발생
- 수정: `sudo -u ansible git` → `sudo -u ansible /usr/bin/git` 전체 경로 지정

**원인 3 — 14c에서 STS 엔드포인트 필요**
- `aws sts get-caller-identity` 호출이 퍼블릭 STS 엔드포인트로 나가 VPC Endpoint 없이 실패 가능
- 수정: 해당 사전 체크 제거 (ssm:PutParameter 자체가 IAM 없으면 어차피 실패)

**확인 방법**
```bash
# SSM 세션 접속
aws ssm start-session --target <AnsibleControlInstanceId> --region ap-northeast-2

# UserData 로그 확인
sudo tail -100 /var/log/ansible-bootstrap.log

# 키 존재 여부
ls -la /home/ansible/.ssh/

# SSM에 공개키 올라갔는지
aws ssm get-parameter \
  --name /lifesync/dev/ansible/public-key \
  --region ap-northeast-2 \
  --query Parameter.Value --output text
```

**재배포 순서**
```
14a → 14b → 14b 출력(AnsibleControlInstanceId) 확인 → 14c
```

---

### SSM start-session 오류 모음 (2026-05-11)

| 에러 | 원인 | 해결 |
|------|------|------|
| `Could not connect to endpoint URL: ssm.ap-northease-2...` | 리전명 오타 (`northease` → `northeast`) | `aws configure set region ap-northeast-2` |
| `403 Forbidden` | 로컬 IAM 자격증명에 `ssm:StartSession` 권한 없음 | IAM 정책에 ssm:StartSession 추가 또는 admin 프로파일 사용 |
| `Session Manager plugin not found` | Session Manager Plugin 미설치 | [SessionManagerPluginSetup.exe](https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe) 설치 후 터미널 재시작 |

---

## 배포 전 필수 처리 항목

| 항목 | 담당 | 참고 파일 |
|------|------|-----------|
| PII 암호화 | ~~온프레미스~~ ✅ 완료 | pii-encryption-guide.md |
| Ansible Vault encrypt 실행 | ~~온프레미스~~ ✅ 완료 | Step 9 |
| taskdef.json ACCOUNT_ID 치환 | ~~배포 담당자~~ ✅ 완료 | platform + admin 총 11곳 |
| Secrets Manager 값 입력 (lifesync/aurora, jwt, redis, admin) | 배포 담당자 | cloud-deploy-procedure.md 2단계 |
| Secrets Manager 값 입력 (lifesync/ansible-vault, ansible-vm, deploy-token) | 배포 담당자 | Control Node IaC 배포 전 필수 |
| GitHub Secrets 등록 | 배포 담당자 | AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY |
| Parameter Store 등록 | 배포 담당자 | /lifesync360/ecr-uri / ecr-uri-admin |
| CloudFormation 스택 배포 | IaC 담당자 | cloud-deploy-procedure.md |
| Lambda TGW Attachment (Platform VPC) | IaC 담당자 | lambda-to-onprem-network.md |
| onprem_customer_query Lambda IaC 배포 (Platform VPC / SG outbound 172.16.1.73:80 / PRIVATE_API_URL) | IaC 담당자 | lambda-to-onprem-network.md |
| ECS Task Role lambda:InvokeFunction 권한 추가 (lifesync-EcsPlatformTaskRole) | IaC 담당자 | taskdef.json ONPREM_QUERY_LAMBDA 참고 |
| On-prem ipsec.conf rightsubnet Platform VPC CIDR 추가 + strongswan 재시작 | 온프레미스 담당자 | aws-vpn-setup.md |
| private_api Ansible 재배포 (werkzeug 추가 + 인증 엔드포인트 4개) | 온프레미스 담당자 | roles/private_api/ |
| 동의 고객 선별 Lambda 구현 | 개발 | ETL 파이프라인 AWS→GCP 전송 전 consent 필터링 |
| Aurora users_ref 동기화 테이블 구축 (어드민 유저목록 이름/이메일, total_users 정확도) | 개발 | on-prem users → Aurora 주기 동기화 |

---

## 2026-05-15 ~ 2026-05-16 — 732 계정 전환 + admin UI 리뉴얼

### 작업 요약

**1. 354 → 732 신규 계정 전환**
- `354-mockup-snapshot` 브랜치 + tag 로 354 상태 스냅샷 보존
- `params/data.env` 의 모든 S3 bucket 이름에 `-732264765472` suffix (전역 unique 충돌 회피)
- `taskdef.json` (platform + admin) execution/task Role ARN hash 정정 (`Dm8CCIe7mct9` / `88cLRd8Eqk8y`)
- GitHub Actions `platform.yml` mirror-to-codecommit `if: false` (354 GitHub Secrets 잔존 — 732 키 재발급 후 복원 예정)

**2. 토큰 에러 근본 원인 수정 (IaC)**
- 증상: ECS task 부팅 시 `invalid token` (SSM SecureString fetch 실패)
- 원인: ExecutionRole 에 `ssm:GetParameters` 만 있고 `kms:Decrypt` 누락 → SecureString 복호화 불가
- 수정 파일:
  - `21-lifesync-ecs-existing-vpc.yaml` — ExecutionRole inline policy 에 `kms:Decrypt` (Condition: `kms:ViaService=ssm.${REGION}.amazonaws.com`) 추가
  - `01b-lifesync-vpc-endpoints.yaml` — KMS Interface VPC Endpoint 추가, ECR Public endpoint 제거 (region 미지원)
  - `08-database.yaml` — SqlOpsSsmVpceSg 에 `CidrIp: 10.0.0.0/16` 443 inbound 추가
  - `08-database.yaml`, `08b-lifesync360-service-db.yaml` — DynamoDB `RecommendationResultTable` + SqlAssetsBucket `Retain` → `Delete` (시연/테스트 환경 한정)
- 인계 노트: `docs/iac-handoff-permissions-addon.md`

**3. 732 계정 인프라 cleanup 완료 (재배포 대기 상태)**
- CloudFormation stack 16개 모두 DELETE_COMPLETE (01·02·06·07·08·09·10·11·15·17·18·19·21·gha-cc-*·08b·01b)
- 전 region 잔여 리소스 0 (NAT GW 3개는 `deleted` 상태로 약 1시간 표시 후 자동 소멸)
- Customer-managed KMS 2개 `PendingDeletion` (자동 회수 대기)
- CloudWatch Log Group 2개만 잔존 (codebuild log, 무비용)

**4. admin-platform UI 리뉴얼 (설계서 V1 기준 5메뉴)**
- 사이드바: `Executive Dashboard` / `Customer 360` / `AI 추천` / `운영 모니터링` / `데이터 정합` (시안 mockup 섹션 제거)
- 라우트:
  - `/dashboard` (신규) — 기존 `/overview` 로직 + KPI 6 카드 + Cloud Status + S3 Ingestion
  - `/overview` (302 redirect → `/dashboard`)
  - `/ai` (신규) — Aurora TOP10 + 카테고리/등급별 + DynamoDB 점수 분포 + AI 모델 메타 (mock)
  - `/ops` (신규) — Cloud Status + 도메인 흐름(7) + VM/Lambda/Glue/ETL
  - `/users` → `Customer 360` 라벨 (기존 라우트 재활용)
  - `/data-integrity` (기존 유지)
  - `/mockup/*` 3개 라우트 + 템플릿 제거
- boto3 ping 헬퍼 7종 추가 (`_ping_cloud_status` / `_s3_ingestion` / `_domain_flow` / `_vm_status` / `_lambda_metrics` / `_glue_last_run` / `_next_batch`) — USE_MOCK=true 시 mock fallback, USE_MOCK=false 시 실연동
- 신규 mock dict 10개 (`mockup_data.py`)
- 신규 템플릿 3개 (`dashboard.html`, `ai.html`, `ops.html`)
- wireframe 5장 (`docs/admin-redesign/`)

### 상태

| 항목 | 상태 |
|------|------|
| 732 계정 인프라 cleanup | ✅ |
| IaC 토큰 에러 수정 (KMS+SG+VPCE) | ✅ |
| 354 → 732 git 스냅샷 보존 | ✅ |
| admin 5메뉴 UI 리뉴얼 (USE_MOCK=true 동작) | ✅ |
| admin boto3 ping 헬퍼 (USE_MOCK=false 분기) | ✅ 코드만 |
| 732 계정 인프라 재배포 | ⏳ |
| GitHub Secrets 732 키로 재발급 + mirror-to-codecommit 복원 | ⏳ |
| admin Task Role 에 ping IAM 권한 추가 (rds/dynamodb/elasticache/ecs/elbv2/ec2/lambda/glue/events/cloudwatch Describe*) | ⏳ |

---

## 2026-05-17 — 시트 매핑 정합 / 동의·신청·추천 / admin V3 / ERD / 다크테마 / 354 환원

### 작업 요약

**1. 시트 매핑 정합 (`통합_매핑_시트분할.xlsx` 106행)**

라운드 전 55% (58/106) → 라운드 후 **92%** (98/106).

- Phase 0: 시트 자체 13셀 자동 수정 (openpyxl) — SQL 오류 6 / 모델 결정 3 / 가독성 2 / 보강 1
- Phase 1: **Analytics Batch** 신규 (P3 r10/r12/r13)
  - `lambda/analytics_aggregator/handler.py` (Aurora `customer_recommend_daily` mart INSERT + DDB BatchWrite `analytics_segment_performance`/`analytics_demographic_summary`)
  - `Aws_iac/templates/23-analytics-batch.yaml` (DDB 2 + Lambda + Role + EventBridge cron DISABLED)
  - bash 3종 (`deploy-analytics-batch.sh`, `create-recommend-daily-table.sh`, `invoke-analytics-aggregator.sh`)
  - admin 라우트 3개: `/api/admin/recommend-trend`, `/segment-performance`, `/demographic-summary`
- Phase 2: **온프레 lambda 9 action 추가** (P1 r3-5 / P2 r13-17,22 / P4 r38-43,60)
  - `lambda/onprem_customer_query/handler.py` action 8 → 17
  - `local_lab_status` (RFC api-health-check-06 호환), `count_master_customer/users/users_consented`, `get_master_customer/identity_map`, `vm_health/mysql_health/tokenization_health`
- Phase 3: **Redis admin 실 호출 전환** (P2 r37, P4 r4) — `_get_redis()` + `r.zrevrange('rec:{global_id}', 0, 2, withscores=True)`
- Phase 4: **GCP 4종 SDK 도입** (P3 r9,17,18,22 / P4 r32-36)
  - `_get_bq()`, `_init_aip()`, `_get_mon()` lazy init (인증 실패 시 None)
  - `_stub_gcp_status`/`_stub_vertex_metrics`/`_stub_feature_importance` 본체 교체 + `_stub_bigquery_analytics(kind)` 신규
  - `requirements.txt`: `google-cloud-bigquery==3.27.0`, `aiplatform==1.71.1`, `monitoring==2.27.1`
- Phase 5: **잔여 일괄 처리** — admin 헬퍼 5개 (`_ping_kinesis`/`_ping_wearable_metrics`/`_ping_emr`/`_ddb_score_distribution`/`_ddb_prob_distribution`) + `/api/*` 17개 라우트 + 21 yaml IAM 권한 5개

**2. Platform 동의 / 신청 / 추천 로직 재설계**

- Phase 1: **동의 페이지** — 단순 체크박스 → 8 계열사 카드 UI (icon/label/desc/scope), `CONSENTS` 8개 (BANK/CARD/INSURANCE/SECURITIES/ONLINE_INS/HEALTHCARE/HOSPITAL/WEARABLE)
- Phase 2: **상품 신청 페이지 신규** — 클릭 alert → `/product/<code>/apply` 폼 페이지 + `POST /api/product/<code>/apply` (신청자 정보/상세/약관 + `customer_product_application` INSERT, application_id `APP-YYYYMMDDHHMMSS-{sub[-6]}`)
- Phase 3: **추천 로직 통합 매칭** — DDB grade 단일 매칭 → Service-DB `recommend_rule` + `cross_sell_rule` + results.csv NBA(next_best_action) 통합
  - NBA→action_code 매핑 13종 (RETENTION→RECOMMEND_HEALTH, INSURANCE_UPSELL→RECOMMEND_INSURANCE, PB/WM/INVEST/SAVING/CARD/LOAN/PENSION/WELLNESS/TELEMED ...)
  - 응답 형식: `list` → `{meta: {grade,score,health,vip_prob,next_best_action}, products}`
  - **계열사 분리 X, 단일 list 반환** (사용자 결정)
  - history INSERT action_code 같이 기록 (NBA 매칭 / cross_sell / fallback)
- Phase 4: **프론트 호환** — `index.html` Home/Recommend 탭 응답 처리 통째 교체, USE_MOCK 분기도 신규 형식 변환
- Phase 5: **잔여 5건** — `seed-ddb-from-csv.sh` (results.csv → DDB BatchWriteItem) / `Service-DB/9.customer_product_application.sql` / admin `/api/admin/applications` / NBA 정렬 검증 / `VIP_PROB_THRESHOLD` env (default 0.5)

**3. admin 설계서 V3 정합 + schema_reference 정합**

- 설계서 V3.xlsx 기준 `/api/*` 23개 라우트 매핑 검증, 누락 추가: `/api/local/status` (P4 r60) + alias `/api/admin/local-lab-status`
- helper stub 5종 추가 (`_stub_aurora_summary/_history/_activity/_recommend_stats/_ai_summary`) — DDB/Aurora 응답 없을 때 화면 깨짐 방지
- admin `/ai` SQL 정정: `p.category` → `cat.category_code` (category_master JOIN 추가), CTR/CVR 분모에 `NULLIF` 적용

**4. PPT 슬라이드 16 ERD 이미지 교체** (`아키텍처구성도_2조_V3.7_Lite.pptx`)

- 텍스트 grep 0 hit → **이미지 안 텍스트** 였음 (`ppt/media/image65.png`)
- `docs/preview/pptx_slide16_media/erd_new.html` 작성 (7 entities, schema_reference 정합: `pii_token` PK, `audit_id` PK, `customer_status`/`vip_grade`/`customer_type` enum, score 5개 분리)
- Edge headless → PNG 캡처 → image65.png 교체, 산출 `아키텍처구성도_2조_V3.7_Lite_erd수정.pptx`
- 원본 잠금 (PowerPoint 열림)으로 덮어쓰기 실패 → 새 파일명 저장

**5. admin 다크/라이트 테마 토글**

- `templates/base.html` (67 → 102줄): head FOUC 방지 inline script + body SSR cookie 기반 class + body 끝 toggle script (localStorage + cookie 동기화)
- `static/css/admin.css` 98줄 추가: `.theme-toggle` + ☀️/🌙 아이콘 + `body.dark-theme` override 50건 (배경/사이드바/topbar/카드/inline style `[style*="color:#xxx"]` 매칭 `!important`/SVG 차트 흰 배경/입력 필드)

**6. admin 화면 mockup + 데이터 정합 화면**

- `docs/preview/admin_p1~p4.html` + `_dark.html` 8개 (P1 Executive Dashboard / P2 Customer 360 / P3 AI 추천 / P4 운영 모니터링)
- 시안 zip 분석 (`docs/preview/대시보드UI샘플수정.zip`, `대시보드UI샘플-화이트.zip`)

**7. 354 계정 환원 (732 → 354)**

직전 라운드 732 전환 후 다시 354 작업 환경 복귀. 4 파일 18곳 일괄 치환 (`732264765472` → `354493396671`):

| 파일 | 곳 |
|---|---:|
| `admin-platform/taskdef.json`, `lifesync360-platform/taskdef.json` | 6 + 6 |
| `Aws_iac/.../params/cicd-service-platform.env`, `data.env` | 4 + 2 |

### 상태

| 항목 | 상태 |
|------|------|
| 시트 매핑 정합 92% | ✅ |
| 동의·신청·추천 로직 (Service-DB + NBA) | ✅ |
| analytics_aggregator lambda + DDB mart 2 + Aurora `customer_recommend_daily` | ✅ 코드 |
| 온프레 lambda 17 action | ✅ |
| Redis 실 호출 + GCP SDK 4종 | ✅ 코드 |
| admin 설계서 V3 100% 정합 (23 + 신규 alias) | ✅ |
| schema_reference 정합 (`/ai` SQL 등) | ✅ |
| 다크/라이트 테마 토글 (admin) | ✅ |
| PPT slide 16 ERD 이미지 교체 | ✅ |
| 354 계정 환원 (4 파일 18곳) | ✅ |
| 23 stack deploy + EventBridge ENABLE | ⏳ |
| 온프레 PrivateAPI 신규 9 엔드포인트 구현 | ⏳ |
| GCP Service Account / Workload Identity 셋업 | ⏳ |

---

## 2026-05-18 — Platform JWT 데코레이터 / api_recommendations 분리 / index·CSS 정리

### 작업 요약

**1. 스파게티 코드 진단 (platform 1075줄 / admin 1500줄)**

- platform: 10 라우트에 JWT 인증 5줄 블록 중복 (50줄 중복), `api_recommendations` 235줄 단일 함수
- admin: DDB client 인스턴스 매번 생성, helper stub_ prefix 일관성 X (P2~P3 다음 라운드 이월)

**2. P0 — `@require_jwt` decorator (`lifesync360-platform/app.py:212~223`)**

```python
def require_jwt(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth  = request.headers.get('Authorization', '')
        token = auth.removeprefix('Bearer ').strip()
        try:
            kwargs['payload'] = decode_jwt(token)
        except jwt.InvalidTokenError:
            return jsonify({'error': 'invalid token'}), 401
        return f(*args, **kwargs)
    return wrapper
```

- 10 라우트 적용 (api_me / api_consent / api_event / api_recommendations / api_upgrade_actions / api_my_applications / api_my_products / api_campaigns / api_dashboard / api_product_apply)
- 8 라우트 자동 sed-like 치환 + 2 라우트 수동 정리 (api_me 외부 try-except 제거+outdent, api_dashboard try-except 통째 제거)
- 결과: 50줄 중복 → 12줄 decorator + 10 라우트 / app.py 1075 → 1053줄

**3. P1 — `api_recommendations` 235줄 → 5 helper 분리**

| Helper | 라인 | 책임 |
|---|---:|---|
| `_NBA_TO_ACTION` (상수) | 17 | next_best_action → action_code 매핑 13개 |
| `_recommendations_mock()` | 27 | USE_MOCK 응답 |
| `_fetch_ddb_meta(global_id)` | 13 | DDB → (grade, score, health, vip_prob, nba) 5-tuple |
| `_fetch_redis_cached_ids(global_id)` | 8 | Redis 캐시 hit 조회 |
| `_match_rules(cur, grade, ...)` | 35 | recommend_rule + cross_sell_rule → (cat_list, rule_action_by_cat) |
| `_fetch_products(cur, cached_ids, ...)` | 54 | 3 모드: cache hit / category 매칭 / fallback |
| `_enrich_and_record(cur, products, ...)` | 32 | reason/rec_rank/score 부여 + history INSERT + 점수 재정렬 |

- 본문: 235 → 55줄 (-76%), 응답 인터페이스 (`{meta:{...}, products:[...]}`) 동일 유지

**4. Plan A — index.html / CSS 정리**

| 파일 | 원본 | 정리 후 | 절감 |
|---|---:|---:|---:|
| `index.html` | 360 | 320 | -38 (SSR 추천 탭 + 정적 JS 핸들러 죽은 코드 제거) |
| `app.py` dashboard route | 1053 | 1051 | -2 (`recommendations=recs, companies=COMPANIES` 미사용 인자 제거) |
| `style.css` | 937 | 658 | **-279 (-30%)** (미사용 룰 71개 — `.home-rec-cat*`/`.history-*`/`.grade-card`/`.detail-list`/`.stab-*`/`.my-seg-*`/`.my-product-*`/`.spend-*`/`.upgrade-*`/`.indicator-pill`/`.company-*`/`.section-title` 등) |
| `admin.css` | 265 | 234 | -31 (-12%) (미사용 룰 32개 — `.sidebar-section`/`.stat-*`/`.grade-dist*`/`.funnel-bar*`/`.view-rank-*`/`.search-bar`/`.pagination`/`.btn-ghost`/`.form-select`/`.two/three/four-col`) |

- CSS 자동 정리 python script — 룰 블록 셀렉터 콤마 분리 → 클래스 모두 unused 면 룰 통째 삭제
- **동적 prefix 강제 보호** (`grade-`, `rank-`, `sc-`, `status-`, `tab-`, `rec-`, `badge-`, `fill-`, `ladder-`, `view-rank-`) — JS 가 `grade-${grade}` 등으로 생성하는 클래스 보존

**5. 화면 동작 검증 — Edge headless 11화면 캡처**

- 환경: `/tmp/ls_venv` venv + `pip install -r requirements.txt` (platform/admin)
- platform `:5000` / admin `:5001` BG (USE_MOCK=true)
- 인증 우회: platform `static/_seed.html` (fetch register → setItem ls_token → redirect) / admin curl POST /login cookie → SSR HTML + `<base href>` 삽입 → file://
- 다크모드 캡처 특이 케이스: `base.html` body 끝 script 가 file:// localStorage 빈 값 보고 `apply('light')` 호출 → 그 script 통째 제거 + admin.css inline embed 후 캡처 → 다크 정상 적용

| # | 화면 | 결과 |
|---|---|---|
| 01~04 | platform/admin 로그인·회원가입·동의 | ✅ |
| 05 | platform `/` 홈 | ✅ VIP + 점수 92.4 + 추천 6개 |
| 06 | platform `/settings` | ✅ |
| 07 | platform `/product/DEP-001` | ✅ |
| 08 | admin `/dashboard` | ✅ KPI 10 + AWS/GCP + 가입률 |
| 09 | admin `/users` | ✅ |
| 10 | admin `/ai` | ✅ CTR/CVR/TOP10 |
| 11 | admin **다크모드** | ✅ override 50건 정확 적용 |

### 상태

| 항목 | 상태 |
|------|------|
| P0 `@require_jwt` decorator + 10 라우트 | ✅ |
| P1 `api_recommendations` 5 helper 분리 (235→55) | ✅ |
| Plan A index/style.css/admin.css 정리 (-350줄) | ✅ |
| Edge headless 11 화면 검증 | ✅ |
| **P2** `db.commit/try-finally` → `with get_db()` 통일 | ⏳ |
| **P3** admin DDB client 캐싱, helper stub_ prefix 일관성 | ⏳ |
| **D-1** index.html `my-applications-list` SSR DOM JS 로직 채움 or 제거 판단 | ⏳ |
| **D-2** index.html home 탭 헤더 중복 (정적 + 동적) 정리 여부 판단 | ⏳ |

### 메모

- 캡처 산출물: `C:\Users\campus3S026\AppData\Local\Temp\ls_caps\` (11 PNG + admin_cookie.txt + HTML 임시)
- 임시 venv: `C:\Users\campus3S026\AppData\Local\Temp\ls_venv` (재사용 가능)
- CSS 정리 사고 + 복구 절차 + Edge headless 캡처 트릭 → `local-test-troubleshooting.md` 별도 정리


## 2026-05-18 ② — admin 화이트 샘플 4 페이지 / DB 정합 검증 / PrivateAPI 풍부화 / Service-DB v3 슬림화 / docs 명세

### 작업 요약

**1. admin UI 화이트 샘플 4 페이지 재구성** (`대시보드UI샘플-화이트.zip` 기준)

- 사이드바 제거 + 상단 헤더(LifeSync 360 + 중앙 4탭 + 우측 admin) 구조로 `base.html` 전면 교체
- **다크 토글/스크립트/cookie 처리 전부 제거** — 화이트 단일 톤 (사용자 결정)
- `admin.css` 전면 교체 — 다크 오버라이드 235줄 들어내고 상단 탭/카드/도넛/토폴로지 스타일 추가
- 신규 mockup 21 상수 (`mockup_data.py` `MOCKUP_DASH_*` / `MOCKUP_C360_*` / `MOCKUP_AI_*` / `MOCKUP_NET_*`)
- 4 페이지 새 템플릿:
  - **P1 dashboard.html** — 8 KPI(4×2) + Cloud 3카드(AWS/GCP/On-Prem) + S3 5카드 + 최근 업로드 테이블
  - **P2 users.html** — 검색 + 프로필 헤더(VIP 배지·종합/건강 점수) + 좌3박스(가입·동의보유·Top-N) + 우3박스(AI NBA·정밀점수·추천활동·행동로그)
  - **P3 ai.html** — 4 KPI + 7일 추이 SVG 차트+TOP10 + 도넛(카테고리)·연령 막대·등급 분포 + BigQuery 3박스 + DDB 히스토그램/Precision-Recall
  - **P4 ops.html** — 토폴로지(AWS 3 VPC + GCP + On-Prem) + AWS Platform/Data/GroupVM 3카드 + Connectivity/GCP/On-Prem 3카드 + Wearable 5KPI + API 엔드포인트
- **렌더링 중 발견 → 즉시 수정**: `insight.items`/`c.items`/`topology.*.items` → Jinja dict `.items()` 메서드 충돌 → mockup 키 `rows`/`lines` 로 rename + 템플릿 동시 수정
- Edge headless 1280×1800 4 페이지 캡처 — 모두 정상 렌더링 확인

**2. DB / 리소스 호출 ↔ 스키마 정합 검증** (`Aurora_Schema_Reference.md` + `schema_reference.md` + `results.csv`)

- admin/platform 의 모든 SQL/DDB/Lambda/Redis 호출 추출 → 3 스키마와 1:1 대조
- SDK 사용법 공식문서 검증 (pymysql DictCursor + with / boto3 resource·conditions.Key / redis-py setex·decode_responses / pyjwt 2.0+ algorithms / google-cloud-bigquery·monitoring_v3 / cloudwatch get_metric_statistics) — deprecated/오용 0건
- **P0 (DDL 누락)** — `customer_recommend_daily`, `analytics_segment_performance`, `analytics_demographic_summary` → `docs/today-tables-2026-05-17/` 폴더에 이미 정의 발견 (`23-analytics-batch.yaml` + `create-recommend-daily-table.sh` + GUIDE)
- **P0 신규** — `_fetch_onprem_profile_map` 의 `action='list_profile_all'` 호출 분기가 Lambda handler 17 action 어디에도 없음 → 페이지네이션 필요

**3. PrivateAPI 풍부화 — 3단계**

| # | 단계 | 영향 |
|---|---|---|
| ① | `GET /internal/profile/list-all?page=N&size=10000` 신설 + Lambda `list_profile_page` action 추가 + `analytics_aggregator._fetch_onprem_profile_map` 페이지 루프 + 메모이즈 (`_profile_cache` 모듈 전역, [2]/[3] 두 단계 재호출 시 1회만 fetch) | Lambda sync invoke 6MB 제한 우회. 1M → 10K × 100회 |
| ② | DBUtils `PooledDB` 도입 — `mincached=2 / maxconnections=10 / ping=1 / charset=utf8mb4 / autocommit=False`. `get_db()` 인터페이스 동일 (다른 코드 0줄 변경). ansible role pip 의존성 `DBUtils` 추가 | `pymysql.connect()` 8~25ms → pool 재사용 0.5ms (handler 시간 50~60% 단축) |
| ③ | A 옵션 9 신규 엔드포인트 (count 3 + 단건 2 + health 4 + 종합 1) — Lambda handler 17 action 이 모두 PrivateAPI 본체에 1:1 매핑됨. socket TCP / urllib HTTP 헬퍼 (`_tcp_check`, `_http_check`, `_now_iso`). VM 매핑 env override 가능 | admin 통합 KPI/ops 화면이 빈 값 → 실데이터 표시 |

**4. admin app.py 죽은 코드 정리** (A 옵션 일관성)

- `_get_identities` 함수 + `PRIVATE_API_URL` env 변수 + `import requests` 통째 제거
- 호출처 → `_call_onprem('get_identity_map', global_id=gid)` 로 교체 (Lambda 경유)
- `requirements.txt` 에서 `requests==2.31.0` 제거
- → admin → 온프레 통신 경로 **100% Lambda 경유로 통일** (ECS subnet에 VPN route 추가 불필요)

**5. platform 인라인 DDL 제거 + Service-DB v2 → v3 정합화**

| 변경 | v1 | v2 | **v3 (현행)** |
|---|---|---|---|
| `customer_product_application` 컬럼 수 | 17 (인라인 DDL) | 16 (product_code 제거) | **9** (applicant_*/apply_amount/contact_time/memo/agree_marketing 7 제거) |
| `status` 타입 | VARCHAR(20) | VARCHAR(20) | **ENUM** 5값 |
| `global_id` 타입 | VARCHAR(20) | **VARCHAR(50)** (history/log 통일) | (동일) |

- `Service-DB/` 폴더 v3 zip 동기화 (9.sql + 10.sql + Aurora_Create + execution + CHANGELOG + NEW_TABLES_GUIDE)
- platform `api_product_apply` INSERT 11컬럼 → **4컬럼** (`application_id, global_id, ls_user_id, product_id`), applicant 가져오는 14줄 블록 통째 제거, `data = request.get_json()` 도 제거
- admin `/api/admin/applications` SELECT 17컬럼 → **12컬럼** (제거 7 + reviewer_id/reviewed_at 추가)
- platform `/api/my-applications` SELECT 의 `a.product_code` → `p.product_code` (product_master JOIN 컬럼)

**6. `apply.html` 폼 단순화** (B 옵션)

- 마케팅 동의 체크박스(`row-mkt`) 행 + `cbMkt` JS 변수 + `payload.agree_marketing` 필드 모두 제거
- 약관 필수 2개(약관/개인정보 제3자) + "모두 동의" 통합 토글만 유지

**7. NEW_TABLES_GUIDE.md CVR 정의 사용자 정의로 수정** — 2 파일 (`ls/` + `Service-DB/`)

- CTR = `clicked / recommended` (노출 대비 클릭)
- **CVR = `purchased / clicked`** (클릭한 건 중 구매로 이어진 비율) — 사용자 정의, 마케팅 표준
- sample SQL 3 곳 모두 `NULLIF(SUM(clicked_flag='Y'), 0)` 패턴으로 갱신

**8. 화면 동작 검증 (USE_MOCK=true)**

- platform `:5000` + admin `:5001` BG 실행
- JWT 발급 → `apply.html` 받아서 `localStorage.setItem('ls_token', ...)` inline 주입 → Edge headless 560×1200 캡처 → 마케팅 행 제거 확인
- `POST /api/product/DEP-001/apply` mock 응답 `{application_id, status:'ok'}` 정상
- `GET /api/my-applications` 3건 mock 정상
- admin 4 페이지 회귀 (HTTP 200 × 4, 사이즈 동일 — `/api/admin/applications` SELECT 변경 무영향)

**9. 신청 시 Aurora 적재 흐름 점검** (운영 USE_MOCK=false 기준)

`POST /api/product/<code>/apply` 한 트랜잭션 안에서 3 테이블 적재:

| 단계 | 테이블 | 동작 |
|---|---|---|
| ① | `customer_product_application` | INSERT 4컬럼 (status default `RECEIVED`, created/updated 자동) |
| ② | `customer_recommend_history` | `purchased_flag='Y'` UPDATE (해당 추천 1건, 있을 때만) |
| ③ | `customer_dashboard_log` | INSERT (`page_type='DETAIL'`, `product_click='Y'`, `session_id=application_id`) |

- pymysql `autocommit=False` → 명시적 `db.commit()` 호출 시에만 영구화
- 예외 시 finally `db.close()` → 자동 rollback → 3 테이블 모두 미반영 (원자성 보장)

**10. 354계정 IaC 적용 점검**

| 결과 | 상태 |
|---|---|
| ECS Docker build + task 부팅 | ✅ 정상 (requirements 호환, app.py import OK) |
| ALB Health check `/` | ⚪ 변경 영향 없음 (이전 동작 그대로) |
| 21 stack IAM (analytics DDB + Kinesis + EMR + lifesync-onprem-customer-query) | ✅ 권한 반영됨 |
| `customer-profile-sync` invoke 권한 | ❌ 21 stack 미정의 — platform `_resolve_global_id` 가 죽은 코드라 즉시 영향 0 |
| **5개 종속 작업** (다음 표) | ⏳ 너 환경에서 실행 |

**11. ls-vpngw 제거 + lc-* → ls-* 표기 정정 + PrivateAPI 명세 파일 신설**

- PrivateAPI `app.py` `VM_HOSTS` dict 에서 `ls-vpngw` 행 제거 (테스트용 미사용)
- Lambda handler docstring `vm_id in (ls-db, ls-token, ls-api)` 로 갱신
- admin `mockup_data.py` 3 곳 정정 — `MOCKUP_LOCAL_LAB` 의 ls-vpngw 행 제거, `MOCKUP_DASH_CLOUD3` 의 `lc-db · lc-tokenz · lc-api` → `ls-db · ls-token · ls-api`, `MOCKUP_NET_TOPOLOGY.onprem` lines 동일 정정
- **`docs/private-api.md` 신규 (362줄)** — 9 섹션: 전체 21 라우트 / 신규 10 상세 (SQL/응답/용도) / 헬퍼 / 환경변수 / Lambda action ↔ endpoint 매핑 / pip 의존성 / 재배포 절차 + 검증 curl / 인증·보안 검토 / 변경이력
- 코드 잔재 grep 0건 (`ls-vpngw|lc-api|lc-db|lc-tokenz`)
- 과거 기록 문서(`local-test-troubleshooting.md`, `pii-encryption-guide.md` 등)는 history 보존을 위해 미정정

### 상태

| 항목 | 상태 |
|---|---|
| admin 화이트 샘플 4 페이지 재구성 | ✅ |
| 다크 토글 제거 + 화이트 단일 | ✅ |
| DB/리소스 호출 ↔ 스키마 정합 리포트 | ✅ |
| PrivateAPI `/internal/profile/list-all` + analytics_aggregator 페이지 루프 | ✅ |
| PrivateAPI DBUtils PooledDB | ✅ |
| PrivateAPI A옵션 9 엔드포인트 (count/단건/health) | ✅ |
| admin `_get_identities`/`PRIVATE_API_URL`/requests 제거 | ✅ |
| platform 인라인 DDL 제거 + INSERT 4컬럼화 | ✅ |
| Service-DB v3 동기화 (16→9 슬림) + admin SELECT 슬림화 + apply.html 폼 단순화 | ✅ |
| NEW_TABLES_GUIDE CVR 정의 수정 (2 파일) | ✅ |
| 화면 동작 검증 (apply 캡처 + mock 응답 + admin 4 페이지) | ✅ |
| 신청 흐름 Aurora 적재 명세 | ✅ |
| ls-vpngw 제거 + lc→ls 정정 + `docs/private-api.md` 명세 | ✅ |
| **Aurora 마이그레이션** (`bash Service-DB/service-db-execution.sh`) | ⏳ |
| **PrivateAPI 재배포** (DBUtils + 10 신규 엔드포인트) | ⏳ |
| **Lambda 재배포** (onprem_customer_query 18 action) | ⏳ |
| **23 stack 배포** (analytics_aggregator + DDB 2 + EventBridge DISABLED) | ⏳ |
| **platform `taskdef.json` REDIS_HOST env 추가** | ⏳ (ElastiCache endpoint 확정 필요) |
| **ECS 재배포** (admin/platform image build + service deploy) | ⏳ (CodePipeline) |
| **EventBridge cron ENABLE** (검증 후) | ⏳ |

### 메모

- **신규 명세 파일**: `docs/private-api.md` (21 라우트 + 환경변수 + 의존성 + 재배포 절차)
- **CVR 정의** (확정): `purchased / NULLIF(SUM(clicked_flag='Y'), 0) × 100` — 클릭한 건 중 구매로 이어진 비율
- **VM 3종** (`ls-db` / `ls-token` / `ls-api`), `ls-vpngw` 테스트용 제외
- `analytics_aggregator` 는 페이지 루프 (size=10000, max 200 페이지 안전 상한) + 메모이즈 — 1M profile fetch Lambda 6MB 제한 안전
- A 옵션 (Lambda 경유) 일관성으로 ECS subnet 에 VPN route 추가 불필요 — B (직접 HTTP) 전환은 운영 안정화 후 별도 검토
- platform `_resolve_global_id` (`PROFILE_SYNC_LAMBDA` 호출) 는 현재 호출처 없음 (죽은 코드) — register 흐름 부활 시 21 stack IAM 권한 추가 필요


## 2026-05-18 ④ — RRN 제거 / Lambda 동적 발견 / 354 인벤토리 / API 테스트 체크리스트

### 작업 요약

**1. PrivateAPI RRN 제거** (운영 미수집 결정)

| 파일 | 변경 |
|---|---|
| `onprem-prod-repo/.../app.py` | `RegisterRequest.rrn` 필드 삭제. `auth_register` INSERT 에서 `rrn_enc` 컬럼 미명시 (default NULL). `get_pii` 응답에서 `rrn` 키 + SELECT 컬럼 제외 |
| `lambda/onprem_customer_query/handler.py` | `register` action payload 에서 `rrn` 필드 삭제 |
| `lifesync360-platform/templates/register.html` | 주민등록번호 input 필드 + label + JS `payload.rrn` 제거 |

→ admin/platform 운영자도 RRN 받을 일 없음. `customer_pii_secure.rrn_enc` 컬럼은 DDL nullable 유지 (기존 데이터 보존).

**2. `_ping_lambda_metrics` 동적 발견 (옵션 C)**

`admin app.py:316` — 하드코딩 4종 → `boto3 lambda.list_functions paginator` + `lifesync-` prefix 필터로 자동 발견. 신규 Lambda 배포 시 코드 변경 없이 자동 포함. `LAMBDA_PREFIX_FILTER` env override 가능.

**3. 354 계정 AWS 인벤토리 스크립트 신설**

`docs/aws-inventory-scan.ps1` (95줄) — PowerShell 한 줄 실행으로 25개 카테고리 (Lambda/DDB/RDS/Redis/S3/ECS/ALB/EC2/VPC/SG/TGW/VPN/Kinesis/EMR/Glue/EventBridge/CFN/IAM/Secrets/SSM 등) JSON 파일 저장. `docs/aws-inventory-YYYY-MM-DD/` 디렉토리 생성.

**4. 354 계정 실 상태 진단** (2026-05-18 18:00 인벤토리)

| 영역 | 배포 |
|---|---|
| S3 (`lifesync-raw` 외 14 버킷) | ✅ |
| Lambda 5종 (`lifesync-wearable-stream` / `identity-enricher` / `recommendation-engine` / `batch-loader` / `ingest`) | ✅ |
| CFN 12 stack (01-network / 02-security / 06-s3 / 09-streaming / 10-data-processing / 12-ec2 / 15·17·18 cicd / 22-identity-enricher / GHA OIDC 3종) | ✅ |
| DynamoDB `lifesync_customer_result` | ❌ (테이블 없음 — 인벤토리 시점 기준) |
| DynamoDB `analytics_segment_daily` / `analytics_demographic_daily` | ❌ (23 stack 미배포) |
| Aurora MySQL | ❌ (`DBClusters: []`) |
| ElastiCache Redis | ❌ (`CacheClusters: []`) |
| ECS 클러스터 + ALB | ❌ (`clusterArns: []`, `LoadBalancers: []`) |
| Lambda `lifesync-onprem-customer-query` | ❌ (V4 P4 r43 명시지만 미배포) |
| analytics_aggregator / consent_snapshot_aggregator Lambda (③ 신규) | ❌ |

→ **데이터 계층 + 컨테이너 계층 + onprem-query Lambda 미배포**. admin USE_MOCK=false 운영 검증은 인프라 종속 작업 후 가능.

**5. admin app.py 의 `DYNAMO_TABLE` default 이름 불일치 발견**

| 위치 | 값 |
|---|---|
| admin `app.py:13` default | `lifesync-scores` (hyphen) |
| `taskdef.json` env | `lifesync-scores` |
| 실제 운영 DDB 이름 | `lifesync_customer_result` (underscore, results.csv 기준) |

→ env 명시 안 하면 `ResourceNotFoundException`. 운영 시 taskdef + admin default 둘 다 `lifesync_customer_result` 로 갱신 필요.

**6. `docs/api-test-after-iac.md` 신설 (278줄)**

IaC 재배포 후 admin USE_MOCK=false 단계별 API 검증 체크리스트:
- §0 354 계정 현재 상태 매트릭스
- §1 사전 확인 (자격증명 / 인벤토리)
- §2 admin env 박기 (run-local.ps1)
- §3 단계별 API 검증 6 step (S3/cloud → DDB → 분석 mart → Lambda → Aurora → ALB)
- §4 운영 종속 작업 8건
- §5 트러블슈팅 9건
- §6 `_call_onprem` graceful fallback 권장 패치
- §7 시나리오 한 줄 + §8 결과 보고 양식

**7. 로컬 테스트 가이드 (③ 라운드 연속)**

`docs/local-test-powershell.md` (380줄) — Windows PowerShell 기준 0~7 단계 절차 (자격증명 / venv / env / curl 검증 / VSCode 디버거 / SSM Port Forwarding / 종료 / 트러블슈팅 12건).

### 상태

| 항목 | 상태 |
|---|---|
| PrivateAPI RRN 제거 (RegisterRequest + INSERT + get_pii) | ✅ |
| Lambda onprem_customer_query register action payload 정리 | ✅ |
| register.html 주민번호 input 제거 | ✅ |
| admin `_list_lifesync_lambdas` + 동적 발견 `_ping_lambda_metrics` | ✅ |
| 354 계정 인벤토리 스크립트 (`docs/aws-inventory-scan.ps1`) | ✅ |
| 354 계정 인벤토리 실행 + 결과 분석 (`docs/aws-inventory-2026-05-18/`) | ✅ |
| `docs/api-test-after-iac.md` IaC 후 검증 체크리스트 | ✅ |
| `docs/local-test-powershell.md` 로컬 PowerShell 가이드 | ✅ |
| **`DYNAMO_TABLE` default 정합화** (admin default + taskdef → `lifesync_customer_result`) | ⏳ 결정 대기 |
| **`_call_onprem` graceful fallback 패치** (Lambda 미배포 시 500 방지) | ⏳ 결정 대기 |
| **Lambda `lifesync-onprem-customer-query` 354 배포** | ⏳ |
| **Aurora / ElastiCache / DDB `lifesync_customer_result` / 23 stack / 25 stack / 21 stack (ECS) IaC 재배포** | ⏳ (내일 사용자 환경 작업) |

### 메모

- **354 계정 현재 인프라 부족 영역**: 데이터 계층 (Aurora/Redis/DDB lifesync_*) + 컨테이너 (ECS/ALB) + onprem-query Lambda + 라운드 ②③ 신규 Lambda 2종
- **DDB 이름 불일치**: admin/taskdef default `lifesync-scores` vs 운영 `lifesync_customer_result` — env 명시로 우회 가능, 코드 default 정합화는 결정 대기
- **AWS CLI 한국어 인코딩**: PowerShell 5.1 CP949 에서 Lambda description 의 em dash(`—`) → `cp949 codec` 에러로 일부 JSON 파일 텍스트 손상. 데이터는 유효, PowerShell 7 또는 `chcp 65001` 권장
- **인벤토리 시점 DDB 결과 모순**: 첫 시도 `lifesync_customer_result + midasImageMetadata` → 인벤토리 시점 `midasImageMetadata` 만. 그 사이 테이블 삭제됐거나 region 차이 가능. 내일 재확인 필요


## 2026-05-18 ③ — 설계서 V4/V5 정합화 / DDB 이름 통일 / P1~P4 화면 명세 / API 응답 통일 / S3 동의 스냅샷 / admin Private EC2 결정

### 작업 요약

**1. DDB 분석 테이블명 설계서 정합 — `analytics_*_daily` 로 통일**

| 출처 | 이전 | 이후 |
|---|---|---|
| 23-analytics-batch.yaml | `analytics_segment_performance` / `analytics_demographic_summary` | `analytics_segment_daily` / `analytics_demographic_daily` |
| 21-lifesync-ecs IAM Resource ARN | 동일 | 동일 |
| admin taskdef env + admin app.py + analytics_aggregator handler + docs/today-tables GUIDE.md | 동일 | 동일 |

- 6 파일 sed 일괄 치환 + ast/JSON 검증 (잔재 0건, 새 이름 29건 매칭)
- 설계서 V4 P3 row 12-13 명시 (`analytics_segment_daily` / `analytics_demographic_daily`) 기준

**2. P1~P4 화면 명세 정합 (V5 4 페이지 vs 코드 4건 불일치 해소)**

| 페이지 | 작업 |
|---|---|
| **P1 KPI 8 → 9** | `MOCKUP_DASH_KPI8` → `MOCKUP_DASH_KPI` (Redis Cache 수 신규 추가, `54,820 keys` / `DBSIZE · 최대 60,000`). `grid-4` → `grid-3` (9 카드 3×3). 설계서 V5 순서 정합 (Row1 고객 / Row2 추천누적+Cache / Row3 CTR/CVR/AI상태) |
| **P2 정밀 → 정적 점수** | 라벨 "정밀 점수 (등급 가중)" → "정적 점수 (On-Prem customer_360_profile · 룰 기반)". 행동 82 → **금융 78** 교체 (설계서 V5 finance_score 정합). 자산 75 / 위험 12 유지 |
| **P4 Wearable 5 → 6** | `MOCKUP_NET_WEARABLE_5KPI` → `MOCKUP_NET_WEARABLE`. **이상 이벤트 (Alert)** 카드 신규 추가 (🚨 / `2` / `24h Alert · SNS`). `grid-5` → `grid-6` + `.grid-6` CSS 추가 |
| **P2 교차판매 UI 신규** | 좌측 컬럼 4 카드 → 5 카드 (가입상태 / 동의보유 / TopN / **교차판매** / 추가). `MOCKUP_CROSSSELL_LIST` 5건 (cross_sell_rule + product_master JOIN 정합) |

**3. 표기 정정 — `ls-vpngw` 제거 + `lc-*` → `ls-*` (코드 + mockup)**

- PrivateAPI `VM_HOSTS` dict 에서 ls-vpngw 행 제거 (테스트용 미사용) → 3 VM (`ls-db`/`ls-token`/`ls-api`)
- Lambda handler docstring `vm_id in (ls-db, ls-token, ls-api)` 로 갱신
- admin `mockup_data.py` 3 곳 정정 (MOCKUP_LOCAL_LAB, MOCKUP_DASH_CLOUD3, MOCKUP_NET_TOPOLOGY)
- 코드 잔재 grep 0건. 과거 기록 문서는 history 보존

**4. PrivateAPI 명세 파일 신설 — `docs/private-api.md` (362줄)**

- 21 라우트 전체 (기존 11 + 신규 10) 명세 + SQL/응답/용도 + 헬퍼 + 환경변수 + Lambda action 매핑 + pip 의존성 + 재배포 절차 + 보안 검토

**5. Admin API 명세 파일 신설 — `docs/admin-api.md` (640줄)**

- 설계서 V4 16 API + admin 내부 7 API = **23 API 정합 매트릭스**
- 각 API 응답 JSON 폼 + 화면 표시 위치 + UI 매핑
- 시연 vs 운영 응답 스키마 차이 식별 (3건)
- 화면 데이터 흐름 3 패턴 (SSR / AJAX / 하이브리드)
- 운영 전환 체크리스트 8건

**6. Admin Data Flow 파일 신설 — `docs/admin-data-flow.md` (391줄)**

- 7 저장소별 Write 흐름 (Aurora/On-Prem/DDB/Redis/S3/BigQuery/GCS)
- 23 API ↔ Read source ↔ Write 적재 흐름 매핑
- 적재 주체 (배치/실시간/사용자/외부) + 빈도
- 결정 사항 6건 / TODO 7건 / 응답 스키마 불일치 3건
- 운영 정합 체크리스트 (5 영역, 18 항목)

**7. 응답 스키마 통일 (시연 ↔ 운영 동일 구조)**

| API | 변경 |
|---|---|
| `/api/dashboard/summary` | `_stub_aurora_summary()` 재작성 — 운영도 9 카드 list 반환 (baseline MOCKUP_DASH_KPI + 실 호출 결과로 value 덮어쓰기, 부분 실패 mockup fallback). 호출 6개: `count_master_customer` / `count_users` / `count_users_consented` / Aurora COUNT 2 / CTR-CVR / DDB scan |
| `/api/s3/status` | 신규 `_s3_status_cards()` 헬퍼 — `_ping_s3_ingestion()` dict → 5 카드 list 매핑 (`MOCKUP_DASH_S3_5` baseline) |
| `/api/customer/profile/{gid}` | 신규 `_profile_full_mock()` 헬퍼 — `MOCK_USERS / MOCK_SCORES / MOCK_CONSENTS / MOCK_IDENTITIES` 를 PrivateAPI `get_all` 구조로 재구성. 라우트: 운영 분기를 `get_profile` + `_load_consent_from_s3` 합성으로 변경 |

- USE_MOCK=true 실호출 검증 — 3 API 모두 동일 응답 형태 ✅

**8. S3 동의 스냅샷 일배치 흐름 신설 (Q1=A S3 / Q2=A 일배치)** ⭐

설계서 V4 row 21-22 정합 — admin → 온프레 동의 직접 호출 0건 으로 전환.

| 구성요소 | 신규/변경 |
|---|---|
| PrivateAPI `/internal/consent/list-all?page=N&size=10000` | **신규** — user 페이지 단위, `JSON_ARRAYAGG(JSON_OBJECT(...))` 로 user 당 consents 8 도메인 묶음 |
| Lambda `onprem_customer_query` `list_consent_page` action | **신규** (action 18 → 19개) |
| Lambda `consent_snapshot_aggregator/handler.py` | **신규** — page 루프 (max 200 페이지 = 2M 안전 상한) + ThreadPoolExecutor PutObject 100 동시 + S3 `lifesync-raw/consent/dt=YYYY-MM-DD/{global_id}.json` |
| CFN `Aws_iac/Aws_iac/templates/25-consent-snapshot.yaml` | **신규** — Lambda + IAM Role (lambda:Invoke + s3:PutObject) + LogGroup + EventBridge cron `cron(0 18 * * ? *)` = **KST 03:00** (초기 DISABLED) |
| admin `_load_consent_from_s3()` 헬퍼 + 호출처 교체 | S3 `lifesync-raw/consent/dt=오늘/{gid}.json` GetObject + 어제 fallback. `user_detail` 라우트 + `api_customer_profile` 라우트 2 곳 교체 (`_call_onprem('get_consent'/'get_all')` 제거) |

**9. 설계서 V4 ↔ admin 23 API 정합 검증**

- V4 16 API 모두 admin 라우트 1:1 매핑 ✅
- admin 내부 보너스 7 API (`/api/admin/recommend-trend`, `/api/admin/segment-performance`, `/api/admin/demographic-summary`, `/api/admin/applications`, `/api/admin/local-lab-status` alias, `/api/kinesis/status`, `/api/emr/status`)
- 설계서 V4 P3 row 9 Feature 분포 출처 — Vertex AI/GCS vs 코드 BigQuery 불일치 (결정 미확정)
- 설계서 V4 P2 row 41 `applied_at` → v3 실제 컬럼 `created_at` (설계서 오기, 코드 정합)

**10. 354계정 IaC 적용 점검**

- ECS Docker build + task 부팅 OK (requirements 호환)
- ALB Health check `/` 변경 영향 없음
- 21 stack IAM: analytics DDB / Kinesis / EMR / lifesync-onprem-customer-query 권한 반영됨
- `customer-profile-sync` invoke 권한 미정의 (platform `_resolve_global_id` 죽은 코드라 즉시 영향 0)
- 런타임 5개 종속 작업 필요 (Aurora 마이그 / PrivateAPI 재배포 / Lambda 재배포 / 23 stack / REDIS_HOST env)

**11. P2 온프레 데이터 보안 점검 (외부 공유 시)**

| 등급 | 항목 | 처리 |
|---|---|---|
| 🟢 안전 (외부 공유 OK) | 그룹사 등록일 / 플랫폼 가입일 / 최근 로그인 / 회원상태 / 고객상태 | 5건 |
| 🟡 회색지대 | 인구통계 5축 / 동의 8 도메인 / 보유 계열사 / AI 등급 / AI 종합·건강 점수 / NBA | 시연 mockup 만 ✅, 실데이터 신중 |
| 🔴 위험 | 이름 / 연락처 / 이메일 / 주소 / 주민번호 / 금융·자산·위험 점수 / 실 global_id | 마스킹 / 권한 분리 / 외부 공유 금지 |

- PrivateAPI `/internal/pii/{global_id}` 응답 평문 5필드 (RRN 포함) — admin 운영자도 평문 보면 보안 사고 가능 → 마스킹 위치 결정 필요 (옵션 A: PrivateAPI 단 마스킹 / B: admin 단 / C: 평문 유지 — 사용자 결정 대기)
- 외부 공유 안전 영역은 **가입/상태 정보 박스 5건만**

**12. Admin 운영 인스턴스 결정 — Private Subnet EC2 1대 (ECS 공개 admin X)**

- ECS Fargate + ALB 공개 admin 폐기 결정
- Private Subnet EC2 단일 운영, VPN/SSM Session Manager 접근
- 같은 admin 이미지 그대로 (ADMIN_LEVEL env 분기 불필요)
- platform `/settings/consent` 보강 — 사용자 본인 동의 상태 표시 + 갱신 (후속 라운드)
- 인프라 변경 영역: 21 stack admin ECS 폐기, 24 stack EC2 신설, CI/CD admin pipeline 변경 (ECR push + SSM run-command)
- 인프라 작업은 별도 라운드 — 이번 라운드는 코드/문서/API 정합만

### 상태

| 항목 | 상태 |
|---|---|
| DDB 테이블명 설계서 정합 (`analytics_*_daily`) 6 파일 | ✅ |
| P1 KPI 8 → 9 (Redis Cache 수) | ✅ |
| P2 정밀 → 정적 점수 (행동 → 금융 + 출처 명시) | ✅ |
| P4 Wearable 5 → 6 (이상 이벤트) | ✅ |
| P2 교차판매 추천 UI 신규 | ✅ |
| ls-vpngw 제거 + lc-* → ls-* 정정 | ✅ |
| `docs/private-api.md` 신설 (362줄) | ✅ |
| `docs/admin-api.md` 신설 (640줄) | ✅ |
| `docs/admin-data-flow.md` 신설 (391줄) | ✅ |
| 응답 스키마 통일 (3 API 시연↔운영) | ✅ |
| S3 동의 스냅샷 일배치 — PrivateAPI / Lambda action / consent_snapshot_aggregator / 25 stack / admin S3 헬퍼 | ✅ (코드/IaC 완료, 배포 대기) |
| 설계서 V4 ↔ admin 23 API 정합 검증 | ✅ |
| 354계정 IaC 적용 점검 리포트 | ✅ (분석) |
| P2 온프레 데이터 보안 등급 식별 | ✅ (분석) |
| Admin 인스턴스 = Private EC2 1대 결정 | ✅ |
| **Aurora 마이그레이션 v3** (Service-DB execution) | ⏳ |
| **23/25 stack 배포** | ⏳ |
| **PrivateAPI 재배포** (22 endpoints + DBUtils) | ⏳ |
| **Lambda 재배포** (onprem 19 actions + consent_snapshot 신규) | ⏳ |
| **24 stack EC2 신설** (admin Private) | ⏳ |
| **21 stack admin ECS 폐기** + CI/CD 변경 | ⏳ |
| **platform `/settings/consent`** 사용자 본인 동의 화면 보강 | ⏳ |
| **PrivateAPI `/internal/pii` 마스킹 + RRN 별도 권한** | ⏳ (결정 대기) |
| EventBridge cron ENABLE (23 + 25 두 stack) | ⏳ (검증 후) |

### 메모

- **신규 문서 3종**: `docs/private-api.md` / `docs/admin-api.md` / `docs/admin-data-flow.md` — 23 API + 21 PrivateAPI 라우트 명세 + 데이터 흐름
- **신규 Lambda 1종 + CFN 1종**: `lambda/consent_snapshot_aggregator/` + `Aws_iac/Aws_iac/templates/25-consent-snapshot.yaml`
- **PrivateAPI 라우트 21 → 22개**: `/internal/consent/list-all` 신규
- **Lambda `onprem_customer_query` action 18 → 19개**: `list_consent_page` 신규
- **응답 스키마 통일 효과**: 시연 검증된 화면이 USE_MOCK=false 운영 전환 후에도 동일 작동
- **count_users_consented 정의**: 사용자 결정 **B 유지** (consent JOIN). `users.consent_completed` 컬럼은 운영에서 sync 코드 없어 default 'N' 고정 — 설계서 SQL 옵션 A 는 무용지물 상태
- **admin 운영 환경**: Private Subnet EC2 단일, ECS 공개 admin 폐기 결정 — 인프라 변경 다음 라운드

---

## 2026-05-19 ④ — admin API 21/21 검증 완료 (100%) + PGA/24-stack IaC + Lambda/DDB 배포

### 작업 요약

**1. Aws_iac 5.zip 신설 — CFN 신규 2 stack**

| 파일 | 역할 |
|---|---|
| `templates/01c-pga-hybrid.yaml` | Private Google Access via VPN/TGW (Route 53 private zone + admin subnet RT → `199.36.153.0/24` TGW) |
| `templates/24-admin-windows-ec2.yaml` | Windows Server 2022 admin EC2 (Private Subnet, SSM Fleet Manager RDP, UserData Chocolatey + Python 3.11 + Git + Chrome) |
| `scripts/infra/deploy-01c-pga-only.sh` | 01c 단독 배포 |
| `scripts/infra/deploy-24-admin-windows-only.sh` | 24 단독 배포 |
| `CHANGES-2026-05-19.md` 2차 보강 | 신규 stack 2종 변경 이력 |

**2. PGA 셋업 가이드 3 파일 (docs/)**

| 파일 | 역할 |
|---|---|
| `docs/gcp-pga-1-request-to-gcp-team.md` | GCP 담당자 작업 4가지 (Cloud Router 광고 / Cloud DNS / 서비스계정 / 키 JSON) — 그대로 전달 |
| `docs/gcp-pga-2-aws-setup.ps1` | AWS Route 53 private zone + admin subnet RT 라우트 PowerShell |
| `docs/gcp-pga-3-admin-env.ps1` | admin env 박기 + GCP SDK end-to-end 검증 (bigquery / aiplatform / monitoring) |

**3. admin API 21/21 검증 — `docs/api-test-after-iac.md`**

상단에 21 라우트 매트릭스 추가 + Step 1~5 별 표 갱신 + 10번 섹션 (재현 가능 명령 로그) 신설.

| 카테고리 | 라우트 수 |
|---|---|
| ✅ V (실 데이터) | 13 (Step 1: 8 / Step 2: 2 / Step 3: 3) |
| ⚠️ V (라우트 동작) | 7 (Step 4: 2 / Step 5: 5) |
| ⚠️ data 0건 | 1 (`/api/emr/status`) |
| ❌ 미배포 | 0 |
| **합계** | **21 / 21 = 100%** |

**4. AWS 신규 리소스 생성**

| 리소스 | 상태 |
|---|---|
| DDB seed — `lifesync_customer_result` (G000000001~3) | 3건 PutItem |
| DDB 신규 — `analytics_segment_daily` + seed 5건 | gender#M/F, age_band#20s/30s/40s |
| DDB 신규 — `analytics_demographic_daily` + seed 5건 | age_band, gender, region |
| Aurora — `lifesync360` DB 생성 | CREATE DATABASE (테이블 0) |
| CFN — `lifesync-dev-24-admin-windows-ec2` | CREATE_COMPLETE (i-0a839dc320eb854d9, 10.0.10.204) |
| Lambda — `lifesync-onprem-customer-query` | python3.11, Handler `handler.handler`, IAM basic execution |

**5. admin 코드 변경 (최소)**

| 위치 | 변경 |
|---|---|
| `admin-platform/app.py:1452-1471` `api_customer_ai_result` | DDB composite key (`global_id`+`update_time`) 발견 → `get_item` → `query(ScanIndexForward=False, Limit=1)` |
| `admin-platform/mockup_data.py:377` `MOCKUP_DASH_KPI` | KPI8 → KPI9 + Redis Cache 카드 추가 (ImportError 해소) |
| `admin-platform/mockup_data.py:636` `MOCKUP_NET_WEARABLE` | 5KPI → 6KPI (이상 이벤트 추가) |

**6. 발견된 정합 이슈**

| 이슈 | 위치 | 후속 |
|---|---|---|
| DDB lifesync_customer_result composite key 미지원 | admin app.py | ✅ 패치 완료 |
| analytics 테이블 SK 이름 — admin code (segment_key) vs admin-data-flow.md (demographic_key) | admin-data-flow.md 1.3 | admin-data-flow.md 갱신 필요 |
| `/api/admin/applications` 응답 폼 불일치 (`{"error":...}` vs `[]`) | admin app.py | 별도 라운드 — 응답 폼 통일 |
| Aurora Secret `/lifesync/dev/db/master` value 미박힘 | 02-security CFN | Secret put-secret-value 또는 GenerateSecretString |
| Lambda VPC config 없음 — On-Prem 접근 불가 | lifesync-onprem-customer-query | 별도 라운드 — VPC + SG + VPN UP |
| SG description 한글 — AWS EC2 비허용 | 24 stack | 영문 변환 (24-stack 적용 완료) |

### 상태

| 항목 | 상태 |
|---|---|
| Aws_iac 5.zip 생성 (01c PGA + 24 admin Windows EC2 CFN) | ✅ |
| docs/gcp-pga-1~3 (PGA 셋업 가이드 3 파일) | ✅ |
| api-test-after-iac.md 상단 21 라우트 매트릭스 + 검증 로그 | ✅ |
| DDB seed 박기 (lifesync_customer_result 3 + analytics 2 테이블 10) | ✅ |
| admin app.py composite key query 패치 | ✅ |
| Aurora SSM tunnel + `CREATE DATABASE lifesync360` | ✅ |
| 24-stack Windows EC2 CFN deploy | ✅ |
| Lambda `lifesync-onprem-customer-query` 배포 | ✅ |
| admin API 21 / 21 V 박음 (100%) | ✅ ⭐ |
| **23 stack 정식** (analytics_aggregator Lambda + EventBridge cron) | ⏳ |
| **Service-DB 마이그레이션** (`Service-DB/run-aurora-migration.py` Python pymysql 변환 신설 + 실행) — Step 5 ⚠️ V 4개 ✅ V 승격 + Step 3 recommend-trend 승격 | ✅ |
| **Lambda VPC config + On-Prem VPN UP + 3 VM** | ⏳ |
| **GCP 측 셋업** (Cloud Router 광고 + Cloud DNS + 서비스계정) | ⏳ |
| **`/api/admin/applications` 응답 폼 정합** | ⏳ |
| **admin-data-flow.md SK 이름 정합** (demographic_key → segment_key) | ⏳ |
| **Aurora Secret 자동 set** (02-security CFN GenerateSecretString) | ⏳ |

### 메모

- **검증 매트릭스 위치**: `docs/api-test-after-iac.md` 상단 + Section 10 (재현 가능 명령 로그) — 21 라우트 + 검증 명령 + 결과 핵심
- **시연 admin 모드**: `USE_MOCK=true` 로 5001 띄움 (PID 변동) — GCP 담당자 시연 시 그대로 사용
- **24-stack Windows EC2 접속**: AWS Console → Systems Manager → Fleet Manager → `lifesync-dev-admin-ec2` → Connect with Remote Desktop
- **Lambda Handler 함수명**: `handler.handler` (lambda_handler 아님 — `handler.py` 의 `def handler(event, context)`)
- **DDB composite key 의미**: 운영 시 Cloud Run lifesync-result-bridge 가 일배치마다 새 update_time 으로 PutItem → 시계열 누적. admin 은 항상 최신 1건 (query Limit=1)
- **analytics 테이블 SK 이름 통일**: admin code 가 두 테이블 다 `segment_key` 사용 → DDB schema 도 동일 박음 (admin-data-flow.md 의 `demographic_key` 표기 갱신 필요)
- **온프레미스 호출 한계**: VPC config + VPN UP + VirtualBox VM 3대 (ls-db / ls-token / ls-api) 모두 필요. 현재 graceful fail 응답 폼만 검증 (⚠️ V)
- **다음 라운드 우선순위 후보**:
  1. Service-DB 마이그레이션 (24-stack 안에서) — Step 5 ⚠️ V 5개 → ✅ V 5개 승격
  2. 23 stack 정식 배포 (analytics_aggregator Lambda + EventBridge) — Step 3 정식
  3. GCP 측 셋업 (담당자 의존) — Step 1 cloud/status + Step 2 vertex_metrics
  4. Lambda VPC config + On-Prem 연결 — Step 4 정식

---

## 라운드 — 2026-05-20 admin 실 클라우드 전환 (USE_MOCK=false 시연)

### 배경
24-admin-windows-ec2 위 admin app 을 실 AWS 데이터로 시연. 사용자 요청: mock 다 빼고 실 데이터, wearable 1s + 폴링 30s, 첫 진입 시 mock 안 보이고 즉시 갱신.

### 인프라 변경 (✅)

| 항목 | 내용 |
|---|---|
| Lambda VPC config | `lifesync-onprem-customer-query` 가 management VPC subnet-05ee715cfbb583854 매핑 + AWSLambdaVPCAccessExecutionRole + 신규 SG (outbound 80/443/8000-8080). TGW → VPN → 172.16.1.73 경로 OK |
| Lambda urlopen timeout | `handler.py:_api_get/_api_post` 8 → 25 — count_master_customer (91만건 COUNT) 시간 흡수 |
| VPN tunnel | 한쪽 UP (13.125.17.139), 한쪽 DOWN (52.78.117.43) — 운영 정상 |
| admin EC2 SG inbound | Aurora 3306 + Redis 6379 + VPC endpoint 443 매핑 |
| admin EC2 IAM | ReadOnlyAccess + Lambda invoke (lifesync-*) + S3 PutObject (admin-screens/admin-patch) + CloudWatch |
| EC2 machine env | USE_MOCK=false, ONPREM_QUERY_LAMBDA, AURORA_HOST, DB_USER/PASS/NAME, DYNAMO_TABLE, LIFESYNC_RAW_S3_BUCKET, GLUE_JOB_PHYSICAL_NAME, PYTHONIOENCODING=utf-8 |

### admin 코드 변경 (✅, S3 push + EC2 sync 까지 완료)

| 파일 | 변경 |
|---|---|
| `app.py:116` | boto3 Config `connect_timeout=3, read_timeout=20` (2/3 → 3/20) |
| `app.py:179` `_ping_cloud_status` | S3 list_buckets → **lifesync prefix 필터링** (14 → 6 buckets) |
| `app.py:218` `_ping_s3_ingestion` | paginator 전체 순회 → **도메인 prefix 8개 × MaxKeys=1000 + CloudWatch NumberOfObjects metric** (timeout 해소) |
| `app.py:504` `_ping_vpn` | bgp_asn XML 누수 → **describe_customer_gateways 별도 호출 + State='deleted' 제외** |
| `app.py:1018` `dashboard()` | **USE_MOCK 분기 추가** — SSR 단 mock 안 보이게 `value='-' state='-' note='-'` 초기화 |
| `app.py:1227` `_stub_aurora_summary` | KPI 1~3 _call_onprem count_* 채움 + KPI 9 DDB scan update_time |
| `app.py:1371` `_cloud3_from_aws` | AWS 6 서비스 details 배열 + **On-Prem VM 단위 통합** (ls-db (MySQL) / ls-token (Tokenization) / ls-api (PrivateAPI) 3 row, ip:port 중복 제거) |
| `app.py:1419` `_uploads_from_s3` | paginator → **도메인 prefix × MaxKeys=50** |
| `wearable_engine.py` | `start_loop(interval=1.0)` (3 → 1) |
| `templates/dashboard.html` | cloud-details div + JS apply replace, 폴링 30000ms (60→30) |
| `templates/ops.html` | 인프라 토폴로지 섹션 제거, 폴링 30000ms |
| `templates/users.html` | 검색 input `placeholder="G000000924" maxlength="10" pattern="[GC][0-9]{9}"` + hint 갱신 |
| `static/css/admin.css` | `.cloud-details`, `.cloud-detail-{up,down,warn,err}` 추가 |

### admin 코드 변경 (⏳, S3 push 완료 but EC2 sync 안 됨)

| 파일 | 변경 |
|---|---|
| `app.py:1031` `users()` route | onprem `get_profile` + `get_pii` + `get_consent` 합산 → template 호환 키 (grade/phone_masked/gender/age_band/region/income/asset/ai_total_score/ai_health_score/status_rows/owned_badges/consent_badges) 통일. 현재 EC2 의 app.py 는 이전 변경 (cloud3 VM merge + S3 lifesync filter) 까지만 반영 — SSM Read-S3Object + Start-Process 의 stream hang 으로 cancel 됨 |

### 검증 결과 (✅)

| KPI/Endpoint | 값 / 응답 시간 |
|---|---|
| KPI 1 통합 고객 수 | **919,502** (master_customer) |
| KPI 2 플랫폼 가입자 | **294,277** (users) |
| KPI 3 분석 대상 | **58,624** (users JOIN consent) |
| Cloud3 AWS | 6/6 정상 (Aurora/DDB/ElastiCache/ECS/ALB/S3 6 buckets) |
| Cloud3 On-Prem | 2/3 정상 (ls-db UP / ls-token DOWN [의도] / ls-api UP) |
| /api/dashboard/uploads | 717ms (이전 timeout) |
| /api/s3/status | 765ms — 157,755 / 275 / 1,000 |
| /api/network/vpn | 482ms — bgp_asn=65000, peer=1.231.165.73, UP/DOWN |
| /api/admin/local-lab-status | 3.2s — mysql pass(11 tables), tokenization fail |

### 미반영 / 별도 작업 필요

| 항목 | 원인 | 조치 |
|---|---|---|
| **users() route EC2 sync** | SSM Read-S3Object hang 으로 download 안 됨 — S3 만 최신 | SSM 명령 분리 (download 단독 → restart 단독) 후 재시도 |
| **동의 고객만 검색 차단** (사용자 추가 요청) | users() route 에 분석 동의 여부 게이트 미구현 | get_consent 응답 확인 후 미동의 시 profile dict 비공개 + status_rows '미동의' 표시 |
| KPI 4 AI 추천 상태 | DDB `lifesync_customer_result.update_time` 미적재 | analytics_aggregator Lambda 배포 |
| KPI 5~8 추천이력/CTR/CVR | Aurora `customer_recommend_history` / `customer_dashboard_log` 미적재 | 23-analytics-batch stack 배포 + 백필 |
| KPI 9 Redis Cache 수 | `REDIS_HOST` env 누락 | ElastiCache `lif-re-1sqfju15n8thy` endpoint 확인 + env 추가 |
| /api/admin/recommend-trend / segment-performance | Aurora customer_recommend_daily / DDB analytics_segment_daily 미배포 | 23-analytics-batch stack |
| /api/kinesis/status | **Kinesis stream 자체 미배포** (account 354 list-streams 빈) | 21-kinesis stack 배포 |
| /api/vm/group | EC2 `Project=lifesync` tag 부착 인스턴스 없음 | EC2 tagging 또는 group-app VM 배포 |
| GCP 자격증명 부재 | cloud3 GCP 카드 '-' | 별도 GCP 셋업 작업 |

### 트러블슈팅 메모

- **SSM Run Command sub-process 가 machine env 못 받음**: machine env 설정해도 SSM script 의 새 process 는 system env snapshot 못 reload. 해결 — `$env:NAME='value'` 를 SSM script 안에서 명시 설정 후 Start-Process (child 가 부모 env 상속)
- **SSM `[System.Diagnostics.Process]::Start` + RedirectStandardOutput=$true hang**: reader 없어 stdout buffer 막힘. 해결 — `Start-Process -RedirectStandardOutput <file>` 옵션 (file 로 redirect)
- **SSM Read-S3Object + Start-Process 한 줄 hang**: 원인 미상, command timeout. 해결 — download 단독 SSM 명령 → 검증 → restart 단독 SSM 명령 (분리)
- **Lambda urlopen timeout=8s 짧음**: master_customer COUNT(*) 91만건이 8s 초과. urlopen 25s + admin boto3 read_timeout 20s 로 매칭
- **`_call_onprem` 의 `ONPREM_QUERY_LAMBDA` env**: app.py 는 `ONPREM_QUERY_LAMBDA` (`ONPREM_LAMBDA_NAME` 아님). 빈 string 이면 `_call_onprem` 이 `{}` 반환 → mock fallback. 환경변수 이름 매칭 주의
- **VPN tunnel 양쪽 DOWN 시 Lambda 호출 실패**: AWS console VPN 상태 확인 + onprem strongSwan/IPsec service restart. 한쪽만 UP 이어도 routing OK
- **AWS CLI cp949 encoding 에러**: `PYTHONIOENCODING=utf-8` 환경변수 + boto3 직접 호출 우회
- **S3 lifesync-raw paginator 30s+**: 157,755 객체 paginator 전체 순회 시간 초과 → 도메인 prefix MaxKeys=1000 합산 + CloudWatch NumberOfObjects metric 활용

### 다음 세션 재개 흐름

1. SSM 으로 S3 → EC2 app.py download 강제 적용 (단독 명령으로)
   ```bash
   aws ssm send-command --region ap-northeast-2 --instance-ids i-09857764d0822ba3c \
     --document-name AWS-RunPowerShellScript \
     --parameters 'commands=["Read-S3Object -BucketName lifesync-artifact-bucket -Key admin-patch/app.py -File C:\\admin-platform\\app.py -Region ap-northeast-2 | Out-Null; (Get-Item C:\\admin-platform\\app.py).Length; (Select-String C:\\admin-platform\\app.py -Pattern domain_label,phone_masked,get_pii | Measure-Object).Count"]'
   ```
   결과: size > 76506 + matches > 0 — OK

2. admin restart (별도 SSM 명령)
   ```bash
   aws ssm send-command --region ap-northeast-2 --instance-ids i-09857764d0822ba3c \
     --document-name AWS-RunPowerShellScript \
     --parameters 'commands=["$env:USE_MOCK=\"false\"; $env:ONPREM_QUERY_LAMBDA=\"lifesync-onprem-customer-query\"; ... ; Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 2; Start-Process -WindowStyle Hidden -FilePath C:\\Python311\\python.exe -ArgumentList C:\\admin-platform\\app.py -WorkingDirectory C:\\admin-platform -RedirectStandardOutput C:\\admin-platform\\admin.log -RedirectStandardError C:\\admin-platform\\admin.err"]'
   ```

3. 동의 고객만 검색 차단 로직 추가 후 push + sync
4. REDIS_HOST env 추가 (KPI 9)
5. 23-analytics-batch / 21-kinesis stack 배포 (KPI 4~8 / Kinesis)

---

## 세션 2026-05-22

### 작업 목표
Admin 플랫폼 4개 섹션 미표시 수정, DataVPC 상태 수정, lifesync360 실 데이터 테스트, IaC 354 계정 정리, 732 계정 리소스 전체 삭제.

---

### 1. Admin 플랫폼 — AI 4개 섹션 + DataVPC 수정

**증상**
- AI 페이지: 일별 추천 성과 추이(7일), 세그먼트 & 분포 분석, BigQuery 분석, AI 모델 평가 4개 섹션 미렌더링
- Ops 페이지 DataVPC 카드: Kinesis 상태만 표시, S3/Glue/EMR 상태 비어있음

**수정 내용**

| 파일 | 변경 |
|------|------|
| `admin-platform/app.py` | `/api/datavpc/status` 엔드포인트 신규 추가 (S3 head_bucket + Kinesis + Glue last_run + EMR 통합 반환) |
| `admin-platform/templates/ops.html` | DataVPC JS: `/api/kinesis/status` → `/api/datavpc/status` 교체, S3·Glue·EMR 행 렌더링 추가 |
| `admin-platform/templates/ai.html` | 4개 섹션 SSE + 폴링 연동 수정 |
| `admin-platform/templates/_chart_ai_trend.j2` | 7일 CTR/CVR 추이 차트 수정 |
| `admin-platform/static/js/auto-refresh.js` | SSE 구독 안정화 |
| `admin-platform/mockup_data.py` | 미사용 함수 제거 |
| `admin-platform/start-admin.ps1` | USE_MOCK 환경변수 제거 |

**결과 (스크린샷 확인)**
- AI 4개 섹션 정상 렌더링 (CTR 28.3% / CVR 15.1% / 정밀도 0.61 / F1 20)
- DataVPC: S3=EXISTS(녹색) / Kinesis=ACTIVE(녹색) / Glue=NO_RUNS(회색) / EMR=NONE(회색)

---

### 2. lifesync360 플랫폼 — 온프레미스 시뮬레이터 실 데이터 테스트

**배포 방식**: 온프레미스 시뮬레이터 EC2(`i-0c36936f6ca95f664`, Linux) → `/opt/ls360/`에 앱 직접 배포

**배포 절차**
1. 로컬에서 `lifesync360-platform/` zip → S3 업로드
2. SSM으로 EC2에서 S3 download + `fix_extract.py`로 Windows 경로 처리 후 압축 해제
3. `/opt/ls360_venv/` 가상환경 생성 + 의존성 설치 (`flask flask-cors pyjwt boto3 pymysql redis playwright`)
4. `start_ls360.sh`로 앱 기동 (Secrets Manager에서 DB/Redis 정보 로드)

**도중 해결한 권한/네트워크 이슈** → 트러블슈팅 문서 참조

**테스트 결과**

| 항목 | 결과 |
|------|------|
| 로그인 | `user1@lifesync.com / Test1234!` → `ls_user_id=U00000001` ✅ |
| DDB 조회 | `grade=A, score=87.0, vip_prob=0.82, health=85.0` ✅ |
| 추천 API (MISS) | Aurora에서 10개 상품 반환 ✅ |
| Redis 캐시 기록 | `rec:G000000001` = [997, 1097, 993, 999, 1093, ...] (10개) ✅ |
| 추천 API (HIT) | 2차 호출 시 Redis 캐시 사용 ✅ |

**스크린샷 저장** (`screenshots/`)

| 파일 | 화면 |
|------|------|
| `ls360_01_login.png` | 로그인 화면 |
| `ls360_02_home.png` | 홈 — 나를 위한 추천 10건 (grade A, score 87) |
| `ls360_03_consent.png` | 동의 화면 — LS 8개 계열사 동의 항목 |
| `ls360_04_settings.png` | 설정 화면 |
| `ls360_05_myapps_api.png` | 내 신청 내역 API 응답 |

---

### 3. IaC / 코드 354 계정 기준 정리

| 파일 | 변경 내용 |
|------|----------|
| `Aws_iac/Aws_iac/params/data.env` | S3 버킷명 `lifesync-732-*` → `lifesync-354-*` |
| `admin-platform/app.py` | `/api/datavpc/status` `LIFESYNC_RAW_S3_BUCKET` 기본값 → `lifesync-354-raw` |
| `start_ls360.sh` | `REDIS_HOST` 하드코딩(732 전용 엔드포인트) → Secrets Manager `/lifesync/dev/db/master`에서 읽도록 변경 |
| `admin-platform/taskdef.json` | 이미 354 ARN (유지) |
| `lifesync360-platform/taskdef.json` | 이미 354 ARN (유지) |
| CloudFormation 템플릿 | 계정 무관 (Ref/Fn::GetAtt) — 변경 불필요 |

**354 계정 배포 준비 상태**: ECS 배포 기준으로 코드/IaC 준비 완료. 스택 올리면 신규 엔드포인트가 Secrets Manager → taskdef.json 경로로 자동 주입됨.

---

### 4. Git Push

| 커밋 해시 | 내용 |
|-----------|------|
| `1da3b4e` | feat(admin): DataVPC 통합 API + AI 4개 섹션 + ops.html + 354 기준 정리 |
| `0d391b2` | fix(ls360): start_ls360.sh Redis 엔드포인트 Secrets Manager로 이관 |

---

### 5. 732 계정 AWS 리소스 전체 삭제

**CloudFormation 스택 14개 전부 DELETE_COMPLETE**

삭제 순서 (역의존성):
`27-onprem-simulator` → `26-onprem-query` → `24-admin-windows-ec2` → `22-identity-enricher` → `15-cicd` → `12-ec2` → `11-observability` → `10-data-processing` → `09-streaming-api-lambda` → `08-database` → `07-ecr` → `06-s3` → `02-security` → `01-network`

**별도 추가 리소스 정리**

| 리소스 | 조치 |
|--------|------|
| IAM 인라인 정책 6개 (admin EC2, simulator EC2) | 스택 삭제 전 수동 제거 |
| SG 인바운드 규칙 4개 (Aurora, Redis에 추가한 것) | 수동 제거 후 스택 삭제 |
| S3 버킷 내용 (raw 8개, artifact 50개) | 비운 후 CFN 삭제 |
| Secrets Manager 2개 (`lifesync/ansible-vault`, `lifesync/onprem-db`) | 즉시 삭제 |
| DynamoDB `lifesync_customer_result` | 수동 삭제 (DeletionPolicy: Retain이었던 것) |
| Lambda, ECR, CodeCommit | 스택 삭제로 함께 제거됨 |

---

## 세션 2026-05-23 — AI 차트 버그 수정 + 설계서 업데이트

### 1. `_ai_age_perf_2step()` 완전 재작성

**증상**: `/api/ai/chart/age` 0.3s 만에 빈 결과 반환.

**원인 추적**:
1차 → `_call_onprem('list_by_age_band')` 호출, `_ROUTES` 딕셔너리에 없어 즉시 `{}` 반환
2차 → 온프레미스 API에 `list_by_age_band` 엔드포인트 자체 없음 (openapi.json 확인)
3차 → Lambda 경로 막힘: `ONPREM_QUERY_LAMBDA` 환경변수 미설정
4차 → DDB fallback: `analytics_segment_performance` 0행 → 빈 결과

**수정**: `_ai_age_perf_2step()` 완전 재작성 (`admin-platform/app.py` 로컬 + EC2 양쪽 SSM base64 패치 적용)
- OLD: `_call_onprem('list_by_age_band')`
- NEW: 온프레미스 `/internal/profile/list-all?size=500&after=<cursor>` 직접 페이지네이션 (cursor: `next_after`, max 10 pages, timeout=2s/call)
- 실패 시 DDB `analytics_segment_performance` `age_band#` fallback 유지

### 2. 설계서 V5_3 업데이트

`관리자_대시보드_설계서_V5_3.xlsx` AI 추천 시트 수정:
- `카테고리별 도넛` 테이블/객체: `category_master` → `customer_recommend_history JOIN product_master JOIN category_master cat`
- `연령대별 추천 성과` 데이터 소스: `On-Prem Lambda (1순위)` → `On-Prem /internal/profile/list-all 직접 HTTP (1순위)`
- 페이지네이션 상세 (cursor, size, max pages, timeout) 반영
- API 테이블 누락 4개 추가: `GET /api/ai/chart/{trend|donut|age|histogram}`

### 3. 인프라/리소스 현황 파악

| 리소스 | 상태 | 영향 |
|--------|------|------|
| Aurora `auroracluster-db-writer` | deleting (삭제 중) | kpi4 CTR/CVR, trend, donut, TOP10 모두 빈 결과 |
| 온프레미스 VM | 종료됨 | 연령대별 차트 DDB fallback → 0행이라 빈 차트 |
| DynamoDB `lifesync_customer_result` | 정상 (58,637 items) | histogram, 배치 고객 수 정상 |
| `analytics_segment_performance` DDB | 0행 | age_band fallback 데이터 없음 |
| `customer-profile-sync` Lambda | 미존재 (ResourceNotFoundException) | - |

---

## 세션 2026-05-24~25 — Audit + 폴더 분리 + 계정 전환 환경

### 1. 코드/설계서 Audit (클라우드 미사용 상태에서)

**검증 항목**:
- admin-platform/app.py 변경분 (`_ai_age_perf_2step` 등)
- mockup_data.py 죽은 코드 제거 확인 (7개 — 모두 미검출 ✅)
- `/api/vm/management` 라우트 추가 (line 2237) ✅
- terms.md 신규 4페이지 용어집 ✅
- IaC 3종 (01-network admin subnet 10.4.20.0/24, 24-admin-windows-ec2 CidrIp 전환, 08-database SqlOps Condition) ✅
- 설계서 V5_3 AI 시트 5개 항목 ✅

**Audit에서 발견된 버그**:
- `_ai_age_perf_2step()` line 2006 CVR 분모 불일치: `pur*100/clk` → 다른 곳은 모두 `pur*100/rec` (분모=recommended). 즉 연령대별 차트만 다른 의미의 CVR.

### 2. CVR 공식 버그 수정

`admin-platform/app.py:2006` CVR 공식을 다른 차트 + 설계서 + terms.md와 통일:
- OLD: `'cvr': round(pur * 100.0 / clk, 1) if clk else 0`
- NEW: `'cvr': round(pur * 100.0 / rec, 1) if rec else 0`

→ CTR/CVR 모두 분모=recommended로 통일, 동일 base 비교 가능.

### 3. IaC 변경/추가 정리 문서 작성

`docs/iac-handoff-2026-05-24.md` 신규 — IaC 담당자 전달용:
- 5개 modified 파일 (commit 후 배포 필요): 01b, 08, 08b, 19-cicd-service-platform, 21
- 3개 untracked 신규 적용 필요: 01-network, 24-admin-windows-ec2, 27-onprem-simulator
- 권한 이슈 IaC 미반영 5건 (수동 해결 → 재배포 시 깨짐):
  - #10 ECS ExecutionRole `kms:Decrypt` (Condition: ViaService)
  - #11 VPC KMS Interface Endpoint
  - #22 OnpremSimRole `lambda:InvokeFunction`
  - #24 OnpremSimRole DynamoDB Query/GetItem/Scan
  - #26 Aurora/Redis SG 인바운드에 OnpremSim SG 미허용
- 보안 audit: `admin123` 비밀번호 하드코딩 → Secrets Manager 분리 권장

### 4. AI 추천 차트 raw count 표시 추가 (9 위치)

시드 데이터 모수가 작아 % 만으로 의미 해석이 애매한 점 보완 — CTR/CVR 옆에 `(clicked/recommended)` 표기:

| 파일 | 변경 |
|------|------|
| `app.py:_aurora_recommend_top10` | SQL `SUM(clicked)/SUM(purchased)` 추가 + return dict 확장 |
| `app.py:_aurora_category_ctr_donut` | return dict에 `recommended`, `clicked` 추가 |
| `app.py:api_ai_chart_age` (route) | age dict에 `recommended/clicked/purchased` 통과 |
| `_chart_ai_age.j2` | `CTR X% (1/4) · CVR X% (0/4)` 형식 |
| `_chart_ai_donut.j2` | legend에 `CTR X% (1/4)` 추가 |
| `_chart_ai_trend.j2` | SVG에 막대 위 추천 건수 + 점 위/아래 CTR%/CVR% 라벨 |
| `ai.html` (TOP10) | `CTR X% (1/4)` 형식 |
| `ai.html` (도넛 legend) | 동일 |
| `ai.html` (7일 추이 SVG 인라인) | _chart_ai_trend.j2와 동일 라벨 |

### 5. 작업 환경 정리 (디스크 회복)

| 단계 | 회복 |
|------|------|
| 잔여물 정리 (zip 14개 — `admin-platform-patch2.zip` 단일 43GB, `.venv`/`__pycache__`/`ssm_*.json`/`*.txt` dump/디버그 스크립트 등) | 42.99 GB |
| outer `Aws_iac/` (옛 354 사본) + inner `Aws_iac/Aws_iac/aws/` + `awscliv2.zip` 정리 | 378 MB |
| **합계** | **약 43.4 GB** (44.68 GB → 1.32 GB) |

**outer `Aws_iac/` 안전 삭제 검증**:
- outer-only 41개 모두 한글 인코딩 깨진 중복본 — inner에 정상본 존재
- 핵심 yaml hash 비교: 01-network/24-admin-windows-ec2/data.env 모두 **inner가 더 최신** (2026-05-22)
- outer는 옛 시점 사본 → 안전 삭제

### 6. Desktop\ls-copy\ 작업 환경 분리

원본 ls/는 354 계정 유지, Desktop 사본은 732 계정 기준으로 변환 → 계정 전환 시 시간 절약.

- Desktop `ls-copy/` 생성: robocopy `/E /MT:8` 1.32 GB · 7,996 파일 · 5.8초
- `.git` 2개 (`ls-copy/.git` + `ls-copy/Aws_iac/Aws_iac/.git`) 모두 보존
- 16 파일 45건 치환:
  - `354493396671` → `732264765472`
  - `lifesync-354-` → `lifesync-732-`
- 원본 ls/ 검증: 354 패턴 15+3 파일 그대로 보존 ✅

### 7. Git 미Commit 상태

- `admin-platform/app.py` 수정 (CVR fix + raw count 표시) — 미Commit
- `admin-platform/templates/*.j2`, `ai.html` 수정 — 미Commit
- `docs/iac-handoff-2026-05-24.md` 신규 — 미Commit
- project-progress.md (이 섹션) — 미Commit
- HANDOFF.md 업데이트 예정 — 미Commit
- ls-copy/는 별도 환경, commit 대상 아님


