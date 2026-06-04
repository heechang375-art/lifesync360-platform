# Lambda → On-Prem Private API 네트워크 연결 절차

> ⚠️ **이 문서는 옛 설계(Service DB VPC + Data VPC 의 `customer_profile_sync`/동의고객선별 Lambda가 `192.168.56.13:8000` 호출) 기준입니다.**
> 현재 구조는 **Platform VPC 직접 VPN** + `onprem_customer_query` Lambda(SG outbound `172.16.1.73:80`)로 변경됐고, `customer_profile_sync`는 폐기됐습니다.
> 아래 "필요 작업 목록"·"진행 상태" 체크리스트는 폐기된 경로 기준이므로 **현재 진행 상황은 `project-progress.md` 를 참조하세요.**

## 목적

Service DB VPC와 Data VPC의 Lambda 함수들이 온프레미스 Private API (`ls-api`, 192.168.56.13:8000)를 직접 호출할 수 있도록 네트워크 경로를 구성한다.

---

## 현재 상태

```
[Ansible EC2] (Management VPC)
    ↓ Site-to-Site VPN (TGW) ← 이미 연결됨
[ls-api VM] 192.168.56.13:8000

[Lambda] (Service DB VPC)  → ❌ 경로 없음
[Lambda] (Data VPC)        → ❌ 경로 없음
```

Management VPC는 TGW에 붙어있고 VPN이 동작 중이라 EC2 → VM 통신은 확인됨.
Lambda가 있는 두 VPC만 TGW에 붙이면 동일한 VPN 경로를 그대로 사용 가능.

---

## 최종 목표 구조

```
Lambda (Service DB VPC) ─┐
                          ├→ TGW → Site-to-Site VPN → ls-api VM (:8000)
Lambda (Data VPC)       ─┘
```

---

## 필요 작업 목록

### 1. IaC 담당자 요청 항목

#### Service DB VPC

| 작업 | 내용 |
|------|------|
| TGW Attachment 추가 | Service DB VPC → TGW에 연결 |
| TGW 라우팅 테이블 | 온프레미스 CIDR(192.168.56.0/24) → VPN attachment |
| VPC 라우팅 테이블 | 192.168.56.0/24 → TGW |
| Lambda SG Outbound | port 8000, dest 192.168.56.13/32 허용 |

#### Data VPC

| 작업 | 내용 |
|------|------|
| TGW Attachment 추가 | Data VPC → TGW에 연결 |
| TGW 라우팅 테이블 | 192.168.56.0/24 → VPN attachment (이미 있으면 공유됨) |
| VPC 라우팅 테이블 | 192.168.56.0/24 → TGW |
| Lambda SG Outbound | port 8000, dest 192.168.56.13/32 허용 |

> TGW 라우팅 테이블의 온프레미스 CIDR 항목은 두 VPC가 공유한다. Management VPC에 이미 있으면 추가 불필요.

---

### 2. VM 측 확인 항목 (VPN 설정)

VPN ipsec.conf의 `leftsubnet`이 192.168.56.0/24를 포함하는지 확인.

```bash
# ls-vpngw VM에서 확인
sudo grep leftsubnet /etc/ipsec.conf
```

- 현재 브리지 어댑터 CIDR(예: 192.168.0.0/24)만 포함된 경우 → 192.168.56.0/24 추가 필요
- 또는 ls-api VM에서 브리지 어댑터 IP로도 8000 포트 바인딩되어 있으면 무방

VPN 도달 가능 IP 확인:
```bash
# Ansible EC2에서 VM으로 실제 도달 확인
curl http://192.168.56.13:8000/health
```

---

### 3. Lambda 코드 설정

네트워크 연결 완료 후 Lambda 환경변수:

```
PRIVATE_API_URL=http://192.168.56.13:8000
```

Lambda VPC 설정:
- VPC: 각 Lambda가 속한 VPC (Service DB / Data)
- Subnet: Private subnet
- Security Group: 위 IaC 항목에서 생성한 SG

---

## 연결 대상 Lambda별 사용 엔드포인트

| Lambda | VPC | 호출 엔드포인트 |
|--------|-----|----------------|
| customer_profile_sync | Service DB VPC | `GET /internal/identity/{affiliate_id}?company_id={id}` |
| gcp_result_ingest | Service DB VPC | 직접 호출 없음 (수신 전용) |
| 동의 고객 선별 | Data VPC | `GET /internal/consent/{global_id}` |
| 그룹 데이터 수집 | Data VPC | `GET /internal/customer/{global_id}` |

---

## 연결 검증 순서

네트워크 구성 완료 후 순서대로 확인:

```bash
# 1. TGW 라우팅 확인 (AWS 콘솔)
# VPC → Transit Gateways → Route Tables
# 192.168.56.0/24 → VPN attachment 항목 존재 여부

# 2. VPC 라우팅 테이블 확인 (AWS 콘솔)
# Service DB VPC / Data VPC Route Tables
# 192.168.56.0/24 → tgw-xxxxxx 항목 존재 여부

# 3. Lambda 테스트 invoke (AWS CLI)
aws lambda invoke \
  --function-name customer-profile-sync \
  --payload '{"ls_user_id":"LS-TEST","email":"test@test.com","company_id":"bank"}' \
  response.json
cat response.json

# 4. Private API health check (Lambda 내부에서)
# Lambda 코드에 임시 /health 호출 추가 후 로그로 확인
```

---

## 현재 진행 상태

- [x] VPN Site-to-Site 연결 (Management VPC ↔ ls-api VM)
- [x] Ansible EC2 → Private API 통신 확인
- [ ] Service DB VPC TGW Attachment (IaC)
- [ ] Data VPC TGW Attachment (IaC)
- [ ] TGW 라우팅: 온프레미스 CIDR 추가 (IaC)
- [ ] Lambda SG 구성 (IaC)
- [ ] Lambda customer_profile_sync 코드 작성 및 배포
- [ ] 동의 고객 선별 Lambda 코드 작성 및 배포
- [ ] 연결 검증
