"""
analytics_aggregator — 일배치 집계 Lambda

EventBridge cron (03:00 KST) 또는 수동 invoke 로 실행.
[1] Aurora customer_recommend_history → customer_recommend_daily (어제 1일치 upsert)  — P3 r10
[2] Aurora + 온프레 인구통계 JOIN → DDB analytics_segment_daily (오늘자 세그먼트별 CTR/CVR)  — P3 r12
[3] 온프레 인구통계 분포 → DDB analytics_demographic_daily (오늘자 차원별 비율)  — P3 r13

환경변수:
  AWS_REGION                              (lambda runtime 자동 주입)
  AURORA_SECRET_ID        — Secrets Manager id (예: lifesync/aurora)
  AURORA_DB_NAME          — 기본 lifesync360
  DDB_SEGMENT_TABLE       — 기본 analytics_segment_daily
  DDB_DEMOGRAPHIC_TABLE   — 기본 analytics_demographic_daily
  ONPREM_QUERY_LAMBDA     — onprem_customer_query lambda 함수명 (선택)
"""
import json
import os
from datetime import datetime, timedelta, timezone

import boto3
import pymysql

REGION                = os.environ.get('AWS_REGION', 'ap-northeast-2')
AURORA_SECRET_ID      = os.environ.get('AURORA_SECRET_ID', 'lifesync/aurora')
AURORA_DB_NAME        = os.environ.get('AURORA_DB_NAME', 'lifesync360')
DDB_SEGMENT_TABLE     = os.environ.get('DDB_SEGMENT_TABLE', 'analytics_segment_daily')
DDB_DEMOGRAPHIC_TABLE = os.environ.get('DDB_DEMOGRAPHIC_TABLE', 'analytics_demographic_daily')
ONPREM_QUERY_LAMBDA   = os.environ.get('ONPREM_QUERY_LAMBDA', '')

KST = timezone(timedelta(hours=9))

_sm        = boto3.client('secretsmanager', region_name=REGION)
_ddb       = boto3.resource('dynamodb',     region_name=REGION)
_lambda    = boto3.client('lambda',         region_name=REGION)


def _aurora_conn():
    secret = json.loads(_sm.get_secret_value(SecretId=AURORA_SECRET_ID)['SecretString'])
    return pymysql.connect(
        host       = secret['host'],
        user       = secret['user'],
        password   = secret['password'],
        port       = int(secret.get('port', 3306)),
        database   = AURORA_DB_NAME,
        cursorclass= pymysql.cursors.DictCursor,
        autocommit = True,
        connect_timeout = 10,
    )


def _kst_today():
    return datetime.now(KST).date()


# ───────────────────────────────────────────────────────────────
# [1] customer_recommend_daily — 어제 1일치 upsert
# ───────────────────────────────────────────────────────────────
def aggregate_recommend_daily(conn):
    yesterday = _kst_today() - timedelta(days=1)
    sql = """
        INSERT INTO customer_recommend_daily (date, recommended, clicked, purchased, ctr, cvr)
        SELECT DATE(recommended_at)       AS date,
               COUNT(*)                   AS recommended,
               SUM(clicked_flag='Y')      AS clicked,
               SUM(purchased_flag='Y')    AS purchased,
               ROUND(SUM(clicked_flag='Y')   / NULLIF(COUNT(*),0)        * 100, 1) AS ctr,
               ROUND(SUM(purchased_flag='Y') / NULLIF(SUM(clicked_flag='Y'),0) * 100, 1) AS cvr
        FROM customer_recommend_history
        WHERE recommended_at >= %s
          AND recommended_at <  %s
        GROUP BY DATE(recommended_at)
        ON DUPLICATE KEY UPDATE
          recommended = VALUES(recommended),
          clicked     = VALUES(clicked),
          purchased   = VALUES(purchased),
          ctr         = VALUES(ctr),
          cvr         = VALUES(cvr)
    """
    with conn.cursor() as cur:
        affected = cur.execute(sql, (yesterday, yesterday + timedelta(days=1)))
    return {'date': str(yesterday), 'affected': affected}


# ───────────────────────────────────────────────────────────────
# [2] analytics_segment_daily — 인구통계 차원 × CTR/CVR
# ───────────────────────────────────────────────────────────────
def aggregate_segment_performance(conn):
    """
    customer_recommend_history (Aurora) + customer_360_profile (온프레)
    → 인구통계 차원별 CTR/CVR. 온프레 fetch 실패 시 빈 결과 (skip).
    """
    profile_map = _fetch_onprem_profile_map()
    if not profile_map:
        return {'rows': 0, 'reason': 'onprem profile unavailable'}

    snapshot = str(_kst_today())
    # 어제 1일치 history만 대상 (적재량 제한)
    yesterday = _kst_today() - timedelta(days=1)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT global_id, "
            "       COUNT(*)                AS recommended, "
            "       SUM(clicked_flag='Y')   AS clicked, "
            "       SUM(purchased_flag='Y') AS purchased "
            "FROM customer_recommend_history "
            "WHERE recommended_at >= %s AND recommended_at < %s "
            "GROUP BY global_id",
            (yesterday, yesterday + timedelta(days=1)),
        )
        rows = cur.fetchall()

    # 차원별 합산 — {dim_key: {recommended, clicked, purchased}}
    agg = {}
    for r in rows:
        prof = profile_map.get(r['global_id'])
        if not prof:
            continue
        for dim, value in (
            ('gender',   prof.get('gender')),
            ('age_band', prof.get('age_band')),
            ('region',   prof.get('region')),
            ('income',   prof.get('income_grade')),
            ('asset',    prof.get('asset_grade')),
        ):
            if not value:
                continue
            key = f'{dim}#{value}'
            slot = agg.setdefault(key, {'recommended': 0, 'clicked': 0, 'purchased': 0})
            slot['recommended'] += int(r['recommended'] or 0)
            slot['clicked']     += int(r['clicked']     or 0)
            slot['purchased']   += int(r['purchased']   or 0)

    table = _ddb.Table(DDB_SEGMENT_TABLE)
    n = 0
    with table.batch_writer() as bw:
        for sk, v in agg.items():
            ctr = round(v['clicked']   / v['recommended'] * 100, 1) if v['recommended'] else 0
            cvr = round(v['purchased'] / v['clicked']     * 100, 1) if v['clicked']     else 0
            bw.put_item(Item={
                'snapshot_date': snapshot,
                'segment_key'  : sk,
                'recommended'  : v['recommended'],
                'clicked'      : v['clicked'],
                'purchased'    : v['purchased'],
                'ctr'          : str(ctr),
                'cvr'          : str(cvr),
            })
            n += 1
    return {'rows': n, 'snapshot_date': snapshot}


# ───────────────────────────────────────────────────────────────
# [3] analytics_demographic_daily — 차원별 인구 분포 비율
# ───────────────────────────────────────────────────────────────
def aggregate_demographic_summary():
    """
    온프레 customer_360_profile 전체 1M 인구통계 분포 (성별/연령대/지역/소득/자산)
    → DDB (PK=snapshot_date, SK='dim#value', attr=count, pct)
    """
    profile_map = _fetch_onprem_profile_map()
    if not profile_map:
        return {'rows': 0, 'reason': 'onprem profile unavailable'}

    snapshot = str(_kst_today())
    total = len(profile_map)

    dim_counts = {}
    for prof in profile_map.values():
        for dim, value in (
            ('gender',   prof.get('gender')),
            ('age_band', prof.get('age_band')),
            ('region',   prof.get('region')),
            ('income',   prof.get('income_grade')),
            ('asset',    prof.get('asset_grade')),
        ):
            if not value:
                continue
            key = f'{dim}#{value}'
            dim_counts[key] = dim_counts.get(key, 0) + 1

    table = _ddb.Table(DDB_DEMOGRAPHIC_TABLE)
    n = 0
    with table.batch_writer() as bw:
        for sk, cnt in dim_counts.items():
            bw.put_item(Item={
                'snapshot_date': snapshot,
                'segment_key'  : sk,
                'count'        : cnt,
                'pct'          : str(round(cnt / total * 100, 2)),
                'total'        : total,
            })
            n += 1
    return {'rows': n, 'snapshot_date': snapshot, 'total': total}


# ───────────────────────────────────────────────────────────────
# 온프레 customer_360_profile fetch (PrivateAPI via onprem_customer_query lambda)
# 1M 행을 sync invoke 6MB 제한에 맞추기 위해 페이지 루프 (size=10000, ~100 pages).
# segment_performance / demographic_summary 두 곳에서 호출되므로 단순 메모이즈.
# 실패 시 빈 dict — caller 가 skip 판단.
# ───────────────────────────────────────────────────────────────
PROFILE_PAGE_SIZE = int(os.environ.get('PROFILE_PAGE_SIZE', '10000'))
PROFILE_MAX_PAGES = int(os.environ.get('PROFILE_MAX_PAGES', '200'))   # 안전 상한 (≥ 2M 행)

_profile_cache = None

def _fetch_onprem_profile_map():
    global _profile_cache
    if _profile_cache is not None:
        return _profile_cache
    if not ONPREM_QUERY_LAMBDA:
        _profile_cache = {}
        return _profile_cache

    profile_map = {}
    try:
        after = ''
        for _ in range(PROFILE_MAX_PAGES):
            resp = _lambda.invoke(
                FunctionName  = ONPREM_QUERY_LAMBDA,
                InvocationType= 'RequestResponse',
                Payload       = json.dumps({
                    'action': 'list_profile_page',
                    'after' : after,
                    'size'  : PROFILE_PAGE_SIZE,
                }).encode(),
            )
            envelope = json.loads(resp['Payload'].read())
            if envelope.get('statusCode') != 200:
                break
            body  = json.loads(envelope['body']) if isinstance(envelope.get('body'), str) else envelope.get('body', {})
            items = body.get('items') or []
            for it in items:
                gid = it.get('global_id')
                if gid:
                    profile_map[gid] = it
            if len(items) < PROFILE_PAGE_SIZE:
                break    # 마지막 페이지
            after = items[-1]['global_id']
    except Exception:
        pass

    _profile_cache = profile_map
    return _profile_cache


# ───────────────────────────────────────────────────────────────
# Lambda entrypoint
# ───────────────────────────────────────────────────────────────
def handler(event, context):
    result = {'date_kst': str(_kst_today())}
    conn = _aurora_conn()
    try:
        result['recommend_daily']      = aggregate_recommend_daily(conn)
        result['segment_performance']  = aggregate_segment_performance(conn)
        result['demographic_summary']  = aggregate_demographic_summary()
    finally:
        try: conn.close()
        except Exception: pass

    return {
        'statusCode': 200,
        'headers'   : {'Content-Type': 'application/json'},
        'body'      : json.dumps(result, ensure_ascii=False),
    }
