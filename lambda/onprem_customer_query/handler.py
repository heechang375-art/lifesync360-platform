"""
온프레미스 고객 데이터 조회 Lambda — Platform VPC 배치
VPN을 통해 온프레미스 Private API 직접 호출

event = {
    "action": "login"|"register"|"get_user"|"get_consent"|"save_consent"|"get_profile"|"get_pii"|"get_all"
            | "local_lab_status"
            | "count_master_customer" | "count_users" | "count_users_consented"
            | "get_master_customer" | "get_identity_map"
            | "vm_health" | "mysql_health" | "tokenization_health"
            | "list_profile_page" | "list_consent_page",
    ...params
}

응답 형식: { statusCode, body(JSON string) }
- local_lab_status 의 body 는 RFC draft (api-health-check-06) 부분 호환 + admin 호환:
  {
    "status": "pass" | "fail" | "warn",      # aggregate
    "time":   "2026-05-17T15:00:00Z",
    "environments": [                         # admin 호환 (admin _ping_local_lab 가 추출)
      { "env": "VirtualBox · ls-db", "state": "Running", "note": "MySQL 8.0 · 192.168.56.11" },
      ...
    ],
    "checks": {                                # RFC draft 표준
      "vm:ls-db":      [{ "status":"pass", "componentType":"system",    "time":"..." }],
      "service:mysql": [{ "status":"pass", "componentType":"datastore", "time":"..." }],
      ...
    }
  }
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PRIVATE_API_URL = os.environ['PRIVATE_API_URL']   # http://172.16.1.73


def _api_get(path):
    with urllib.request.urlopen(f'{PRIVATE_API_URL}{path}', timeout=8) as resp:
        return json.loads(resp.read())


def _api_post(path, payload):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f'{PRIVATE_API_URL}{path}',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read())


def _resp(status, body):
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body, ensure_ascii=False),
    }


def _now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _local_lab_status():
    """
    온프레미스 Private API /internal/health/local-lab 호출 → 응답 가공.
    PrivateAPI 응답 가정 (운영):
      { "environments": [ {"env","state","note"}, ... ],
        "checks":      { "vm:ls-db":[{...}], "service:mysql":[{...}], ... } }
    실패 시 status=fail + 빈 환경 반환 (admin 안 깨짐, RFC draft 호환).
    """
    try:
        raw = _api_get('/internal/health/local-lab')
        envs   = raw.get('environments') or []
        checks = raw.get('checks') or {}
        # aggregate status: 하나라도 fail 이면 fail, warn 하나라도 있으면 warn, 외엔 pass
        all_states = [c['status'] for arr in checks.values() for c in arr if isinstance(c, dict) and c.get('status')]
        if any(s == 'fail' for s in all_states):
            agg = 'fail'
        elif any(s == 'warn' for s in all_states):
            agg = 'warn'
        else:
            agg = 'pass'
        return {
            'status':       agg,
            'time':         _now_iso(),
            'environments': envs,
            'checks':       checks,
        }
    except Exception as e:
        return {
            'status':       'fail',
            'time':         _now_iso(),
            'environments': [],
            'checks':       {},
            'output':       f'PrivateAPI 호출 실패: {str(e)}',
        }


def handler(event, context):
    body   = json.loads(event['body']) if 'body' in event else event
    action = body.get('action')

    if not action:
        return _resp(400, {'error': '필수 필드 누락: action'})

    try:
        if action == 'login':
            result = _api_post('/internal/auth/login', {
                'email':    body['email'],
                'password': body['password'],
            })
        elif action == 'set_password':
            result = _api_post('/internal/auth/set-password', {
                'email':        body['email'],
                'new_password': body['new_password'],
            })
        elif action == 'register':
            # rrn (주민번호) 운영 미수집 — body 에 들어와도 PrivateAPI 로 전달하지 않음
            result = _api_post('/internal/auth/register', {
                'ls_user_id':    body['ls_user_id'],
                'global_id':     body['global_id'],
                'email':         body['email'],
                'password_hash': body['password_hash'],
                'name':          body.get('name'),
                'mobile':        body.get('mobile'),
                'address':       body.get('address'),
            })
        elif action == 'get_user':
            result = _api_get(f'/internal/auth/user/{body["ls_user_id"]}')
        elif action == 'get_user_by_global':
            result = _api_get(f'/internal/auth/user/by_global/{body["global_id"]}')
        elif action == 'get_consent':
            result = _api_get(f'/internal/consent/{body["global_id"]}')
        elif action == 'save_consent':
            result = _api_post('/internal/auth/consent', {
                'global_id': body['global_id'],
                'consents':  body['consents'],
            })
        elif action == 'get_profile':
            result = _api_get(f'/internal/customer/{body["global_id"]}')
        elif action == 'get_pii':
            result = _api_get(f'/internal/pii/{body["global_id"]}')
        elif action == 'get_pii_masked':
            result = _api_get(f'/internal/pii-masked/{body["global_id"]}')
        elif action == 'get_all':
            customer = _api_get(f'/internal/customer/{body["global_id"]}')
            consent  = _api_get(f'/internal/consent/{body["global_id"]}')
            result   = {
                'global_id': body['global_id'],
                'customer':  customer,
                'consents':  consent.get('consents', []),
            }
        elif action == 'local_lab_status':
            # P4 r38~43, r60. 온프레 환경/서비스 종합 헬스. HTTPError 발생 시에도
            # _local_lab_status 안에서 catch 해서 status=fail 형식으로 반환.
            result = _local_lab_status()

        # ── 통합 카운트 (P1 r3,4,5) ────────────────────────────
        elif action == 'count_master_customer':
            # P1 r3 — master_customer COUNT(*) WHERE customer_status='ACTIVE'
            result = _api_get('/internal/count/master_customer?status=ACTIVE')
        elif action == 'count_users':
            # P1 r4 — users COUNT(ls_user_id) WHERE user_status='ACTIVE'
            result = _api_get('/internal/count/users?status=ACTIVE')
        elif action == 'count_users_consented':
            # P1 r5 — users JOIN consent (active + consent_flag='Y' + revoke_dt IS NULL)
            result = _api_get('/internal/count/users_consented')

        # ── 단건 조회 (P2 r13~17, r22) ──────────────────────────
        elif action == 'get_master_customer':
            # P2 r13,r17 — master_customer 단건 (first_created_dt, customer_status)
            result = _api_get(f'/internal/master_customer/{body["global_id"]}')
        elif action == 'get_identity_map':
            # P2 r22 — customer_identity_map (active_flag='Y' 활성 계열사 + source_customer_id)
            result = _api_get(f'/internal/identity_map/{body["global_id"]}')

        # ── analytics batch (P3 r12,r13) ───────────────────────
        elif action == 'list_profile_page':
            # customer_360_profile 페이지 조회 — analytics_aggregator batch.
            # after(global_id 커서) 있으면 keyset, 없으면 page OFFSET (하위호환).
            size  = int(body.get('size', 10000))
            after = body.get('after')
            if after is not None:
                result = _api_get(f'/internal/profile/list-all?after={urllib.parse.quote(str(after), safe="")}&size={size}')
            else:
                page = int(body.get('page', 0))
                result = _api_get(f'/internal/profile/list-all?page={page}&size={size}')

        elif action == 'list_consent_page':
            # users + consent 페이지 조회 — consent_snapshot_aggregator 일배치.
            # after(global_id 커서) 있으면 keyset, 없으면 page OFFSET (하위호환).
            size  = int(body.get('size', 10000))
            after = body.get('after')
            if after is not None:
                result = _api_get(f'/internal/consent/list-all?after={urllib.parse.quote(str(after), safe="")}&size={size}')
            else:
                page = int(body.get('page', 0))
                result = _api_get(f'/internal/consent/list-all?page={page}&size={size}')

        # ── 단일 헬스 체크 (P4 r40,41,42) ───────────────────────
        elif action == 'vm_health':
            # P4 r40 — VirtualBox VM 단건 health. body['vm_id'] in (ls-db, ls-token, ls-api)
            result = _api_get(f'/internal/health/vm/{body["vm_id"]}')
        elif action == 'mysql_health':
            # P4 r41 — local MySQL health (8 tables alive 여부)
            result = _api_get('/internal/health/mysql')
        elif action == 'tokenization_health':
            # P4 r42 — Tokenization Service (FastAPI /health on port 8000)
            result = _api_get('/internal/health/tokenization')

        else:
            return _resp(400, {'error': f'지원하지 않는 action: {action}'})

        return _resp(200, result)

    except urllib.error.HTTPError as e:
        code = e.code
        try:
            detail = json.loads(e.read())
        except Exception:
            detail = {'error': str(e)}
        return _resp(code if code in (400, 401, 404) else 502, detail)
    except Exception as e:
        return _resp(502, {'error': f'온프레미스 연결 실패: {str(e)}'})
