# AWS Site-to-Site VPN 설정 진행 내용
> Local VM (VirtualBox) → AWS Ansible Control Node 통신 구성

---

## 아키텍처 구성

```
VirtualBox VM (Private API VM)
        ↓ 브리지 어댑터 (공인IP)
공유기/로컬 네트워크
        ↓ IPSec Tunnel
AWS Site-to-Site VPN
        ↓
AWS Transit Gateway
        ↓
Management VPC → Private Subnet
        ↓
Amazon EC2 (Ansible Control Node)
```

---

## 목적
- Legacy System의 Private API VM이 클라우드로부터 호출을 받아 PII 데이터를 응답하는 구조
- Ansible Control Node가 로컬 VM을 관리(자동화)하는 구조

---

## VirtualBox 네트워크 어댑터 설정

Private API VM에 브리지 어댑터 추가 (기존 어댑터 유지):

| 어댑터 | 모드 | 용도 |
|--------|------|------|
| 어댑터1 | NAT | 인터넷 연결 |
| 어댑터2 | Host-only | VM간 내부 통신 |
| 어댑터3 | **브리지 (추가)** | AWS VPN 피어 통신 |

```
VirtualBox → VM 설정 → 네트워크 → 어댑터3
→ 네트워크 어댑터 사용 체크
→ 브리지 어댑터 선택
→ 실제 NIC 선택 (Wi-Fi 또는 이더넷)
```

---

## StrongSwan 설치

```bash
sudo apt update
sudo apt install strongswan strongswan-pki libcharon-extra-plugins -y
```

---

## AWS 콘솔 설정 순서

1. **Customer Gateway 생성**
   - VPC → Customer Gateways → Create Customer Gateway
   - IP Address: 공유기 공인IP (`curl ifconfig.me`로 확인)
   - BGP ASN: 65000

2. **Site-to-Site VPN Connection 생성**
   - VPC → Site-to-Site VPN → Create
   - Customer Gateway: 위에서 생성한 것
   - Transit Gateway 연결

3. **Configuration 파일 다운로드**
   - Site-to-Site VPN Connections → 해당 VPN 선택
   - Download Configuration 클릭
   - **Vendor: Generic 선택** (Strongswan 별도 옵션 없음)
   - 다운받은 파일에서 아래 값 확인:
     - AWS VPN 터널 IP
     - Pre-shared Key (PSK)

---

## StrongSwan 설정

### /etc/ipsec.conf 수정
```bash
sudo nano /etc/ipsec.conf
```

```conf
config setup
    charondebug="ike 2, knl 2, cfg 2"

conn aws-vpn
    authby=secret
    left=<브리지 어댑터 IP>        # %defaultroute 대신 명시 (ex: 192.168.45.157)
    leftid=<공유기 공인IP>          # curl ifconfig.me 값, AWS Customer Gateway에 등록된 IP
    leftsubnet=<로컬 브리지 CIDR>   # ex) 192.168.45.0/24
    right=<AWS VPN 터널IP>
    rightsubnet=<AWS VPC CIDR>      # ex) 10.0.0.0/16
    ike=aes256-sha256-modp2048
    esp=aes256-sha256
    keyingtries=%forever
    keyexchange=ikev2
    forceencaps=yes                 # NAT 환경 필수 (공유기 뒤에 있을 경우)
    dpdaction=restart               # 피어 무응답 시 즉시 재협상
    dpddelay=10s                    # 10초마다 DPD keepalive 전송
    dpdtimeout=30s                  # 30초 내 응답 없으면 재시작
    ikelifetime=7800s               # AWS Phase1 기본(28800s)보다 짧게 — StrongSwan이 먼저 재협상
    lifetime=3300s                  # AWS Phase2 기본(3600s)보다 짧게
    margintime=300s                 # 만료 5분 전부터 재협상 시작 (끊김 없는 rekeying)
    auto=start
```

> **주의:** `left=`에 `%defaultroute` 대신 브리지 어댑터 IP를 명시해야 합니다.
> `leftid=`는 AWS Customer Gateway에 등록한 공인IP와 반드시 일치해야 합니다.

### /etc/ipsec.secrets 수정
```bash
sudo nano /etc/ipsec.secrets
```

```
<공유기 공인IP> <AWS VPN 터널IP> : PSK "<PSK값>"
```

### IP 포워딩 활성화
```bash
sudo nano /etc/sysctl.conf
# 아래 줄 주석 해제 또는 추가
net.ipv4.ip_forward = 1

# 적용
sudo sysctl -p
```

---

## 시작 및 확인 명령어

```bash
# 재시작 (Ubuntu 20.04+ 기준)
sudo systemctl restart strongswan-starter

# 부팅시 자동시작
sudo systemctl enable strongswan-starter

# 터널 상태 확인
sudo ipsec status
sudo ipsec statusall

# 실시간 로그
sudo journalctl -u strongswan-starter -f
```

### 정상 연결 시 출력 예시
```
aws-vpn[1]: ESTABLISHED ...    ← 터널 연결됨
aws-vpn{1}: INSTALLED, TUNNEL  ← 트래픽 흐를 준비 완료
```

### 로그 에러 메시지 해석

| 메시지 | 의미 |
|--------|------|
| `peer not responding` / `giving up after 5 retransmits` | AWS에서 응답 없음 → 포트포워딩 또는 IP 불일치 |
| `authentication failed` | PSK 불일치 |
| `TS_UNACCEPTABLE` | leftsubnet/rightsubnet CIDR 불일치 |
| `INVALID_KE_PAYLOAD` | ike 암호화 알고리즘 불일치 |

### tcpdump로 패킷 송수신 확인
```bash
# 브리지 인터페이스 확인
ip addr | grep <브리지IP>

# UDP 500/4500 패킷 모니터링
sudo tcpdump -i <브리지인터페이스> udp port 500 or udp port 4500 -n
```

- **send만 있고 recv 없음** → 공유기 포트포워딩 미설정 (AWS 응답이 VM까지 못 옴)
- **recv도 있음** → ipsec 설정 문제

---

## 현재 진행 상태

- [x] VirtualBox 브리지 어댑터 추가
- [x] StrongSwan 설치
- [x] AWS Customer Gateway / Site-to-Site VPN 생성 (Static 라우팅)
- [x] ipsec.conf / ipsec.secrets 설정
- [x] VPN 터널 연결 확인 (ESTABLISHED)
- [x] Ansible Control Node까지 통신 확인
- [x] DPD + SA lifetime 설정 (간헐적 끊김 방지)
- [x] Lambda VPC → TGW 부착 + 라우팅 구성 (2026-05-23)
- [x] 공유기 교체 후 Private API IP 변경 대응 (2026-05-23)

---

## 트러블슈팅 과정

### 문제 1: Customer Gateway IP 불일치
`sudo ipsec status` 결과: `security association (0 up, 1 connecting)`
로그: `peer not responding, giving up after 5 retransmits`

**원인:** AWS Customer Gateway에 등록한 IP가 실제 공유기 공인IP와 달랐음
**해결:** Customer Gateway IP를 `curl ifconfig.me` 값과 일치하도록 수정

---

### 문제 2: 학원 공유기 포트포워딩 불가
IPSec VPN은 공유기에서 아래 포트포워딩이 필요하나 학원 공유기 조작 불가:

| 프로토콜 | 외부 포트 | 내부 IP | 내부 포트 |
|----------|-----------|---------|-----------|
| UDP | 500 | <브리지IP> | 500 |
| UDP | 4500 | <브리지IP> | 4500 |

tcpdump 확인 결과: VM → AWS 방향 패킷만 있고 AWS → VM 응답 없음
**해결:** CGW IP 수정 후 포트포워딩 없이도 연결 성공

---

### 문제 3: BGP Status Down으로 인한 통신 불가
터널은 ESTABLISHED 되었으나 EC2 → VM 방향 통신 안 됨
AWS 콘솔에서 확인 시 `BGP Status: Down`, `IPSec: Down`

**원인:** StrongSwan은 IPSec 터널만 담당하고 BGP는 별도 데몬 필요

| 방식 | 필요한 것 | 동작 여부 |
|------|-----------|-----------|
| Static | StrongSwan만 | ✅ |
| BGP (Dynamic) | StrongSwan + FRRouting | ❌ (FRR 미설치) |

BGP를 사용하려면 FRRouting 같은 BGP 데몬을 추가로 설치해야 함:
```bash
# BGP 사용 시 FRRouting 설치 필요
sudo apt install frr -y
sudo nano /etc/frr/daemons
# bgpd=yes 로 변경
```

**해결:** VPN Connection을 Static 라우팅으로 재생성

```
VPC → Site-to-Site VPN Connections → Create
→ Routing Options: Static 선택
→ Static IP Prefixes: 192.168.45.0/24 입력  # 공유기 브리지 대역 전체 (변경 가능)
→ Customer Gateway: 기존 것 선택
→ Transit Gateway 연결
```

---

### 문제 4: leftsubnet CIDR이 GCP 대역과 충돌 가능성
브리지 어댑터가 Wi-Fi라 IP 변경 불가 (공유기 DHCP에서 받아오는 구조)

**해결:** leftsubnet을 /24 대신 /32로 단일 IP 지정 (초기 구성 시)
```conf
leftsubnet=172.16.1.73/32    # 초기 설정 — 이후 공유기 교체로 IP 변경됨 (아래 변경 이력 참고)
```
AWS Transit Gateway + Management VPC 라우팅 테이블도 /32로 변경
→ Longest Prefix Match 원칙으로 GCP 대역보다 우선 라우팅됨

---

## 다중 연결 구성 (EC2 1대 + Lambda 2개)

Private API VM이 총 3곳(EC2 1대, Lambda 2개)과 통신해야 하는 구조.
Lambda는 각각 다른 VPC(VPC-A, VPC-B)에 위치.

### 최종 아키텍처

```
Lambda A (VPC-A) ─┐
Lambda B (VPC-B) ─┤→ VPC Peering → EC2 (Management VPC) → 터널 → VM
EC2 (Ansible)    ─┘
```

### 왜 이 구조인가

| 방식 | 가능 여부 | 이유 |
|------|-----------|------|
| Site-to-Site VPN 직접 연결 | ❌ | 공유기 포트포워딩 불가 |
| PrivateLink + NLB | 가능하나 불필요 | 학습 환경에서 NLB 비용 과다 |
| VPC Peering + EC2 직접 포워딩 | ✅ | 비용 최소, 구성 단순 |

> 실제 프로덕션 온프레미스 환경이라면 전용 라우터로 포트포워딩이 가능하므로
> Site-to-Site VPN 직접 연결이 표준. 현재 구조는 학습 환경 제약으로 인한 차선책.

---

## EC2 직접 포트포워딩 방식 전체 설정

### 1단계 — EC2 Elastic IP 할당

```
AWS 콘솔 → EC2 → Elastic IPs
→ Allocate Elastic IP
→ Associate → Ansible EC2 선택
```
> EC2에 연결된 상태에서는 Elastic IP 비용 무료

---

### 2단계 — VM에서 Reverse SSH 터널 설정

```bash
# autossh 설치
sudo apt install autossh -y

# SSH 키 생성 (없으면)
ssh-keygen -t rsa -b 4096

# EC2에 공개키 등록
ssh-copy-id -i ~/.ssh/id_rsa.pub ec2-user@<Elastic IP>
```

API 포트 포함 터널 연결:
```bash
autossh -M 0 -f -N \
    -R 2222:localhost:22 \       # Ansible SSH용
    -R 8080:localhost:8080 \     # Lambda A API용
    -R 8443:localhost:8443 \     # Lambda B API용
    ec2-user@<Elastic IP>
```

부팅 시 자동 실행 설정:
```bash
sudo nano /etc/systemd/system/autossh-tunnel.service
```

```ini
[Unit]
Description=AutoSSH Reverse Tunnel
After=network.target

[Service]
User=<VM유저>
ExecStart=/usr/bin/autossh -M 0 -N \
    -R 2222:localhost:22 \
    -R 8080:localhost:8080 \
    -R 8443:localhost:8443 \
    -i /home/<VM유저>/.ssh/id_rsa \
    ec2-user@<Elastic IP>
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable autossh-tunnel
sudo systemctl start autossh-tunnel
```

---

### 3단계 — EC2 iptables 포트포워딩 설정

Lambda에서 EC2로 오는 트래픽을 터널(127.0.0.1)로 전달:

```bash
# IP 포워딩 활성화
sudo sysctl -w net.ipv4.ip_forward=1
echo "net.ipv4.ip_forward = 1" | sudo tee -a /etc/sysctl.conf

# iptables 규칙 추가
sudo iptables -t nat -A PREROUTING \
    -p tcp --dport 8080 \
    -j DNAT --to-destination 127.0.0.1:8080

sudo iptables -t nat -A PREROUTING \
    -p tcp --dport 8443 \
    -j DNAT --to-destination 127.0.0.1:8443

# 재부팅 후에도 규칙 유지
sudo apt install iptables-persistent -y
sudo netfilter-persistent save
```

---

### 4단계 — EC2 Security Group 설정

```
EC2 Security Group → Inbound Rules 추가
→ TCP 8080 : VPC-A CIDR 허용  (Lambda A)
→ TCP 8443 : VPC-B CIDR 허용  (Lambda B)
→ TCP 22   : 관리용 IP 허용
```

---

### 5단계 — VPC Peering 설정

NLB 없이 Lambda → EC2 직접 연결을 위해 VPC Peering 사용:

```
AWS 콘솔 → VPC → Peering Connections
→ Create Peering Connection

Peering 1: Management VPC ↔ VPC-A
Peering 2: Management VPC ↔ VPC-B
```

각 VPC 라우팅 테이블 추가:
```
Management VPC 라우팅 테이블
→ VPC-A CIDR → Peering Connection 1
→ VPC-B CIDR → Peering Connection 2

VPC-A 라우팅 테이블
→ EC2 IP (/32) → Peering Connection 1

VPC-B 라우팅 테이블
→ EC2 IP (/32) → Peering Connection 2
```

> **주의:** VPC-A, VPC-B, Management VPC의 CIDR이 서로 겹치면 안 됨

---

### 6단계 — Lambda VPC 및 Security Group 설정

```
Lambda A → Configuration → VPC
→ VPC-A 선택
→ Private Subnet 선택
→ Security Group Outbound: EC2 IP, TCP 8080 허용

Lambda B → Configuration → VPC
→ VPC-B 선택
→ Private Subnet 선택
→ Security Group Outbound: EC2 IP, TCP 8443 허용
```

---

### 7단계 — Ansible 인벤토리 설정

```ini
[local_vms]
vm1 ansible_host=127.0.0.1 ansible_port=2222 ansible_user=<VM유저>
```

---

### 8단계 — 통신 확인

EC2에서 터널 및 포트 확인:
```bash
# 터널 포트 리스닝 확인
ss -tlnp | grep 8080
ss -tlnp | grep 8443

# VM API 직접 테스트
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8443/health
```

Lambda에서 테스트:
```python
import urllib.request
response = urllib.request.urlopen("http://<EC2 Private IP>:8080/health")
print(response.read())
```

---

### 전체 트래픽 흐름 요약

```
[Ansible 관리]
EC2 → SSH 터널(2222) → VM

[Lambda A API 호출]
Lambda A → VPC Peering → EC2:8080 → iptables → 터널 → VM:8080

[Lambda B API 호출]
Lambda B → VPC Peering → EC2:8443 → iptables → 터널 → VM:8443
```

---

## 라우팅 문제 해결 체크리스트 (터널 연결 후)

VPN 터널이 ESTABLISHED 되었으나 Ansible EC2 Private IP까지 통신이 안 될 경우:

1. **Transit Gateway 라우팅 테이블 확인**
   ```
   AWS 콘솔 → VPC → Transit Gateways → Route Tables
   → 로컬 네트워크 CIDR → Management VPC로 가는 경로 있는지 확인
   ```

2. **Management VPC 라우팅 테이블 확인**
   ```
   AWS 콘솔 → VPC → Route Tables
   → Management VPC 라우팅 테이블
   → 로컬 CIDR이 Transit Gateway로 향하는 경로 있는지 확인
   ```

3. **VPN Route Propagation 확인**
   ```
   AWS 콘솔 → VPC → Site-to-Site VPN
   → Route Propagation → Management VPC 라우팅 테이블에 로컬 CIDR 있는지 확인
   ```

4. **Ansible EC2 Security Group 확인**
   ```
   AWS 콘솔 → EC2 → Ansible 인스턴스
   → Security Groups → Inbound Rules
   → 로컬 브리지 CIDR에서 오는 SSH(22), ICMP 허용 여부 확인
   ```

---

## 변경 이력

### 2026-05-23 — 공유기 교체 후 Private API 서버 IP 변경 대응

**변경 배경:**  
학원 공유기 교체로 VirtualBox 브리지 어댑터 IP가 변경됨.  
Private API 서버의 브리지 NIC IP: `172.16.1.73` → `192.168.45.157`

**AWS 측 변경 사항:**

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| Lambda `PRIVATE_API_URL` | `http://172.16.1.73:80` | `http://192.168.45.157:80` |
| Lambda VPC TGW 부착 | 없음 | `tgw-attach-04c5657d93f2fe920` |
| Lambda 서브넷 라우트 | `192.168.45.0/24` 없음 | `192.168.45.0/24` → TGW |
| Lambda SG Egress | `172.16.1.0/24:80` 만 있음 | `192.168.45.0/24:80` 추가 |
| TGW 라우트 (`tgw-rtb-05da340fa6bc057c7`) | `192.168.45.0/24` → VPN만 있음 | `10.0.0.0/16` (Lambda VPC) propagated 추가됨 |

**온프레미스 측 변경 사항 (ipsec.conf):**

```conf
# 변경 전
left=172.16.1.73
leftsubnet=172.16.1.73/32

# 변경 후
left=192.168.45.157
leftsubnet=192.168.45.157/32  # 또는 192.168.45.0/24
```

VPN 재시작:
```bash
sudo systemctl restart strongswan-starter
sudo ipsec status  # ESTABLISHED 확인
```

**검증 결과:**

```bash
# Lambda → 온프레미스 Private API 연결 확인
aws lambda invoke --function-name lifesync-onprem-customer-query \
  --payload '{"action":"count_users"}' out.json
# → {"status": "ACTIVE", "count": 294277}  ✅

# VPN 터널 상태
# 43.201.181.136: UP  /  13.125.57.64: DOWN (이중화 중 1개 UP → 정상)
```