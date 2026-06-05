# LifeSync360 온프레미스 DB 스키마 레퍼런스

- **DB 서버**: ls-db (192.168.56.11)
- **스키마**: `lifesync_onprem`
- **엔진**: MySQL 8.x, InnoDB, utf8mb4_unicode_ci
- **테이블 수**: 8개
- **기준 일자**: 2026-05-19 (라이브 실측 반영 — 인덱스·행수)
- **인덱스 추가(2026-05-19)**: users `uq_users_login_email`/`uq_users_ls_user_id`/`idx_users_status`/`idx_global`, master_customer `idx_mc_status` — status·키 풀스캔 제거용. 그 외 인덱스는 기존.

## ID 체계

| ID | 형식 | 역할 |
|----|------|------|
| `ls_user_id` | `LS000000001` | LifeSync 플랫폼 회원 ID (가입 시 발급) |
| `global_id` | `G000000001` | 계열사 통합 고객키 (마스터 매칭 결과) |
| `source_customer_id` | `BNK-00000001`, `CRD-00000001` 등 | 계열사 원본 고객 ID (도메인별) |
| `pii_token` | `PII-XXXXXXXXXXXXXXXX` | PII 저장 식별자 (SHA256 첫 16자) |
| `token_id` | UUID4 | AWS 송신용 비식별 토큰 |

---

## 1. users (회원 마스터)

> 플랫폼 가입자(consent_completed='Y') 정보. **300,314건** (2026-05-18 마스터 100만 → 가입 30%로 축소). ACTIVE ≈ 294,277.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| user_id | BIGINT PK | 회원 일련번호 | AUTO_INCREMENT |
| ls_user_id | VARCHAR(20) | 플랫폼 회원 ID | `LS000000001` |
| global_id | VARCHAR(30) | 통합 고객키 | master_customer 참조 |
| login_email | VARCHAR(100) | 로그인 이메일 | 평문 (참고용, 운영은 암호화 필요) |
| password_hash | VARCHAR(60) | 비밀번호 해시 | SHA256 hex (운영은 bcrypt 권장) |
| mobile | VARCHAR(20) | 휴대폰 | `010-0000-0001` 평문 |
| user_status | VARCHAR(10) | 회원 상태 | `ACTIVE` / `LOCK` |
| consent_completed | CHAR(1) | 동의 완료 플래그 | `Y` / `N` |
| created_dt | TIMESTAMP | 가입일시 | |
| last_login_dt | TIMESTAMP | 최근 로그인 | |

**인덱스/제약**: PK `user_id` · UNIQUE `uq_users_login_email`(login_email) · UNIQUE `uq_users_ls_user_id`(ls_user_id) · INDEX `idx_global`(global_id) · INDEX `idx_users_status`(user_status)

---

## 2. master_customer (통합 고객 마스터)

> 계열사 통합 후 고객 1인당 1건. 1,000,000건.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| global_id | VARCHAR(30) PK | 통합 고객키 | |
| customer_status | VARCHAR(15) | 고객 상태 | `ACTIVE` / `DORMANT` / `WITHDRAWN` |
| vip_grade | VARCHAR(10) | VIP 등급 | `NORMAL` / `SILVER` / `GOLD` 등 |
| customer_type | VARCHAR(15) | 고객 타입 | `INDIVIDUAL` / `CORPORATE` |
| first_created_dt | TIMESTAMP | 최초 등록일 | |
| last_updated_dt | TIMESTAMP | 최종 갱신일 | |

**인덱스/제약**: PK `global_id` · INDEX `idx_mc_status`(customer_status) · 1,000,000건

---

## 3. customer_pii_secure (PII 암호화 저장소)

> AES-256-GCM 으로 암호화된 개인정보. 1,000,000건.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| pii_token | VARCHAR(20) PK | PII 토큰 | `PII-` + SHA256(global_id)[:16] |
| global_id | VARCHAR(30) | 통합 고객키 | |
| customer_name_enc | VARCHAR(255) | 이름(암호화) | base64(IV+CT+TAG) |
| rrn_enc | VARCHAR(255) | 주민번호(암호화) | 형식: `YYMMDD-NMMMMMM` |
| mobile_enc | VARCHAR(255) | 휴대폰(암호화) | |
| email_enc | VARCHAR(255) | 이메일(암호화) | |
| address_enc | VARCHAR(500) | 주소(암호화) | 시/도 + 시/군/구 + 도로명 + 건물번호 |
| created_dt | TIMESTAMP | 행 생성일시 | DEFAULT CURRENT_TIMESTAMP |
| updated_dt | TIMESTAMP | 마지막 갱신일시 | ON UPDATE CURRENT_TIMESTAMP |

**인덱스/제약**: PK `pii_token` · INDEX `idx_global`(global_id) · 1,000,000건

---

## 4. customer_360_profile (360° 분석 프로파일)

> 비식별 분석 데이터. 1,000,000건.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| global_id | VARCHAR(30) PK | 통합 고객키 | |
| gender | CHAR(1) | 성별 | `M` / `F` |
| age_band | VARCHAR(10) | 연령대 | `20s` / `30s` / ... / `70s` |
| region | VARCHAR(20) | 지역 | `SEOUL` / `GYEONGGI` 등 |
| income_grade | VARCHAR(10) | 소득 등급 | `LOW` / `MID` / `HIGH` |
| asset_grade | VARCHAR(10) | 자산 등급 | `LOW` / `MID` / `HIGH` |
| wearable_flag | CHAR(1) | 웨어러블 연동 | `Y` / `N` |
| risk_score | DECIMAL(5,2) | 위험 점수 | 0~100 |
| health_score | DECIMAL(5,2) | 건강 점수 | 0~100 |
| finance_score | DECIMAL(5,2) | 금융 점수 | 0~100 |
| asset_score | DECIMAL(5,2) | 자산 점수 | 0~100 (CRC32 기반 채움) |
| lifesync_score | DECIMAL(5,2) | LifeSync 종합점수 | 0~100 |
| last_calc_dt | TIMESTAMP | 마지막 계산일시 | |

**인덱스/제약**: PK `global_id` (보조 인덱스 없음 — 전건 분석 배치 전용) · 1,000,000건

---

## 5. customer_identity_map (계열사 ID 매핑)

> 계열사별 원본 ID ↔ global_id 매핑. **3,500,246건**.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| id | BIGINT PK | 매핑 일련번호 | AUTO_INCREMENT |
| global_id | VARCHAR(30) | 통합 고객키 | |
| domain | VARCHAR(20) | 계열사 도메인 | `BANK` / `CARD` / `INSURANCE` 등 |
| source_customer_id | VARCHAR(30) | 계열사 원본 고객 ID | `BNK-00000001` 형식 |
| match_type | VARCHAR(10) | 매칭 방식 | `EXACT` / `FUZZY` |
| active_flag | CHAR(1) | 활성 여부 | `Y` / `N` |
| created_dt | TIMESTAMP | 매핑 생성일시 | DEFAULT CURRENT_TIMESTAMP |

**인덱스/제약**: PK `id` · UNIQUE `uq_map`(global_id, domain) · INDEX `idx_affiliate`(source_customer_id)
> ⚠️ `domain` 단독 인덱스 없음 → `WHERE domain=?` 필터는 비효율(uq_map 선두컬럼 global_id). 도메인별 대량 조회 시 주의.

---

## 6. consent (동의 이력)

> 도메인별 동의 상태. 8,000,000건 (1M 고객 × 8 도메인).

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| id | BIGINT PK | 동의 일련번호 | AUTO_INCREMENT |
| global_id | VARCHAR(30) | 통합 고객키 | |
| domain | VARCHAR(30) | 도메인 | 8종 (아래 참고) |
| consent_flag | CHAR(1) | 동의 플래그 | `Y` (현재 동의) / `N` (미동의/철회) |
| consent_version | VARCHAR(10) | 동의 버전 | `v1.0` 등 |
| revoke_dt | TIMESTAMP NULL | 철회일시 | `NULL` = 철회 안 됨 |
| consent_dt | TIMESTAMP NULL | 동의일시 | `NULL` = 동의 이력 없음 |

**도메인 8종** (Aurora `company_master.company_code` 와 통일):
- `BANK` (은행)
- `CARD` (카드)
- `SEC` (증권)
- `INS` (보험사)
- `ONINS` (인터넷보험)
- `HLT` (헬스케어)
- `HOS` (병원)
- `WBL` (웨어러블)

**의미 조합**:
| consent_flag | consent_dt | revoke_dt | 의미 |
|---|---|---|---|
| `Y` | 채워짐 | NULL | 활성 (현재 동의 중) |
| `N` | 채워짐 | 채워짐 | 동의했다가 철회 |
| `N` | NULL | NULL | 동의한 적 없음 |

**인덱스/제약**: PK `id` · UNIQUE `uq_consent`(global_id, domain) · INDEX `idx_consent_flag`(consent_flag) · 8,000,000건
> "현재 동의" 정의 = `consent_flag='Y' AND revoke_dt IS NULL` (라이브 Y행 199,413, distinct global_id 59,817). `idx_consent_flag` 로 Y 필터는 인덱스 사용(풀스캔 아님).

---

## 7. matching_audit_log (매칭 감사 로그)

> 계열사 → 통합 매칭 요청 이력. **3,498,623건**.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| audit_id | BIGINT PK | 감사 일련번호 | AUTO_INCREMENT |
| request_id | VARCHAR(20) | 요청 ID | `REQ-0000000001` |
| ls_user_id | VARCHAR(20) | 요청자(플랫폼 ID) | |
| matched_global_id | VARCHAR(30) | 매칭 결과 통합키 | |
| match_rule | VARCHAR(30) | 매칭 규칙 | `EXACT_RRN` 등 |
| match_score | INT | 매칭 점수 | 0~100 |
| result | VARCHAR(20) | 결과 | `MATCH` / `NEW_CREATE` |
| request_dt | TIMESTAMP | 요청일시 | |
| remarks | TEXT | 추가 메모 | 자유 텍스트, NULL 가능 |

**인덱스/제약**: PK `audit_id` · INDEX `idx_audit_global`(matched_global_id) · INDEX `idx_audit_ls_user`(ls_user_id) · INDEX `idx_audit_req_dt`(request_dt)

---

## 8. token_map (AWS 송신용 토큰 매핑)

> global_id ↔ UUID 토큰 매핑. 1,000,000건.

| 컬럼 | 타입 | 한글명 | 비고 |
|------|------|--------|------|
| token_id | VARCHAR(36) PK | 토큰 (UUID) | UUID4, AWS 로 송신되는 값 |
| field_name | VARCHAR(30) NOT NULL DEFAULT `'global_id'` | 토큰 필드 종류 | 현재 `global_id` 만 사용 |
| original_hash | VARCHAR(64) UNIQUE | 원본 SHA256 해시 | hex 64자 (멱등성 키) |
| global_id | VARCHAR(30) NOT NULL | 원본 global_id | FK → master_customer |
| created_dt | TIMESTAMP | 발급일시 | DEFAULT CURRENT_TIMESTAMP |

**인덱스/제약** (라이브 실측): PK `token_id` · UNIQUE `uq_hash`(original_hash) · INDEX `idx_global`(global_id) · 1,000,000건
- `UNIQUE uq_hash (original_hash)` — 중복 토큰 방지 (멱등)
- `FK fk_token_map_global_id` → `master_customer(global_id)` — orphan 방지
- `KEY idx_global (global_id)` — global_id 조회 인덱스

---

# 암호화 / 토큰화 방식

## AES-256-GCM (PII 암호화)

**대상**: customer_pii_secure 의 5개 enc 컬럼

```
key       = 32 bytes (base64 env: TOKEN_AES_KEY_B64)
IV        = 12 bytes random (매 암호화 시 새로 생성)
ciphertext = IV(12) || CT || GCM_TAG(16)
저장형식  = base64(ciphertext)
```

**특성**:
- 동일 평문도 매번 다른 IV 라 다른 ciphertext 생성
- GCM 인증 태그로 무결성 검증
- 키 분실 시 복호화 불가 → 키 vault 보관 필수

**Python 구현** (encrypt_pii.py):
```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os, base64
aesgcm = AESGCM(base64.b64decode(KEY_B64))

def aes_encrypt(value: str) -> str:
    iv = os.urandom(12)
    ct = aesgcm.encrypt(iv, value.encode("utf-8"), None)
    return base64.b64encode(iv + ct).decode("ascii")
```

**복호화**:
```python
def aes_decrypt(enc_b64: str) -> str:
    raw = base64.b64decode(enc_b64)
    return aesgcm.decrypt(raw[:12], raw[12:], None).decode("utf-8")
```

**pii_token (결정적 식별자)**:
```python
pii_token = "PII-" + sha256(global_id).hexdigest().upper()[:16]
```
→ 동일 global_id 면 동일 pii_token. 재실행 안전.

---

## SHA-256 + UUID4 토큰화 (AWS 송신용)

**대상**: token_map (global_id → UUID 매핑)

```
original_hash = SHA-256(global_id) hex   ← 식별 키 (멱등성)
token_id      = UUID4                    ← AWS 로 송신되는 값
```

**특성**:
- 토큰은 **랜덤 (UUID4)** — 원본과 무관, 역추적 불가
- 매핑은 온프레미스 token_map 만 보유 → 토큰 vault 패턴
- AWS 침해 시 토큰만 유출, 매핑은 격리 유지
- original_hash 가 UNIQUE → 같은 global_id 재요청 시 기존 token_id 반환 (멱등)

**Python 구현** (tokenize_global_id.py):
```python
import hashlib, uuid

original_hash = hashlib.sha256(global_id.encode()).hexdigest()
token_id      = str(uuid.uuid4())
# INSERT INTO token_map (token_id, field_name, original_hash, global_id)
```

**역방향 (token → global_id)**: token_service.py `/detokenize/{token_id}` 엔드포인트

---

## 토큰 서비스 API

**위치**: ls-token (192.168.56.12) systemd `tokenization.service`, 포트 8000

| 엔드포인트 | 메소드 | 용도 |
|---|---|---|
| `/health` | GET | 헬스체크 |
| `/tokenize` | POST | 신규 토큰 발급 (또는 기존 반환) |
| `/detokenize/{token_id}` | GET | 토큰 → 원본 조회 |

**ALLOWED_FIELDS**: `resident_number`, `phone_number`, `account_number`, `card_number`, `email`
(현재 `global_id` 토큰은 batch 스크립트로 직접 INSERT — API 미사용)

---

## 데이터 흐름 요약

```
[온프레미스 ls-db]
  ┌────────────────────────────────┐
  │ users               (평문 PII) │ ← consent_completed = 동의 요약
  │ master_customer     (마스터)   │
  │ customer_pii_secure (AES-256)  │ ← 5필드 암호화 저장
  │ customer_360_profile (분석용)  │
  │ customer_identity_map (매핑)   │
  │ consent             (동의 이력) │ ← domain별 Y/N + 일시
  │ matching_audit_log  (감사)     │
  │ token_map (global_id ↔ UUID)   │ ← AWS 송신 keying
  └────────────────────────────────┘
                │
                ▼  (token_id 만 송신, global_id 미송신)
        ┌──────────────┐
        │  AWS  (분석)  │
        └──────────────┘
```
