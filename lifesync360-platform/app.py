import os
import datetime
import hashlib
import uuid
import json as _json
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from functools import wraps
import jwt
import redis
import boto3
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)
JWT_SECRET          = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    raise RuntimeError('JWT_SECRET 환경변수 누락 — IaC env 주입 확인 필요')
USE_MOCK            = os.environ.get('USE_MOCK', 'true').lower() != 'false'
PROFILE_SYNC_LAMBDA  = os.environ.get('PROFILE_SYNC_LAMBDA', '')
ONPREM_QUERY_LAMBDA  = os.environ.get('ONPREM_QUERY_LAMBDA', 'lifesync-onprem-customer-query')
AWS_REGION           = os.environ.get('AWS_REGION', 'ap-northeast-2')

# mock_data는 항상 import (인증 + USE_MOCK 분기 둘 다에서 사용)
from mock_data import (
    MOCK_USERS, MOCK_RECOMMENDATIONS, PRODUCTS_MAP, get_mock_health,
    get_mock_campaigns,
)

COMPANIES = [
    {'key': 'BANK',       'name': 'LS 은행'},
    {'key': 'CARD',       'name': 'LS 카드'},
    {'key': 'INSURANCE',  'name': 'LS 보험'},
    {'key': 'SECURITIES', 'name': 'LS 증권'},
    {'key': 'HEALTHCARE', 'name': 'LS 헬스케어'},
    {'key': 'HOSPITAL',   'name': 'LS 병원'},
]

CONSENTS = [
    {
        'key':   'BANK',
        'label': 'LS 은행 데이터 활용 동의',
        'icon':  '🏦',
        'desc':  '예금·적금·대출·연금 거래 내역을 분석해 자산 흐름에 맞는 금융 상품을 추천드립니다.',
        'scope': '계좌 잔액 · 거래 패턴 · 신용 등급',
    },
    {
        'key':   'CARD',
        'label': 'LS 카드 데이터 활용 동의',
        'icon':  '💳',
        'desc':  '카드 사용 카테고리와 포인트 적립 패턴을 분석해 라이프스타일 맞춤 혜택을 제안드립니다.',
        'scope': '결제 카테고리 · 사용 금액 · 포인트 적립/사용',
    },
    {
        'key':   'INSURANCE',
        'label': 'LS 보험 데이터 활용 동의',
        'icon':  '🛡️',
        'desc':  '보유 보험과 보장 공백을 분석해 필요한 보장을 보완할 보험 상품을 추천드립니다.',
        'scope': '보험 종목 · 보장 한도 · 만기 정보',
    },
    {
        'key':   'SECURITIES',
        'label': 'LS 증권 데이터 활용 동의',
        'icon':  '📈',
        'desc':  '투자 성향과 보유 종목을 기반으로 ETF·펀드·연금 등 투자 상품을 추천드립니다.',
        'scope': '포트폴리오 · 거래 패턴 · 위험 성향',
    },
    {
        'key':   'ONLINE_INS',
        'label': 'LS 다이렉트보험 데이터 활용 동의',
        'icon':  '📱',
        'desc':  '비대면 가입 이력 기반으로 모바일 간편 보험 상품을 우선 추천드립니다.',
        'scope': '온라인 가입 이력 · 견적 조회 · 클릭 패턴',
    },
    {
        'key':   'HEALTHCARE',
        'label': 'LS 헬스케어 데이터 활용 동의',
        'icon':  '💪',
        'desc':  '건강검진 결과와 측정 데이터로 건강 점수 산출 및 맞춤 헬스·웰니스 프로그램을 제공합니다.',
        'scope': '검진 결과 · 건강 지표 · 운동/식단 기록',
    },
    {
        'key':   'HOSPITAL',
        'label': 'LS 협력병원 데이터 활용 동의',
        'icon':  '🏥',
        'desc':  '진료 기록을 기반으로 화상진료·맞춤 보험·건강관리 서비스를 연결해 드립니다.',
        'scope': '진료/처방 이력 · 예약 정보',
    },
    {
        'key':   'WEARABLE',
        'label': '웨어러블 기기 데이터 활용 동의',
        'icon':  '⌚',
        'desc':  '심박수·걸음수·수면 데이터를 실시간 분석해 동적 건강 점수와 알림을 제공합니다.',
        'scope': '심박/혈압/SpO2 · 걸음수 · 수면 패턴',
    },
]

GRADE_SCORE_MAP = {
    'VIP':    90,
    'GOLD':   80,
    'SILVER': 70,
    'BASIC':  60,
    'CARE':    0,
}

# Service-DB 등급 체계: VIP > GOLD > SILVER > BASIC, CARE는 건강 특화
GRADE_BENEFITS = {
    'VIP': {'color': 'vip', 'desc': '최상위 고객 전용 혜택', 'benefits': [
        '보험료 최대 15% 할인', '포인트 3배 적립', 'PB 전담 매니저 배정',
        '공항 라운지 무제한', 'VIP 종합 건강검진 무료',
    ]},
    'GOLD': {'color': 'gold', 'desc': '우수 고객 혜택', 'benefits': [
        '보험료 10% 할인', '포인트 2배 적립', '건강검진 30% 할인',
        '전용 상담 채널 이용', '금융상품 우대금리 0.3%p',
    ]},
    'SILVER': {'color': 'silver', 'desc': '일반 우대 혜택', 'benefits': [
        '보험료 5% 할인', '포인트 1.5배 적립', '건강검진 15% 할인',
        '금융상품 우대금리 0.1%p',
    ]},
    'BASIC': {'color': 'basic', 'desc': '기본 혜택', 'benefits': [
        '포인트 기본 적립', '제휴 서비스 이용',
    ]},
    'CARE': {'color': 'care', 'desc': '건강관리 특화 혜택', 'benefits': [
        'AI 건강 리포트 제공', '운동/식단 코칭', '건강검진 우선 예약',
    ]},
}


# ── DB / 인프라 헬퍼 ──────────────────────────────────
_redis  = None
_dynamo = None

def get_redis():
    global _redis
    if _redis is None:
        host = os.environ.get('REDIS_HOST','lif-re-1sqfju15n8thy')
        if not host:
            raise RuntimeError('REDIS_HOST 환경변수가 설정되지 않았습니다.')
        _redis = redis.Redis(host=host, port=int(os.environ.get('REDIS_PORT', '6379')), decode_responses=True)
    return _redis

def get_dynamo_table():
    global _dynamo
    if _dynamo is None:
        _dynamo = boto3.resource('dynamodb', region_name=AWS_REGION)
    return _dynamo.Table(os.environ.get('DYNAMO_TABLE', 'lifesync_customer_result'))

def get_db():
    """Service-DB (lifesync360) 연결"""
    import pymysql
    return pymysql.connect(
        host=os.environ.get('AURORA_HOST', 'auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com'),
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASS'],
        database=os.environ.get('DB_NAME', 'lifesync360'),
        cursorclass=pymysql.cursors.DictCursor,
    )

def _call_onprem(action, **kwargs):
    """온프레미스 조회 Lambda 호출 — Control Node 경유"""
    if not ONPREM_QUERY_LAMBDA:
        raise RuntimeError('ONPREM_QUERY_LAMBDA 환경변수 미설정')
    resp   = _get_lambda().invoke(
        FunctionName=ONPREM_QUERY_LAMBDA,
        InvocationType='RequestResponse',
        Payload=_json.dumps({'action': action, **kwargs}),
    )
    result = _json.loads(resp['Payload'].read())
    status = result.get('statusCode', 200)
    body   = _json.loads(result['body']) if isinstance(result.get('body'), str) else result
    if status not in (200,):
        raise ValueError(body.get('error') or body.get('detail') or '온프레미스 오류')
    return body


# ── Lambda 호출 ───────────────────────────────────────
_lambda_client = None

def _get_lambda():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client('lambda', region_name=AWS_REGION)
    return _lambda_client

def _resolve_global_id(ls_user_id, email):
    if not PROFILE_SYNC_LAMBDA:
        return None
    try:
        resp = _get_lambda().invoke(
            FunctionName=PROFILE_SYNC_LAMBDA,
            InvocationType='RequestResponse',
            Payload=_json.dumps({'ls_user_id': ls_user_id, 'email': email}),
        )
        result = _json.loads(resp['Payload'].read())
        if result.get('statusCode') == 200:
            return _json.loads(result['body'])['global_id']
    except Exception:
        pass
    return None


# ── JWT ───────────────────────────────────────────────
def make_jwt(ls_user_id, global_id):
    payload = {
        'sub': ls_user_id,
        'gid': global_id,
        'exp': datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=24),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def decode_jwt(token):
    return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])


def require_jwt(f):
    """Authorization Bearer 검증 + payload 를 함수 kwarg 'payload' 로 주입."""
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


# ── API ──────────────────────────────────────────────
@app.route('/api/register', methods=['POST'])
def api_register():
    # 임시: Lambda 미배포 검증용 — 인증만 Mock 강제
    user = list(MOCK_USERS.values())[0]
    token = make_jwt(user['ls_user_id'], user['global_id'])
    return jsonify({'token': token, 'ls_user_id': user['ls_user_id']})


@app.route('/api/login', methods=['POST'])
def api_login():
    # 임시: Lambda 미배포 검증용 — 인증만 Mock 강제
    data     = request.get_json() or {}
    email    = data.get('email', '')
    password = data.get('password', '')

    user = MOCK_USERS.get(email)
    if not user or hashlib.sha256(password.encode('utf-8')).hexdigest() != user['password_hash']:
        return jsonify({'error': '이메일 또는 비밀번호가 올바르지 않습니다.'}), 401
    token = make_jwt(user['ls_user_id'], user['global_id'])
    return jsonify({'token': token, 'ls_user_id': user['ls_user_id']})


@app.route('/api/me')
@require_jwt
def api_me(payload):
    if USE_MOCK:
        user = next((u for u in MOCK_USERS.values() if u['ls_user_id'] == payload['sub']), None)
        if not user:
            return jsonify({'error': 'user not found'}), 404
        return jsonify({
            'ls_user_id': payload['sub'],
            'global_id':  payload['gid'],
            'name':       user['name'],
            'grade':      user['grade'],
            'email':      user['email'],
            # 인구통계 (customer_360_profile)
            'gender':        user.get('gender'),
            'age_band':      user.get('age_band'),
            'region':        user.get('region'),
            'income_grade':  user.get('income_grade'),
            'asset_grade':   user.get('asset_grade'),
            'wearable_flag': user.get('wearable_flag'),
            # 마스터 (master_customer)
            'customer_status':  user.get('customer_status'),
            'vip_grade':        user.get('vip_grade'),
            'customer_type':    user.get('customer_type'),
            'first_created_dt': user.get('first_created_dt'),
            'last_login_dt':    user.get('last_login_dt'),
        })

    # Mock 유저 fallback 준비 (Lambda 미배포 검증용)
    _mock_user = next((u for u in MOCK_USERS.values() if u['ls_user_id'] == payload['sub']), None)

    global_id = payload['gid']

    with ThreadPoolExecutor(max_workers=4) as pool:
        fut_user = pool.submit(_call_onprem, 'get_user', ls_user_id=payload['sub'])
        fut_all  = pool.submit(_call_onprem, 'get_all',  global_id=global_id)
        fut_pii  = pool.submit(_call_onprem, 'get_pii',  global_id=global_id)
        fut_ddb  = pool.submit(_ddb_get_latest, global_id)

        login_email = None
        try:
            user = fut_user.result()
            login_email = user.get('login_email')
            global_id   = user.get('global_id', global_id)
        except Exception:
            if _mock_user:
                login_email = _mock_user.get('email')

        grade = None
        try:
            grade = fut_ddb.result().get('dynamic_grade')
        except Exception:
            pass

        onprem = None
        try:
            onprem = fut_all.result()
        except Exception:
            pass

        name = None
        try:
            name = fut_pii.result().get('name')
        except Exception:
            if _mock_user:
                name = _mock_user.get('name')

    consents = onprem.get('consents', []) if onprem else []
    profile  = ((onprem or {}).get('customer') or {}).get('profile') or {}

    return jsonify({
        'ls_user_id': payload['sub'],
        'global_id':  global_id,
        'name':       name,
        'grade':      grade,
        'email':      login_email,
        'consents':   consents,
        'profile':    profile,
    })



@app.route('/api/consent', methods=['POST'])
@require_jwt
def api_consent(payload):
    if USE_MOCK:
        return jsonify({'status': 'ok'})

    consents = request.get_json().get('consents', [])
    try:
        _call_onprem('save_consent', global_id=payload['gid'], consents=consents)
    except ValueError as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'status': 'ok'})


@app.route('/api/event', methods=['POST'])
@require_jwt
def api_event(payload):
    """
    클라이언트 이벤트 적재:
      ① customer_dashboard_log INSERT (모든 event_type) — page_type/banner_click/product_click 분기
      ② customer_recommend_history UPDATE (recommendation_click → clicked_flag,
                                            apply_submitted/purchased → purchased_flag)

    event_type 매핑:
      recommendation_click → MAIN  + product_click='Y' + history.clicked_flag='Y'
      product_view         → DETAIL + product_click='Y'
      apply_view           → DETAIL
      apply_started        → DETAIL + product_click='Y'
      apply_submitted      → DETAIL + product_click='Y' + history.purchased_flag='Y'
      purchased            → (legacy) history.purchased_flag='Y'
      banner_click         → MAIN  + banner_click='Y'
      tab_click            → MAIN
    """
    if USE_MOCK:
        return jsonify({'status': 'ok'})

    data        = request.get_json() or {}
    event_type  = data.get('event_type', '')
    product_id  = data.get('product_id')
    session_id  = (data.get('session_id') or '')[:100]
    global_id   = payload['gid']

    # 분기 매핑
    detail_events = {'product_view', 'apply_view', 'apply_started', 'apply_submitted'}
    page_type     = 'DETAIL' if event_type in detail_events else 'MAIN'
    banner_click  = 'Y' if event_type == 'banner_click' else 'N'
    product_click = 'Y' if event_type in ('recommendation_click', 'product_view',
                                          'apply_started', 'apply_submitted') else 'N'

    try:
        db = get_db()
        try:
            with db.cursor() as cur:
                # ① customer_dashboard_log INSERT
                cur.execute(
                    "INSERT INTO customer_dashboard_log "
                    "(global_id, page_type, banner_click, product_click, click_product_id, session_id, view_time) "
                    "VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                    (global_id, page_type, banner_click, product_click, product_id, session_id)
                )
                # ② customer_recommend_history UPDATE (product_id 있을 때만)
                if product_id:
                    if event_type == 'recommendation_click':
                        cur.execute(
                            "UPDATE customer_recommend_history SET clicked_flag='Y' "
                            "WHERE global_id=%s AND product_id=%s AND clicked_flag='N' LIMIT 1",
                            (global_id, product_id)
                        )
                    elif event_type in ('apply_submitted', 'purchased'):
                        cur.execute(
                            "UPDATE customer_recommend_history SET purchased_flag='Y' "
                            "WHERE global_id=%s AND product_id=%s AND purchased_flag='N' LIMIT 1",
                            (global_id, product_id)
                        )
            db.commit()
        finally:
            db.close()
    except Exception:
        app.logger.exception('event insert failed (event_type=%s, gid=%s)', event_type, global_id)
    return jsonify({'status': 'ok'})


# NBA → recommend_rule.action_code 매핑 (results.csv 의 next_best_action 컬럼 기준)
_NBA_TO_ACTION = {
    'RETENTION':         'RECOMMEND_HEALTH',
    'INSURANCE_UPSELL':  'RECOMMEND_INSURANCE',
    'HEALTH_SERVICE':    'RECOMMEND_HEALTH_INS',
    'HEALTH_INS':        'RECOMMEND_HEALTH_INS',
    'PB':                'RECOMMEND_PB',
    'WM':                'RECOMMEND_WM',
    'INVEST':            'RECOMMEND_INVEST',
    'SAVING':            'RECOMMEND_SAVING',
    'CARD':              'RECOMMEND_CARD',
    'LOAN':              'RECOMMEND_LOAN',
    'PENSION':           'RECOMMEND_PENSION',
    'WELLNESS':          'RECOMMEND_WELLNESS',
    'TELEMED':           'RECOMMEND_TELEMED',
}


def _recommendations_mock():
    flat = []
    for rec in MOCK_RECOMMENDATIONS:
        for p in rec.get('products', []):
            flat.append({
                'product_id'   : p.get('id'),
                'product_code' : p.get('id'),
                'product_name' : p.get('name'),
                'description'  : p.get('desc', ''),
                'category_code': (rec.get('key') or '').upper(),
                'category_name': rec.get('name', ''),
                'company_code' : (rec.get('key') or '').upper(),
                'company_name' : rec.get('name', ''),
                'risk_level'   : p.get('tag', ''),
                'target_grade' : p.get('type', ''),
                'priority_rank': 0,
            })
    flat = flat[:20]
    for i, p in enumerate(flat):
        p['reason']               = f'VIP 등급 + {p.get("category_name","")} 카테고리 매칭'
        p['rec_rank']             = i + 1
        p['recommendation_score'] = max(60, 95 - i * 4)
    return {
        'meta'    : {'grade': 'VIP', 'score': 90.0, 'health': 88.0,
                     'vip_prob': 0.85, 'next_best_action': 'PB'},
        'products': flat,
    }


def _ddb_get_latest(global_id):
    """DDB lifesync_customer_result HASH(global_id)+RANGE(update_time) 에서 최신 1건.
    GetItem 은 schema 상 두 key 다 필요 — Query + ScanIndexForward=False + Limit 1 로 최신만."""
    try:
        r = get_dynamo_table().query(
            KeyConditionExpression='global_id = :g',
            ExpressionAttributeValues={':g': global_id},
            ScanIndexForward=False,
            Limit=1,
        )
        items = r.get('Items') or []
        return items[0] if items else {}
    except Exception:
        return {}

def _fetch_ddb_meta(global_id):
    """DDB lifesync_customer_result → (grade, dynamic_score, health_score, vip_prob, nba)"""
    item = _ddb_get_latest(global_id)
    return (
        item.get('dynamic_grade', 'BASIC'),
        float(item.get('dynamic_score') or 0),
        float(item.get('health_score')  or 0),
        float(item.get('vip_prob')      or 0),
        item.get('next_best_action'),
    )


def _fetch_redis_cached_ids(global_id):
    try:
        c = get_redis().get(f'rec:{global_id}')
        if c:
            return _json.loads(c)
    except Exception:
        pass
    return None


def _match_rules(cur, grade, dynamic_score, health_score, vip_required_flag, target_action):
    """recommend_rule + cross_sell_rule → (cat_list, rule_action_by_cat)"""
    cur.execute("""
        SELECT category_code, action_code, priority_rank
        FROM recommend_rule
        WHERE active_flag = 'Y'
          AND target_grade = %s
          AND %s BETWEEN min_score AND max_score
          AND (vip_required = 'N' OR vip_required = %s)
          AND (health_min_score IS NULL OR %s >= health_min_score)
        ORDER BY
          CASE WHEN action_code = %s THEN 0 ELSE 1 END,
          priority_rank
    """, (grade, dynamic_score, vip_required_flag, health_score, target_action or ''))
    rule_rows = cur.fetchall()
    rule_action_by_cat = {r['category_code']: r['action_code'] for r in rule_rows}

    cross_cats = []
    if rule_rows:
        cur.execute("""
            SELECT target_category FROM cross_sell_rule
            WHERE base_category = %s AND active_flag = 'Y'
            ORDER BY priority_rank LIMIT 3
        """, (rule_rows[0]['category_code'],))
        cross_cats = [r['target_category'] for r in cur.fetchall()]

    seen = set()
    cat_list = []
    for c in [r['category_code'] for r in rule_rows] + cross_cats:
        if c not in seen:
            seen.add(c); cat_list.append(c)
    for c in cross_cats:
        rule_action_by_cat.setdefault(c, 'RECOMMEND_CROSS_SELL')

    return cat_list, rule_action_by_cat


def _fetch_products(cur, cached_ids, cat_list, dynamic_score, grade):
    """3 모드: cache hit → id 조회 / category 매칭 → top2*N / fallback → score 기반 LIMIT 20."""
    if cached_ids:
        placeholders = ', '.join(['%s'] * len(cached_ids))
        cur.execute(f"""
            SELECT p.product_id, p.product_code, p.product_name, p.description,
                   p.target_grade, p.risk_level, p.priority_rank,
                   c.company_code, c.company_name, cat.category_code, cat.category_name
            FROM product_master p
            JOIN company_master   c   ON p.company_id  = c.company_id
            JOIN category_master  cat ON p.category_id = cat.category_id
            WHERE p.product_id IN ({placeholders}) AND p.active_flag = 'Y'
            ORDER BY p.priority_rank
        """, cached_ids)
        return cur.fetchall()

    products = []
    if cat_list:
        cat_placeholders = ', '.join(['%s'] * len(cat_list))
        cur.execute(f"""
            SELECT p.product_id, p.product_code, p.product_name, p.description,
                   p.target_grade, p.risk_level, p.priority_rank,
                   c.company_code, c.company_name, cat.category_code, cat.category_name,
                   ROW_NUMBER() OVER (PARTITION BY cat.category_code ORDER BY p.priority_rank) AS rn
            FROM product_master p
            JOIN company_master   c   ON p.company_id  = c.company_id
            JOIN category_master  cat ON p.category_id = cat.category_id
            WHERE p.active_flag = 'Y'
              AND cat.category_code IN ({cat_placeholders})
              AND p.min_score <= %s
            ORDER BY FIELD(cat.category_code, {cat_placeholders}), p.priority_rank
        """, cat_list + [dynamic_score] + cat_list)
        for r in cur.fetchall():
            if r['rn'] <= 2:
                r.pop('rn', None)
                products.append(r)
            if len(products) >= 20:
                break

    if not products:
        min_score = GRADE_SCORE_MAP.get(grade, 60)
        cur.execute("""
            SELECT p.product_id, p.product_code, p.product_name, p.description,
                   p.target_grade, p.risk_level, p.priority_rank,
                   c.company_code, c.company_name, cat.category_code, cat.category_name
            FROM product_master p
            JOIN company_master   c   ON p.company_id  = c.company_id
            JOIN category_master  cat ON p.category_id = cat.category_id
            WHERE p.active_flag = 'Y' AND p.min_score <= %s
            ORDER BY p.priority_rank LIMIT 20
        """, (min_score,))
        products = cur.fetchall()

    return products


def _enrich_and_record(cur, products, global_id, grade, dynamic_score, health_score,
                       vip_required_flag, target_action, nba, rule_action_by_cat):
    """reason/rec_rank/score 부여 + customer_recommend_history INSERT + 점수 내림차순 재정렬."""
    now = datetime.datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    for i, p in enumerate(products):
        action = rule_action_by_cat.get(p.get('category_code'), 'RECOMMEND_DASHBOARD')
        reason_parts = []
        if target_action and action == target_action:
            reason_parts.append(f'NBA "{nba}" 매칭')
        reason_parts.append(f'{grade} 등급')
        if action == 'RECOMMEND_CROSS_SELL':
            reason_parts.append('cross_sell 보강')
        if vip_required_flag == 'Y':
            reason_parts.append('VIP 후보')
        if health_score and any(kw in (action or '') for kw in ('HEALTH','WELLNESS','TELEMED')):
            reason_parts.append(f'건강점수 {int(health_score)}점')
        p['reason']   = ' · '.join(reason_parts) if reason_parts else f'{p.get("category_name","")} 카테고리 매칭'
        p['rec_rank'] = i + 1
        base        = max(0, 30 - p.get('priority_rank', 10))
        grade_bonus = {'VIP':25,'GOLD':20,'SILVER':15,'BASIC':10,'CARE':10}.get(grade, 10)
        nba_bonus   = 20 if (target_action and action == target_action) else 0
        cross_bonus = -5 if action == 'RECOMMEND_CROSS_SELL' else 0
        p['recommendation_score'] = base + grade_bonus + nba_bonus + cross_bonus
        cur.execute(
            '''INSERT INTO customer_recommend_history
               (global_id, product_id, dynamic_score, dynamic_grade, action_code, recommended_at)
               VALUES (%s, %s, %s, %s, %s, %s)''',
            (global_id, p['product_id'], dynamic_score, grade, action, now)
        )
    products.sort(key=lambda x: -x.get('recommendation_score', 0))
    for i, p in enumerate(products):
        p['rec_rank'] = i + 1


@app.route('/api/recommendations')
@require_jwt
def api_recommendations(payload):
    """
    추천 흐름 (Service-DB recommend_rule + cross_sell_rule + results.csv NBA):
      ① DDB lifesync_customer_result → dynamic_grade / score / health / vip_prob / NBA
      ② Redis 캐시 hit → 즉시 반환 (TTL 6h, miss/fail 시 Aurora fallback)
      ③ recommend_rule 매칭 (target_grade + score 범위 + vip_required + health_min_score)
         + NBA(next_best_action) 매칭된 action_code 우선 정렬
      ④ cross_sell_rule 보강 (첫 base_category → target_category 3개 추가)
      ⑤ category별 product_master 매칭 (각 카테고리당 top 2, 합쳐서 LIMIT 20)
      ⑥ customer_recommend_history INSERT + Redis 캐시 갱신
    """
    if USE_MOCK:
        return jsonify(_recommendations_mock())

    global_id = payload['gid']
    grade, dynamic_score, health_score, vip_prob, nba = _fetch_ddb_meta(global_id)
    cached_ids = _fetch_redis_cached_ids(global_id)

    target_action     = _NBA_TO_ACTION.get(str(nba or '').upper())
    # vip_required 임계 — 운영 데이터 분포에 따라 환경변수로 조정 (results.csv 보면 0.5~0.58 분기)
    _vip_th           = float(os.environ.get('VIP_PROB_THRESHOLD', '0.5'))
    vip_required_flag = 'Y' if vip_prob >= _vip_th else 'N'

    db = get_db()
    try:
        with db.cursor() as cur:
            if cached_ids:
                cat_list, rule_action_by_cat = [], {}
            else:
                cat_list, rule_action_by_cat = _match_rules(
                    cur, grade, dynamic_score, health_score, vip_required_flag, target_action,
                )
            products = _fetch_products(cur, cached_ids, cat_list, dynamic_score, grade)
            _enrich_and_record(
                cur, products, global_id, grade, dynamic_score, health_score,
                vip_required_flag, target_action, nba, rule_action_by_cat,
            )
        db.commit()
    finally:
        db.close()

    products = products[:10]

    if not cached_ids and products:
        try:
            get_redis().setex(
                f'rec:{global_id}', 21600,
                _json.dumps([p['product_id'] for p in products]),
            )
        except Exception:
            pass

    return jsonify({
        'meta'    : {'grade': grade, 'score': dynamic_score, 'health': health_score,
                     'vip_prob': vip_prob, 'next_best_action': nba},
        'products': products,
    })


@app.route('/api/my-applications')
@require_jwt
def api_my_applications(payload):
    """
    내 신청 내역 — customer_product_application + product/company JOIN.
    status (RECEIVED/IN_REVIEW/APPROVED/REJECTED/CANCELED) + 상품 정보.
    """
    if USE_MOCK:
        # 시연용 mock — 최근 신청 3건 가정
        return jsonify([
            {'application_id':'APP-20260517100000-AABBCC','product_code':'HLT-HEALTHCARE-00012-03',
             'product_name':'VIP 종합 건강검진','company_name':'LS 헬스케어','category_name':'헬스케어',
             'status':'IN_REVIEW','created_at':'2026-05-17 10:00:00'},
            {'application_id':'APP-20260515143020-AABBCC','product_code':'INS-INSURANCE-00045-02',
             'product_name':'프리미엄 실손 보험','company_name':'LS 보험','category_name':'보험',
             'status':'APPROVED','created_at':'2026-05-15 14:30:20'},
            {'application_id':'APP-20260510091505-AABBCC','product_code':'BANK-DEPOSIT-00001-01',
             'product_name':'PB 우대 정기예금 12개월','company_name':'LS 은행','category_name':'예금',
             'status':'RECEIVED','created_at':'2026-05-10 09:15:05'},
        ])

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT a.application_id, p.product_code, p.product_name, "
                "       c.company_name, cat.category_name, a.status, "
                "       NULL AS created_at "
                "FROM customer_product_application a "
                "LEFT JOIN product_master  p   ON a.product_id  = p.product_id "
                "LEFT JOIN company_master  c   ON p.company_id  = c.company_id "
                "LEFT JOIN category_master cat ON p.category_id = cat.category_id "
                "WHERE a.global_id = %s "
                "ORDER BY a.application_id DESC LIMIT 50",
                (payload['gid'],),
            )
            rows = []
            for r in cur.fetchall():
                rows.append({**r, 'created_at': str(r['created_at']) if r.get('created_at') else None})
        return jsonify(rows)
    except Exception:
        app.logger.exception('my-applications query failed (gid=%s)', payload['gid'])
        return jsonify([])
    finally:
        db.close()


@app.route('/api/campaigns')
@require_jwt
def api_campaigns(payload):
    """등급별 활성 캠페인 배너"""
    grade = 'BASIC'
    if USE_MOCK:
        user = next((u for u in MOCK_USERS.values() if u['ls_user_id'] == payload['sub']), None)
        if user:
            grade = user.get('grade', 'BASIC')
        return jsonify(get_mock_campaigns(grade))

    try:
        item  = _ddb_get_latest(payload['gid'])
        grade = item.get('dynamic_grade', 'BASIC')
    except Exception:
        pass

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("""
                SELECT campaign_name, banner_title, banner_desc, start_date, end_date
                FROM campaign_master
                WHERE target_grade = %s AND active_flag = 'Y'
                  AND end_date >= CURDATE()
                ORDER BY start_date DESC
                LIMIT 5
            """, (grade,))
            rows = cur.fetchall()
    except Exception:
        app.logger.exception('campaigns query failed (grade=%s)', grade)
        rows = []
    finally:
        db.close()
    return jsonify([
        {'icon': '🎯', 'title': r['campaign_name'], 'desc': r['banner_desc'],
         'period': f"{r['start_date']} ~ {r['end_date']}", 'cta': '자세히 보기'}
        for r in rows
    ])


@app.route('/health')
def health():
    return {
        'status': 'ok',
        'jwt_from_env': bool(os.environ.get('JWT_SECRET')),
        'jwt_len':      len(JWT_SECRET),
        'use_mock':     USE_MOCK,
        'dynamo_table': os.environ.get('DYNAMO_TABLE', 'NOT_SET'),
    }


@app.route('/api/dashboard')
@require_jwt
def api_dashboard(payload):
    if USE_MOCK:
        h = get_mock_health(payload['sub'])
        return jsonify({**h, 'no_data': False})

    item = _ddb_get_latest(payload['gid'])
    if not item:
        return jsonify({'no_data': True})

    def _f(key):
        v = item.get(key, '')
        return float(v) if v else None

    return jsonify({
        'no_data':          False,
        'dynamic_score':    _f('dynamic_score'),
        'health_score':     _f('health_score'),
        'next_best_action': item.get('next_best_action'),
        'update_time':      item.get('update_time'),
    })


# ── 페이지 ────────────────────────────────────────────
@app.route('/settings')
def settings():
    return render_template('settings.html',
        grade_benefits=GRADE_BENEFITS,
        consents=CONSENTS,
    )


@app.route('/product/<product_code>')
def product(product_code):
    if USE_MOCK:
        item = PRODUCTS_MAP.get(product_code)
        if not item:
            return redirect(url_for('dashboard'))
        return render_template('product.html', item=item)

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("""
                SELECT p.product_id, p.product_code, p.product_name, p.description,
                       p.target_grade, p.risk_level, p.min_score, p.max_score,
                       c.company_code, c.company_name, cat.category_code, cat.category_name
                FROM product_master p
                JOIN company_master   c   ON p.company_id  = c.company_id
                JOIN category_master  cat ON p.category_id = cat.category_id
                WHERE p.product_code = %s AND p.active_flag = 'Y'
            """, (product_code,))
            row = cur.fetchone()
            if not row:
                return redirect(url_for('dashboard'))

            cur.execute(
                'SELECT option_name, option_value FROM product_option WHERE product_id = %s ORDER BY option_id',
                (row['product_id'],)
            )
            options = cur.fetchall()
    finally:
        db.close()

    item = {
        'id':       row['product_code'],
        'name':     row['product_name'],
        'type':     row['target_grade'],
        'desc':     row['description'],
        'tag':      row['risk_level'],
        'detail':   [{'key': o['option_name'], 'value': o['option_value']} for o in options],
        'category': row['company_code'],
    }
    return render_template('product.html', item=item)


@app.route('/product/<product_code>/apply')
def product_apply(product_code):
    """상품 신청 페이지 — product.html '신청하기' 클릭 시 이동."""
    if USE_MOCK:
        m = PRODUCTS_MAP.get(product_code)
        if not m:
            return redirect(url_for('dashboard'))
        item = {'id': product_code, 'name': m['name'], 'desc': m.get('desc', ''),
                'category': m.get('category', ''), 'product_id': None}
        return render_template('apply.html', item=item)

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("""
                SELECT p.product_id, p.product_code, p.product_name, p.description,
                       c.company_code, c.company_name, cat.category_name
                FROM product_master p
                JOIN company_master   c   ON p.company_id  = c.company_id
                JOIN category_master  cat ON p.category_id = cat.category_id
                WHERE p.product_code = %s AND p.active_flag = 'Y'
            """, (product_code,))
            row = cur.fetchone()
    finally:
        db.close()

    if not row:
        return redirect(url_for('dashboard'))
    item = {
        'id'        : row['product_code'],
        'product_id': row['product_id'],
        'name'      : row['product_name'],
        'desc'      : row['description'] or '',
        'category'  : row['category_name'],
    }
    return render_template('apply.html', item=item)


@app.route('/api/product/<product_code>/apply', methods=['POST'])
@require_jwt
def api_product_apply(product_code, payload):
    """상품 신청 처리 — customer_product_application 테이블 INSERT.

    Service-DB v3 기준 9컬럼 슬림 스키마:
      application_id / global_id / ls_user_id / product_id / status / reviewer_id /
      reviewed_at / created_at / updated_at
    INSERT 시점에는 4컬럼 (status default 'RECEIVED', 나머지 자동/NULL).
    컨택 정보(이름/전화/금액/메모/마케팅동의) 는 별도 시스템 책임 — Aurora 미저장.
    """
    if USE_MOCK:
        application_id = f"APP-{datetime.datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{payload['sub'][-6:]}"
        return jsonify({'status': 'ok', 'application_id': application_id})

    db = get_db()
    try:
        with db.cursor() as cur:
            # 온프레미스 users 테이블에서 실제 ls_user_id 조회 (JWT mock 값과 다를 수 있음)
            real_ls_user_id = payload['sub']
            try:
                u = _call_onprem('get_user_by_global', global_id=payload['gid'])
                if u and u.get('ls_user_id'):
                    real_ls_user_id = u['ls_user_id']
            except Exception:
                pass

            application_id = f"APP-{datetime.datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{real_ls_user_id[-6:]}"

            # product_id 조회 (apply.html 이 보내준 product_id 가 null/모를 수도 있어 안전하게 재조회)
            cur.execute(
                "SELECT product_id FROM product_master WHERE product_code = %s AND active_flag = 'Y'",
                (product_code,),
            )
            row = cur.fetchone()
            product_id = row['product_id'] if row else None
            if not product_id:
                return jsonify({'error': '상품을 찾을 수 없습니다.'}), 404

            # 신청 INSERT — Service-DB/9.customer_product_application.sql (v3, 9컬럼) 단일 출처
            cur.execute("""
                INSERT INTO customer_product_application
                  (application_id, global_id, ls_user_id, product_id)
                VALUES (%s, %s, %s, %s)
            """, (application_id, payload['gid'], real_ls_user_id, product_id))
            # 신청 즉시 customer_recommend_history.purchased_flag='Y' UPDATE
            # (apply_submitted event 와 중복되어도 LIMIT 1 + WHERE purchased_flag='N' 조건이라 안전)
            cur.execute(
                "UPDATE customer_recommend_history SET purchased_flag='Y' "
                "WHERE global_id=%s AND product_id=%s AND purchased_flag='N' LIMIT 1",
                (payload['gid'], product_id)
            )
            # 신청 dashboard_log 도 직접 기록 (event 의존 X)
            cur.execute(
                "INSERT INTO customer_dashboard_log "
                "(global_id, page_type, banner_click, product_click, click_product_id, session_id, view_time) "
                "VALUES (%s, 'DETAIL', 'N', 'Y', %s, %s, NOW())",
                (payload['gid'], product_id, application_id)
            )
        db.commit()
    except Exception as e:
        return jsonify({'error': f'신청 처리 실패: {str(e)}'}), 500
    finally:
        db.close()

    return jsonify({'status': 'ok', 'application_id': application_id})


@app.route('/register')
def register():
    return render_template('register.html')


@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/consent')
def consent():
    return render_template('consent.html', consents=CONSENTS)


@app.route('/')
def dashboard():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
