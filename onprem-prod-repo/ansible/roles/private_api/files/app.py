import base64
import hashlib
import boto3
import json
import os
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import pymysql
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dbutils.pooled_db import PooledDB
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

DEPLOY_TOKEN = os.environ['DEPLOY_TOKEN']
REGION = 'ap-northeast-2'
SECRET_ID = 'lifesync/onprem-db'
DB_NAME = 'lifesync_onprem'

DB_POOL_MIN     = int(os.environ.get('DB_POOL_MIN', '2'))
DB_POOL_MAX     = int(os.environ.get('DB_POOL_MAX', '10'))
DB_POOL_MAXIDLE = int(os.environ.get('DB_POOL_MAXIDLE', '5'))

# Local lab VM 매핑 (host:port TCP 헬스용). 운영 환경 변경 시 env override.
VM_HOSTS = {
    'ls-db':    (os.environ.get('VM_LS_DB_HOST',    '192.168.56.11'), int(os.environ.get('VM_LS_DB_PORT',    '3306'))),
    'ls-token': (os.environ.get('VM_LS_TOKEN_HOST', '192.168.56.12'), int(os.environ.get('VM_LS_TOKEN_PORT', '8000'))),
    'ls-api':   (os.environ.get('VM_LS_API_HOST',   '192.168.56.13'), int(os.environ.get('VM_LS_API_PORT',   '80'))),
}
TOKENIZATION_HEALTH_URL = os.environ.get('TOKENIZATION_HEALTH_URL', 'http://192.168.56.12:8000/health')

# schema_reference.md 기준 8 테이블
_ONPREM_TABLES = [
    'users', 'master_customer', 'customer_pii_secure', 'customer_360_profile',
    'customer_identity_map', 'consent', 'matching_audit_log', 'token_map',
]

_aesgcm = None

def get_aesgcm():
    global _aesgcm
    if _aesgcm is None:
        key_b64 = os.environ.get('TOKEN_AES_KEY_B64')
        if not key_b64:
            secret  = boto3.client('secretsmanager', region_name=REGION).get_secret_value(SecretId=SECRET_ID)
            key_b64 = json.loads(secret['SecretString'])['token_aes_key_b64']
        _aesgcm = AESGCM(base64.b64decode(key_b64))
    return _aesgcm

def encrypt_pii(value):
    if value is None or value == '':
        return None
    iv = os.urandom(12)
    ct = get_aesgcm().encrypt(iv, value.encode('utf-8'), None)
    return base64.b64encode(iv + ct).decode('ascii')

def decrypt_pii(enc_b64):
    if not enc_b64:
        return None
    raw = base64.b64decode(enc_b64)
    return get_aesgcm().decrypt(raw[:12], raw[12:], None).decode('utf-8')

def pii_token_of(global_id):
    return 'PII-' + hashlib.sha256(global_id.encode('utf-8')).hexdigest().upper()[:16]

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


_db_pool = PooledDB(
    creator        = pymysql,
    mincached      = DB_POOL_MIN,
    maxcached      = DB_POOL_MAXIDLE,
    maxconnections = DB_POOL_MAX,
    blocking       = True,        # pool 고갈 시 대기 (drop 대신)
    ping           = 1,           # 매 checkout 시 SELECT 1 (stale 방지)
    host           = os.environ['DB_HOST'],
    user           = os.environ['DB_USER'],
    password       = os.environ['DB_PASS'],
    database       = DB_NAME,
    cursorclass    = pymysql.cursors.DictCursor,
    charset        = 'utf8mb4',
    autocommit     = False,
)


def get_db():
    """pool 에서 connection 반환. 기존 호출자는 그대로 — db.close() 는 pool 반환."""
    return _db_pool.connection()


def _ndjson_stream(sql, params):
    """SSDictCursor 서버사이드 커서로 행을 NDJSON 줄단위 스트림 (대용량 메모리 안전)."""
    def gen():
        db = get_db()
        try:
            with db.cursor(pymysql.cursors.SSDictCursor) as cur:
                cur.execute(sql, params)
                for row in cur:
                    yield json.dumps(row, ensure_ascii=False,
                                     default=lambda o: o.isoformat() if hasattr(o, 'isoformat') else str(o)) + '\n'
        finally:
            db.close()
    return StreamingResponse(gen(), media_type='application/x-ndjson')


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _tcp_check(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_check(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError):
        return False


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/internal/customer/{global_id}')
def get_customer(global_id: str):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'SELECT * FROM master_customer WHERE global_id = %s', (global_id,)
            )
            customer = cur.fetchone()
            if not customer:
                raise HTTPException(status_code=404, detail='Customer not found')

            cur.execute(
                'SELECT domain, source_customer_id, created_dt FROM customer_identity_map WHERE global_id = %s',
                (global_id,)
            )
            customer['identities'] = cur.fetchall()

            cur.execute(
                'SELECT lifesync_score, health_score, finance_score, asset_score, last_calc_dt FROM customer_360_profile WHERE global_id = %s',
                (global_id,)
            )
            customer['profile'] = cur.fetchone()
    finally:
        db.close()
    return customer


@app.get('/internal/profile/list-all')
def list_profile_all(page: int = 0, size: int = 10000, after: str = None):
    """
    customer_360_profile 전체 분포 페이지 조회 (analytics_aggregator batch 용).
    1M 행을 sync invoke 6MB 응답 제한에 맞추기 위해 페이지네이션.
    after(global_id 커서) 지정 시 keyset, 미지정 시 기존 OFFSET. items < size 면 마지막.
    """
    if size < 1 or size > 50000:
        raise HTTPException(status_code=400, detail='size: 1~50000 범위')
    if after is None and page < 0:
        raise HTTPException(status_code=400, detail='page: 0 이상')
    base = ('SELECT global_id, gender, age_band, region, income_grade, asset_grade '
            'FROM customer_360_profile ')
    if after is None:
        sql, params = base + 'ORDER BY global_id LIMIT %s OFFSET %s', (size, page * size)
    else:
        sql, params = base + 'WHERE global_id > %s ORDER BY global_id LIMIT %s', (after, size)
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        db.close()
    return {'page': page, 'size': size, 'count': len(rows), 'items': rows,
            'next_after': rows[-1]['global_id'] if rows else None}


@app.get('/internal/consent/list-all')
def list_consent_all(page: int = 0, size: int = 10000, after: str = None):
    """
    consent 스냅샷 배치용 — users + consent JOIN 페이지 조회 (user 페이지 단위).

    user 1명당 1 row, consents 는 JSON_ARRAYAGG 로 8 도메인 묶음.
    after(global_id 커서) 지정 시 keyset, 미지정 시 기존 OFFSET.
    """
    if size < 1 or size > 50000:
        raise HTTPException(status_code=400, detail='size: 1~50000 범위')
    if after is None and page < 0:
        raise HTTPException(status_code=400, detail='page: 0 이상')
    base = (
        'SELECT u.global_id, u.ls_user_id, u.user_status, '
        '       (SELECT JSON_ARRAYAGG(JSON_OBJECT('
        '            \'domain\',        c.domain, '
        '            \'consent_flag\',  c.consent_flag, '
        '            \'consent_version\', c.consent_version, '
        '            \'consent_dt\',    c.consent_dt, '
        '            \'revoke_dt\',     c.revoke_dt)) '
        '        FROM consent c WHERE c.global_id = u.global_id) AS consents '
        'FROM users u '
        "WHERE u.user_status = 'ACTIVE' "
    )
    if after is None:
        sql, params = base + 'ORDER BY u.global_id LIMIT %s OFFSET %s', (size, page * size)
    else:
        sql, params = base + 'AND u.global_id > %s ORDER BY u.global_id LIMIT %s', (after, size)
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        db.close()
    # consents 는 MySQL이 JSON 문자열로 반환할 수 있으므로 dict로 정규화
    for r in rows:
        if isinstance(r.get('consents'), str):
            r['consents'] = json.loads(r['consents']) if r['consents'] else []
        elif r.get('consents') is None:
            r['consents'] = []
    return {'page': page, 'size': size, 'count': len(rows), 'items': rows,
            'next_after': rows[-1]['global_id'] if rows else None}


@app.get('/internal/consent/active')
def consent_active_stream():
    """현재 동의(consent_flag='Y' AND revoke_dt IS NULL) NDJSON 스트림 — identity_enricher 용.
    /internal/consent/{global_id} 보다 먼저 등록돼야 'active' 가 global_id 로 안 먹힘."""
    return _ndjson_stream(
        "SELECT global_id, domain, consent_version, consent_dt "
        "FROM consent WHERE consent_flag = 'Y' AND revoke_dt IS NULL",
        (),
    )


@app.get('/internal/identity-map')
def identity_map_stream(domain: str):
    """domain(LONG/SHORT 모두 허용, DOMAIN_ALIAS 로 SHORT 정규화)별 active 매핑 NDJSON 스트림."""
    d = DOMAIN_ALIAS.get(domain.upper(), domain.upper())
    return _ndjson_stream(
        "SELECT source_customer_id, global_id FROM customer_identity_map "
        "WHERE domain = %s AND active_flag = 'Y'",
        (d,),
    )


@app.get('/internal/consent/{global_id}')
def get_consent(global_id: str):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'SELECT domain, consent_flag, consent_version, revoke_dt, consent_dt FROM consent WHERE global_id = %s',
                (global_id,)
            )
            rows = cur.fetchall()
    finally:
        db.close()
    return {'global_id': global_id, 'consents': rows}


@app.get('/internal/identity/{source_customer_id}')
def get_identity(source_customer_id: str, domain: str):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'SELECT global_id FROM customer_identity_map WHERE source_customer_id = %s AND domain = %s',
                (source_customer_id, domain)
            )
            row = cur.fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(status_code=404, detail='Identity mapping not found')
    return row


# ── 인증 엔드포인트 ───────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post('/internal/auth/login')
def auth_login(req: LoginRequest):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute('SELECT * FROM users WHERE login_email = %s', (req.email,))
            user = cur.fetchone()
    finally:
        db.close()
    if not user or hash_password(req.password) != user['password_hash']:
        raise HTTPException(status_code=401, detail='이메일 또는 비밀번호 불일치')
    return {
        'ls_user_id':   user['ls_user_id'],
        'global_id':    user['global_id'],
        'login_email':  user['login_email'],
    }


class SetPasswordRequest(BaseModel):
    email: str
    new_password: str

@app.post('/internal/auth/set-password')
def auth_set_password(req: SetPasswordRequest):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'UPDATE users SET password_hash = %s WHERE login_email = %s',
                (hash_password(req.new_password), req.email)
            )
            affected = cur.rowcount
            db.commit()
    finally:
        db.close()
    if affected == 0:
        raise HTTPException(status_code=404, detail='사용자 없음')
    return {'status': 'ok', 'email': req.email}


class RegisterRequest(BaseModel):
    ls_user_id:    str
    global_id:     str
    email:         str
    password_hash: str
    name:          Optional[str] = None
    mobile:        Optional[str] = None
    address:       Optional[str] = None
    # rrn (주민번호) — 운영 미수집 (2026-05-18 ③ 결정). DDL `rrn_enc` 컬럼은 nullable 유지

@app.post('/internal/auth/register')
def auth_register(req: RegisterRequest):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'INSERT INTO master_customer (global_id) VALUES (%s)',
                (req.global_id,)
            )
            cur.execute(
                'INSERT INTO users (ls_user_id, global_id, login_email, password_hash, mobile) VALUES (%s, %s, %s, %s, %s)',
                (req.ls_user_id, req.global_id, req.email, req.password_hash, req.mobile)
            )
            # rrn_enc 컬럼은 미명시 → DB default NULL (운영 미수집 정책)
            cur.execute(
                '''INSERT INTO customer_pii_secure
                       (pii_token, global_id, customer_name_enc, mobile_enc, email_enc, address_enc)
                   VALUES (%s, %s, %s, %s, %s, %s)''',
                (
                    pii_token_of(req.global_id), req.global_id,
                    encrypt_pii(req.name), encrypt_pii(req.mobile),
                    encrypt_pii(req.email), encrypt_pii(req.address),
                )
            )
            db.commit()
    finally:
        db.close()
    return {'status': 'ok', 'ls_user_id': req.ls_user_id, 'global_id': req.global_id}


@app.get('/internal/pii/{global_id}')
def get_pii(global_id: str):
    """PII 4 필드 복호화 반환 — rrn 은 운영 미수집 정책으로 응답 제외."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'SELECT customer_name_enc, mobile_enc, email_enc, address_enc'
                ' FROM customer_pii_secure WHERE global_id = %s',
                (global_id,)
            )
            row = cur.fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(status_code=404, detail='PII 정보 없음')
    return {
        'global_id': global_id,
        'name':      decrypt_pii(row['customer_name_enc']),
        'mobile':    decrypt_pii(row['mobile_enc']),
        'email':     decrypt_pii(row['email_enc']),
        'address':   decrypt_pii(row['address_enc']),
    }


@app.get('/internal/pii-masked/{global_id}')
def pii_masked_proxy(global_id: str):
    """ls-token /pii-masked 프록시 — PII 복호화 키는 ls-token만 보유, 마스킹값만 전달."""
    host, port = VM_HOSTS['ls-token']
    url = f'http://{host}:{port}/pii-masked/{urllib.parse.quote(global_id, safe="")}'
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=e.code, detail='tokenization pii-masked 오류')
    except (urllib.error.URLError, OSError):
        raise HTTPException(status_code=502, detail='tokenization 서버 연결 실패')


@app.get('/internal/auth/user/by_global/{global_id}')
def auth_get_user_by_global(global_id: str):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'SELECT ls_user_id, global_id, login_email FROM users WHERE global_id = %s LIMIT 1',
                (global_id,)
            )
            user = cur.fetchone()
    finally:
        db.close()
    if not user:
        raise HTTPException(status_code=404, detail='사용자 없음')
    return user


@app.get('/internal/auth/user/{ls_user_id}')
def auth_get_user(ls_user_id: str):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'SELECT ls_user_id, global_id, login_email FROM users WHERE ls_user_id = %s',
                (ls_user_id,)
            )
            user = cur.fetchone()
    finally:
        db.close()
    if not user:
        raise HTTPException(status_code=404, detail='사용자 없음')
    return user


class ConsentSaveRequest(BaseModel):
    global_id: str
    consents:  list

DOMAIN_ALIAS = {
    'SECURITIES': 'SEC',
    'INSURANCE':  'INS',
    'ONLINE_INS': 'ONINS',
    'ONLINE_INSURANCE': 'ONINS',
    'HEALTHCARE': 'HLT',
    'HOSPITAL':   'HOS',
    'WEARABLE':   'WBL',
}

ALL_CONSENT_KEYS = ['BANK', 'CARD', 'SEC', 'INS', 'ONINS', 'HLT', 'HOS', 'WBL']

@app.post('/internal/auth/consent')
def auth_save_consent(req: ConsentSaveRequest):
    checked = {DOMAIN_ALIAS.get(c, c) for c in req.consents}
    db = get_db()
    try:
        with db.cursor() as cur:
            for key in ALL_CONSENT_KEYS:
                if key in checked:
                    cur.execute(
                        '''INSERT INTO consent (global_id, domain, consent_flag, consent_dt, revoke_dt)
                           VALUES (%s, %s, 'Y', NOW(), NULL)
                           ON DUPLICATE KEY UPDATE
                               consent_flag = 'Y',
                               consent_dt   = COALESCE(consent_dt, NOW()),
                               revoke_dt    = NULL''',
                        (req.global_id, key)
                    )
                else:
                    cur.execute(
                        '''INSERT INTO consent (global_id, domain, consent_flag)
                           VALUES (%s, %s, 'N')
                           ON DUPLICATE KEY UPDATE
                               consent_flag = 'N',
                               revoke_dt    = IF(consent_dt IS NOT NULL AND revoke_dt IS NULL, NOW(), revoke_dt)''',
                        (req.global_id, key)
                    )
            db.commit()
    finally:
        db.close()
    return {'status': 'ok'}


@app.post('/internal/deploy')
async def trigger_deploy(request: Request):
    if request.headers.get('X-Deploy-Token', '') != DEPLOY_TOKEN:
        raise HTTPException(status_code=401, detail='배포 토큰 불일치')
    subprocess.Popen(['/opt/private-api/trigger_ansible.sh'])
    return {'status': 'triggered'}


# ── P1 카운트 (admin 통합 KPI) ────────────────────────────

@app.get('/internal/count/master_customer')
def count_master_customer(status: str = 'ACTIVE'):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute('SELECT COUNT(*) AS cnt FROM master_customer WHERE customer_status = %s', (status,))
            row = cur.fetchone()
    finally:
        db.close()
    return {'status': status, 'count': row['cnt']}


@app.get('/internal/count/users')
def count_users(status: str = 'ACTIVE'):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute('SELECT COUNT(*) AS cnt FROM users WHERE user_status = %s', (status,))
            row = cur.fetchone()
    finally:
        db.close()
    return {'status': status, 'count': row['cnt']}


@app.get('/internal/count/users_consented')
def count_users_consented():
    """active 회원 중 1개 도메인 이상에서 현재 동의 상태(Y + revoke_dt IS NULL)인 ls_user_id 카운트."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'SELECT COUNT(DISTINCT u.ls_user_id) AS cnt '
                'FROM users u JOIN consent c ON u.global_id = c.global_id '
                "WHERE u.user_status = 'ACTIVE' AND c.consent_flag = 'Y' AND c.revoke_dt IS NULL"
            )
            row = cur.fetchone()
    finally:
        db.close()
    return {'count': row['cnt']}


# ── P2 단건 조회 (admin 고객 상세) ────────────────────────

@app.get('/internal/master_customer/{global_id}')
def get_master_customer(global_id: str):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute('SELECT * FROM master_customer WHERE global_id = %s', (global_id,))
            row = cur.fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(status_code=404, detail='Customer not found')
    return row


@app.get('/internal/identity_map/{global_id}')
def get_identity_map(global_id: str):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'SELECT domain, source_customer_id, created_dt '
                'FROM customer_identity_map '
                "WHERE global_id = %s AND active_flag = 'Y' "
                'ORDER BY domain',
                (global_id,)
            )
            rows = cur.fetchall()
    finally:
        db.close()
    return {'global_id': global_id, 'identities': rows}


# ── P4 헬스 체크 (admin Network 페이지) ────────────────────

@app.get('/internal/health/vm/{vm_id}')
def health_vm(vm_id: str):
    if vm_id not in VM_HOSTS:
        raise HTTPException(status_code=404, detail=f'Unknown vm_id: {vm_id}')
    host, port = VM_HOSTS[vm_id]
    ok = _tcp_check(host, port)
    return {
        'vm_id':  vm_id,
        'host':   host,
        'port':   port,
        'status': 'pass' if ok else 'fail',
        'time':   _now_iso(),
    }


@app.get('/internal/health/mysql')
def health_mysql():
    """local MySQL 헬스 — schema_reference 기준 8 테이블 존재 확인."""
    try:
        db = get_db()
        try:
            with db.cursor() as cur:
                cur.execute('SHOW TABLES')
                tables = {list(r.values())[0] for r in cur.fetchall()}
        finally:
            db.close()
    except Exception as e:
        return {'status': 'fail', 'time': _now_iso(), 'error': str(e)[:120]}
    missing = [t for t in _ONPREM_TABLES if t not in tables]
    return {
        'status':  'pass' if not missing else 'warn',
        'time':    _now_iso(),
        'tables':  sorted(tables),
        'missing': missing,
    }


@app.get('/internal/health/tokenization')
def health_tokenization():
    ok = _http_check(TOKENIZATION_HEALTH_URL)
    return {
        'status':   'pass' if ok else 'fail',
        'time':     _now_iso(),
        'endpoint': TOKENIZATION_HEALTH_URL,
    }


@app.get('/internal/health/local-lab')
def health_local_lab():
    """4 VM TCP + MySQL + Tokenization 종합. Lambda local_lab_status 가 호출 → admin ops 페이지."""
    envs   = []
    checks = {}

    for vm_id, (host, port) in VM_HOSTS.items():
        ok = _tcp_check(host, port)
        checks[f'vm:{vm_id}'] = [{
            'status':        'pass' if ok else 'fail',
            'componentType': 'system',
            'observedValue': f'{host}:{port}',
            'time':          _now_iso(),
        }]
        envs.append({
            'env':   f'VirtualBox · {vm_id}',
            'state': 'Running' if ok else 'Down',
            'note':  f'{host}:{port}',
        })

    mysql_resp = health_mysql()
    checks['service:mysql'] = [{
        'status':        mysql_resp['status'],
        'componentType': 'datastore',
        'observedValue': f"{len(mysql_resp.get('tables', []))} tables",
        'time':          mysql_resp['time'],
    }]

    tok_resp = health_tokenization()
    checks['service:tokenization'] = [{
        'status':        tok_resp['status'],
        'componentType': 'component',
        'observedValue': tok_resp['endpoint'],
        'time':          tok_resp['time'],
    }]

    return {
        'environments': envs,
        'checks':       checks,
    }


class MatchRequest(BaseModel):
    domain:             str
    source_customer_id: str
    global_id:          str


@app.post('/internal/match')
def match_identity(req: MatchRequest):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                '''INSERT INTO customer_identity_map (global_id, domain, source_customer_id)
                   VALUES (%s, %s, %s)
                   ON DUPLICATE KEY UPDATE source_customer_id = VALUES(source_customer_id)''',
                (req.global_id, req.domain, req.source_customer_id)
            )
            cur.execute(
                '''INSERT INTO matching_audit_log (request_id, ls_user_id, match_rule, result, matched_global_id)
                   VALUES (%s, %s, %s, %s, %s)''',
                (
                    str(uuid.uuid4()),
                    req.source_customer_id,
                    req.domain,
                    'MATCH',
                    req.global_id,
                )
            )
            db.commit()
    finally:
        db.close()
    return {'status': 'ok', 'global_id': req.global_id}
