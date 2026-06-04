# 문서 현행화 체크리스트

> 작성일: 2026-05-11
> 대상: 아키텍처구성도, 비용최적화, WBS 파일

> ⚠️ **프로젝트 종료(2026-06) — 미진행 마감.**
> 아래 `[ ]` 설계서(PPTX/XLSX) 현행화 작업은 진행하지 않고 종료됐습니다. **실행 목록이 아니라 "설계서와 실제 구현의 차이 기록"**으로 참고하세요. 최신 설계서(아키텍처 V3.9, WBS V4.0)에는 일부 반영됐을 수 있으니 해당 파일을 직접 확인하세요.

이진 파일(xlsx/pptx)은 직접 수정 불가 — 아래 항목 기준으로 수동 업데이트.

---

## 아키텍처구성도 V3.6.pptx (우선)

V3.4도 같은 항목 동일 적용.

### [ ] CI/CD 흐름 (슬라이드 10 또는 CI/CD 다이어그램)

| 구분 | 현재 파일 | 실제 구현 |
|------|---------|---------|
| 배포 방식 | Ansible Pull — VM이 내부 저장소에서 Playbook pull | **Push 방식** — ls-api가 EC2 `/deploy` POST → EC2가 `ansible-playbook` 실행 |
| 트리거 주체 | 저장소 변경 감지 | ls-api의 cron 또는 수동 HTTP 호출 |
| EC2 역할 | 미표시 | **EC2 Control Node** (Deploy Server 포함) 명시 필요 |

수정 방향: "Ansible Pull" 화살표를 "ls-api → EC2 Deploy Server(9000) → ansible-playbook" 흐름으로 변경.

---

### [ ] PII 테이블 구조 (슬라이드 13 / 26 / 31)

| 구분 | 현재 파일 | 실제 구현 |
|------|---------|---------|
| 테이블 구조 | `customer_pii_secure` 별도 테이블 존재 | **없음** — `master_customer`에 직접 암호화 저장 |
| 암호화 컬럼 | 별도 테이블의 모든 컬럼 | `representative_name`, `birth_dt` 두 컬럼 Fernet 암호화 |
| 복호화 경로 | pii_secure 테이블 조인 | ls-token 서비스 → Fernet 복호화 후 반환 |

수정 방향: `customer_pii_secure` 테이블 제거, `master_customer` 내 암호화 컬럼 표시.

---

### [ ] 컬럼명 오류 (슬라이드 14)

| 구분 | 현재 파일 | 실제 코드 |
|------|---------|---------|
| 고객 식별자 컬럼명 | `global_customer_id` | **`global_id`** |

수정 방향: 다이어그램 및 테이블 정의서 내 컬럼명 일치.

---

### [ ] VPN 라우팅 방식 (슬라이드 2)

| 구분 | 현재 파일 | 실제 구현 |
|------|---------|---------|
| 라우팅 | Cloud Router + BGP | **Static Routing** |
| 변경 이유 | — | BGP 연결 불안정으로 전환 |

수정 방향: BGP → Static Routing, Cloud Router 제거 또는 주석.

---

### [ ] GCP 처리 방식 (슬라이드 4)

| 구분 | V3.4 | V3.6 |
|------|------|------|
| GCP 데이터 적재 | BigQuery Load Job | Dataflow |

실제 최종 구현 방식 확인 후 통일. V3.6 기준이 최신이면 V3.4 폐기 또는 V3.6으로 통일.

---

## 비용최적화_V3.2.xlsx

### [ ] EC2 Control Node 항목 추가

현재 파일에 미포함. 추가할 항목:

| 서비스 | 사양 | 시간/월 | 단가 | 월 비용 |
|--------|------|---------|------|---------|
| EC2 Control Node | t3.small | 198h | $0.0272/h | ~$5.4 |

---

### [ ] 운영 시간 재계산

| 구분 | 파일 | 실제 |
|------|------|------|
| 월 운영 시간 | 180시간 | **198시간** (9시간/일 × 22일) |
| 비고 | — | Aurora만 24/7 (DeletionProtection으로 재생성 시 유지) |

Aurora는 IaC 재배포 시에도 삭제 불가(DeletionProtection=true) → 730시간 풀 과금 반영 필요.

---

### [ ] 총비용 재산출 (상세는 cost-analysis.md 참고)

현재 파일 $220/월 → 실제 계산 기준 약 **$109-115/월** (198시간 운영 + Aurora 24/7 포함, 기존 항목 일부 과다 계상 정정).

---

## WBS_V3.5.xlsx

### [ ] 일정 전면 업데이트

Gantt 차트 날짜 구버전. 현재 진행 상황 기준으로 완료/진행 중/잔여 구간 재작성 필요.

현재 실제 완료 항목:
- VM 4대 구성, Ansible 배포, 데이터 적재, PII 암호화
- CloudFormation 전체 YAML, ECS Blue/Green, CodeDeploy/Pipeline IaC
- EC2 Control Node, Deploy Server, VPN Static 라우팅 전환

잔여 항목:
- Secrets Manager 값 입력 (배포 시점)
- CloudFormation 스택 실제 배포
- settings 포인트 Aurora 연동

---

## 데이터셋정의서_v9.xlsx / 역할분담_V3.2.pptx / 데이터처리프로세스_결과처리.pptx

현재 내용이 아키텍처 기준에 크게 어긋나지 않음. 수정 불필요.

단, `데이터셋정의서`에서 컬럼명 `global_customer_id` 사용 여부 확인 후 `global_id`로 통일.
