import base64
import boto3
import hashlib
import json
import os
import uuid
import pymysql
from dbutils.pooled_db import PooledDB
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

REGION = 'ap-northeast-2'
SECRET_ID = 'lifesync/onprem-db'
DB_NAME = 'lifesync_onprem'
MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')

DB_POOL_MIN     = int(os.environ.get('DB_POOL_MIN', '2'))
DB_POOL_MAX     = int(os.environ.get('DB_POOL_MAX', '10'))
DB_POOL_MAXIDLE = int(os.environ.get('DB_POOL_MAXIDLE', '5'))

ALLOWED_FIELDS = {'resident_number', 'phone_number', 'account_number', 'card_number', 'email'}


def _resolve_db_creds():
    db_user = os.environ.get('DB_USER')
    db_pass = os.environ.get('DB_PASS')
    if not db_user or not db_pass:
        secret = boto3.client('secretsmanager', region_name=REGION).get_secret_value(SecretId=SECRET_ID)
        creds = json.loads(secret['SecretString'])
        db_user, db_pass = creds['username'], creds['password']
    return db_user, db_pass


_DB_USER, _DB_PASS = _resolve_db_creds()

_db_pool = PooledDB(
    creator        = pymysql,
    mincached      = DB_POOL_MIN,
    maxcached      = DB_POOL_MAXIDLE,
    maxconnections = DB_POOL_MAX,
    blocking       = True,        # pool 고갈 시 대기 (drop 대신)
    ping           = 1,           # 매 checkout 시 SELECT 1 (stale 방지)
    host           = MYSQL_HOST,
    user           = _DB_USER,
    password       = _DB_PASS,
    database       = DB_NAME,
    cursorclass    = pymysql.cursors.DictCursor,
    charset        = 'utf8mb4',
    autocommit     = False,
)


def get_db():
    """pool 에서 connection 반환. db.close() 는 pool 반환."""
    return _db_pool.connection()


class TokenizeRequest(BaseModel):
    field: str
    value: str
    global_id: str = None


class TokenizeResponse(BaseModel):
    token_id: str


@app.post('/tokenize', response_model=TokenizeResponse)
def tokenize(req: TokenizeRequest):
    if req.field not in ALLOWED_FIELDS:
        raise HTTPException(status_code=400, detail=f"Field '{req.field}' not in allowed fields")

    original_hash = hashlib.sha256(req.value.encode()).hexdigest()

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute('SELECT token_id FROM token_map WHERE original_hash = %s', (original_hash,))
            row = cur.fetchone()
            if row:
                return TokenizeResponse(token_id=row['token_id'])

            token_id = str(uuid.uuid4())
            cur.execute(
                'INSERT INTO token_map (token_id, field_name, original_hash, global_id) VALUES (%s, %s, %s, %s)',
                (token_id, req.field, original_hash, req.global_id)
            )
            db.commit()
    finally:
        db.close()

    return TokenizeResponse(token_id=token_id)


@app.get('/detokenize/{token_id}')
def detokenize(token_id: str):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'SELECT field_name, global_id, created_dt FROM token_map WHERE token_id = %s',
                (token_id,)
            )
            row = cur.fetchone()
    finally:
        db.close()

    if not row:
        raise HTTPException(status_code=404, detail='Token not found')
    return {'token_id': token_id, **row}


_aesgcm = None


def _get_aesgcm():
    global _aesgcm
    if _aesgcm is None:
        kb = os.environ.get('TOKEN_AES_KEY_B64')
        if not kb:
            raise HTTPException(status_code=500, detail='TOKEN_AES_KEY_B64 not configured')
        _aesgcm = AESGCM(base64.urlsafe_b64decode(kb))
    return _aesgcm


def _dec(enc_b64):
    if not enc_b64:
        return None
    raw = base64.b64decode(enc_b64)
    return _get_aesgcm().decrypt(raw[:12], raw[12:], None).decode('utf-8')


def _mask_name(s):
    if not s:
        return s
    n = len(s)
    if n == 1:
        return '*'
    if n == 2:
        return s[0] + '*'
    return s[0] + '*' * (n - 2) + s[-1]


def _mask_email(s):
    if not s or '@' not in s:
        return '***'
    loc, dom = s.split('@', 1)
    return (loc[:2] if len(loc) >= 2 else loc[:1]) + '***@' + dom


def _mask_mobile(s):
    if not s:
        return s
    d = ''.join(ch for ch in s if ch.isdigit())
    if len(d) < 7:
        return '***'
    return d[:3] + '-****-' + d[-4:]


def _mask_address(s):
    if not s:
        return s
    parts = s.split()
    return (' '.join(parts[:2]) + ' ***') if parts else '***'


@app.get('/pii-masked/{global_id}')
def pii_masked(global_id: str):
    """customer_pii_secure 복호화 후 마스킹값만 반환 (평문 미반출, rrn 제외)."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'SELECT p.customer_name_enc, p.mobile_enc, p.email_enc, p.address_enc, '
                'u.ls_user_id '
                'FROM customer_pii_secure p '
                'LEFT JOIN users u ON u.global_id = p.global_id '
                'WHERE p.global_id = %s',
                (global_id,)
            )
            row = cur.fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(status_code=404, detail='PII not found')
    return {
        'global_id':  global_id,
        'ls_user_id': row['ls_user_id'],
        'name':       _mask_name(_dec(row['customer_name_enc'])),
        'mobile':     _mask_mobile(_dec(row['mobile_enc'])),
        'email':      _mask_email(_dec(row['email_enc'])),
        'address':    _mask_address(_dec(row['address_enc'])),
    }


@app.get('/health')
def health():
    return {'status': 'ok'}
