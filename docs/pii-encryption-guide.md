# PII 암호화 적용 가이드

대상 테이블: `master_customer` (ls-db, 192.168.56.11)
암호화 컬럼: `representative_name`, `birth_dt`
방식: Fernet AES-128 (`cryptography` 라이브러리)
키 관리: `PII_AES_KEY` 환경변수 → Ansible Vault 보관

---

## 전체 순서

| 단계 | 내용 | 실행 위치 |
|------|------|-----------|
| 1 | 암호화 키 생성 | ls-vpngw |
| 2 | Vault 파일 생성 | ls-vpngw |
| 3 | 코드 수정 5개 파일 | 개발 PC |
| 4 | ls-db 컬럼 타입 변경 | ls-db |
| 5 | 마이그레이션 스크립트 실행 | ls-db |
| 6 | Ansible 재배포 | ls-vpngw |
| 7 | 검증 | ls-vpngw |
| 8 | Ansible Vault 암호화 | ls-vpngw |

---

## 1단계 — 암호화 키 생성

```bash
ssh ansible@192.168.56.10
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 출력 예시: ZmFrZWtleWZha2VrZmFrZWtleWZha2Vr...==
# 이 값을 복사해 2단계에서 사용. 잃어버리면 복호화 불가.
```

---

## 2단계 — Ansible Vault 파일 생성 (ls-vpngw)

```bash
cd /opt/ansible/onprem-prod-repo
mkdir -p ansible/inventory/group_vars/private_api

cat > ansible/inventory/group_vars/private_api/vault.yml << 'EOF'
vault_pii_aes_key: "<1단계에서 생성한 키>"
EOF
```

---

## 3단계 — 코드 수정

### 3-1. `onprem-prod-repo/ansible/inventory/hosts.yml`

`private_api` 섹션 ls-api 호스트에 변수 추가:

```yaml
private_api:
  hosts:
    ls-api:
      ansible_host: 192.168.56.13
      pii_aes_key: "{{ vault_pii_aes_key }}"   # 추가
```

### 3-2. `onprem-prod-repo/ansible/roles/private_api/templates/private-api.service.j2`

마지막 `Environment=CONTROL_NODE_URL=...` 줄 아래에 추가:

```
Environment=ENV=production
Environment=ANSIBLE_ENV=production
Environment=AWS_DEFAULT_REGION=ap-northeast-2
Environment=DEPLOY_TOKEN={{ deploy_token }}
Environment=CONTROL_NODE_URL={{ control_node_url }}
Environment=PII_AES_KEY={{ pii_aes_key }}    ← 추가
```

### 3-3. `onprem-prod-repo/ansible/roles/private_api/tasks/main.yml`

`Install Python dependencies` 태스크 pip 리스트에 `cryptography` 추가:

```yaml
- name: Install Python dependencies
  pip:
    name:
      - fastapi
      - uvicorn
      - boto3
      - pymysql
      - cryptography    # 추가
    virtualenv: /opt/private-api/venv
```

### 3-4. `onprem-prod-repo/ansible/roles/private_api/files/app.py`

**상단 import에 추가:**
```python
from cryptography.fernet import Fernet
```

**`get_db()` 함수 위에 추가:**
```python
def get_pii_key():
    key = os.environ.get('PII_AES_KEY')
    if not key:
        secret = boto3.client('secretsmanager', region_name=REGION).get_secret_value(SecretId=SECRET_ID)
        key = json.loads(secret['SecretString'])['pii_aes_key']
    return Fernet(key.encode())

def decrypt_pii(val):
    if not val:
        return None
    return get_pii_key().decrypt(val.encode()).decode('utf-8')
```

**`/internal/customer/{global_id}` 엔드포인트 — `customer = cur.fetchone()` 이후에 추가:**
```python
customer = cur.fetchone()
if not customer:
    raise HTTPException(status_code=404, detail='Customer not found')
customer['representative_name'] = decrypt_pii(customer['representative_name'])
customer['birth_dt'] = decrypt_pii(customer['birth_dt'])
```

### 3-5. `db/onprem_schema.sql`

`master_customer` 테이블 컬럼 타입 변경:

```sql
-- 변경 전
representative_name  VARCHAR(100),
birth_dt             DATE,

-- 변경 후
representative_name  VARCHAR(300),
birth_dt             VARCHAR(100),
```

---

## 4단계 — ls-db 컬럼 타입 변경

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

---

## 5단계 — 마이그레이션 스크립트 실행

ls-vpngw(control node) 한 곳에서만 실행. `DB_HOST`로 ls-db MySQL에 원격 접속하므로 ls-db에 직접 들어갈 필요 없음.

**스크립트 내용** (`db/migrate_pii_encrypt.py`):

```python
#!/usr/bin/env python3
"""
master_customer.representative_name, birth_dt 를 Fernet AES 암호화.
실행 전 환경변수 설정 필요:
  export PII_AES_KEY=<1단계에서 생성한 키>
  export DB_PASS=<MySQL root 패스워드>
"""
import os, pymysql
from cryptography.fernet import Fernet

BATCH = 10_000
f     = Fernet(os.environ['PII_AES_KEY'].encode())

def enc(val):
    if val is None:
        return None
    return f.encrypt(str(val).encode('utf-8')).decode('utf-8')

conn = pymysql.connect(
    host=os.environ.get('DB_HOST', '127.0.0.1'),
    user=os.environ.get('DB_USER', 'root'),
    password=os.environ['DB_PASS'],
    database='lifesync_onprem',
    cursorclass=pymysql.cursors.DictCursor
)
try:
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS cnt FROM master_customer')
        total = cur.fetchone()['cnt']
        print(f'총 {total:,}건 처리 시작')

    offset, done = 0, 0
    while True:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT global_id, representative_name, birth_dt FROM master_customer LIMIT %s OFFSET %s',
                (BATCH, offset)
            )
            rows = cur.fetchall()
        if not rows:
            break

        with conn.cursor() as cur:
            cur.executemany(
                'UPDATE master_customer SET representative_name=%s, birth_dt=%s WHERE global_id=%s',
                [(enc(r['representative_name']),
                  enc(str(r['birth_dt']) if r['birth_dt'] else None),
                  r['global_id']) for r in rows]
            )
        conn.commit()
        done += len(rows)
        offset += BATCH
        print(f'{done:,} / {total:,}')
finally:
    conn.close()
print('암호화 완료')
```

**ls-vpngw에서 실행:**

```bash
# 의존성 설치 (최초 1회)
pip3 install cryptography pymysql --break-system-packages

# 실행 (약 5~10분 소요)
export PII_AES_KEY=<1단계 키>
export DB_HOST=192.168.56.11
export DB_USER=lifesync
export DB_PASS=<MySQL lifesync 계정 패스워드>
python3 /opt/ansible/onprem-prod-repo/db/migrate_pii_encrypt.py
```

**완료 확인:**
```sql
-- 암호화된 값(gAAAAAB...) 이 보이면 정상
SELECT global_id, representative_name FROM master_customer LIMIT 3;
```

---

## 6단계 — Ansible 재배포 (ls-api)

```bash
# ls-vpngw에서
cd /opt/ansible/onprem-prod-repo
git pull
ansible-playbook ansible/site.yml -i ansible/inventory/hosts.yml --limit ls-api --ask-vault-pass
```

---

## 7단계 — 검증

```bash
# ls-vpngw 또는 동일 네트워크에서
curl http://192.168.56.13/internal/customer/G000000001
```

정상 응답:
```json
{
  "global_id": "G000000001",
  "representative_name": "홍길동",
  "birth_dt": "1990-01-01",
  ...
}
```

실패 시 확인:
```bash
ssh ansible@192.168.56.13
sudo systemctl status private-api
sudo journalctl -u private-api -n 50
# PII_AES_KEY 환경변수 미적용 → 서비스 재시작
sudo systemctl restart private-api
```

---

## 8단계 — Ansible Vault 암호화

```bash
# ls-vpngw에서
cd /opt/ansible/onprem-prod-repo
ansible-vault encrypt ansible/inventory/group_vars/private_api/vault.yml
# vault 패스워드 입력 및 기억 (tokenization vault와 동일 패스워드 권장)

git add ansible/inventory/group_vars/private_api/
git commit -m "feat(vault): private_api PII 암호화 키 vault 보호 적용"
git push
```

이후 ansible-playbook 실행 시:
```bash
ansible-playbook ansible/site.yml -i ansible/inventory/hosts.yml --ask-vault-pass
```
