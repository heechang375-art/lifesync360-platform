import os
import functools
import json
import time
from datetime import datetime, timezone, timedelta

import boto3

_KST = timezone(timedelta(hours=9))

def _kst(dt_val):
    """Aurora UTC datetime → KST 문자열 (YYYY-MM-DD HH:MM)"""
    if not dt_val:
        return '-'
    try:
        dt = dt_val if hasattr(dt_val, 'year') else datetime.fromisoformat(str(dt_val))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_KST).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return str(dt_val)[:16]
from flask import Flask, Response, render_template, request, redirect, url_for, session, jsonify, stream_with_context

import wearable_engine


def _bootstrap_dotenv():
    """admin-platform/.env 또는 .env.local 가 있으면 os.environ 에 로드. AWS 호출 전에 실행."""
    here = os.path.dirname(os.path.abspath(__file__))
    for fname in ('.env', '.env.local'):
        path = os.path.join(here, fname)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and not os.environ.get(k):
                        os.environ[k] = v
        except Exception:
            pass


_bootstrap_dotenv()


def _bootstrap_secrets():
    """Secrets Manager /lifesync/dev/db/master + GCP SA key → os.environ (미설정 항목만 주입)"""
    _log = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bootstrap.log')
    try:
        client = boto3.client('secretsmanager', region_name='ap-northeast-2')
        resp = client.get_secret_value(SecretId='/lifesync/dev/db/master')
        d = json.loads(resp['SecretString'])
        _alias = {'host': 'AURORA_HOST', 'username': 'DB_USER', 'password': 'DB_PASS', 'dbname': 'DB_NAME'}
        for src, dst in _alias.items():
            if src in d:
                os.environ[dst] = str(d[src])
        with open(_log, 'a') as f:
            f.write(f'DB OK: AURORA_HOST={os.environ.get("AURORA_HOST")} DB_NAME={os.environ.get("DB_NAME")}\n')
    except Exception as e:
        with open(_log, 'a') as f:
            f.write(f'DB ERROR: {e}\n')
    try:
        client = boto3.client('secretsmanager', region_name='ap-northeast-2')
        resp = client.get_secret_value(SecretId='lifesync/gcp/service-account-key')
        gcp_key = json.loads(resp['SecretString'])
        if not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
            import tempfile
            tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
            json.dump(gcp_key, tmp)
            tmp.close()
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = tmp.name
        if not os.environ.get('GCP_PROJECT_ID'):
            os.environ['GCP_PROJECT_ID'] = gcp_key.get('project_id', '')
    except Exception:
        pass
    try:
        client = boto3.client('secretsmanager', region_name='ap-northeast-2')
        resp = client.get_secret_value(SecretId='lifesync/dev/redis')
        redis_cfg = json.loads(resp['SecretString'])
        if not os.environ.get('REDIS_HOST'):
            os.environ['REDIS_HOST'] = redis_cfg.get('host', '')
        if not os.environ.get('REDIS_PORT'):
            os.environ['REDIS_PORT'] = str(redis_cfg.get('port', '6379'))
    except Exception:
        pass


_bootstrap_secrets()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'admin-dev-secret-32bytes-lifesync!!')  # TODO: 운영 배포 시 env var로 교체

ADMIN_USER           = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASS           = os.environ.get('ADMIN_PASSWORD', 'admin123')
DYNAMO_TABLE         = os.environ.get('DYNAMO_TABLE', 'lifesync_customer_result')
DDB_SEGMENT_TABLE    = os.environ.get('DDB_SEGMENT_TABLE',    'analytics_segment_performance')
DDB_DEMOGRAPHIC_TABLE= os.environ.get('DDB_DEMOGRAPHIC_TABLE','analytics_demographic_information')
AWS_REGION           = os.environ.get('AWS_REGION', 'ap-northeast-2')
ONPREM_QUERY_LAMBDA  = os.environ.get('ONPREM_QUERY_LAMBDA', 'lifesync-onprem-customer-query')
ONPREM_BASE_URL      = os.environ.get('ONPREM_BASE_URL', 'http://172.16.1.73')

GRADES = ['VIP', 'GOLD', 'SILVER', 'BASIC', 'CARE']
CONSENT_LABELS = {
    'BANK':  '은행',
    'CARD':  '카드',
    'INS':   '보험',
    'SEC':   '증권',
    'HLT':   '헬스케어',
    'HOS':   '병원',
    'WBL':   '웨어러블',
    'ONINS': '온라인보험',
}

# ── 카드 구조 정의 (라벨·아이콘·색상만, 값 없음) ────────────────────────────
_DASH_KPI_CARDS = [
    {'label': '통합 고객 수',      'sub': '전체 100% · On-Prem master_customer',     'accent': '#3b82f6', 'is_status': False},
    {'label': '플랫폼 가입자',     'sub': '전체의 30% · On-Prem users',              'accent': '#f59e0b', 'is_status': False},
    {'label': '분석 대상 고객',    'sub': '가입자의 20% · 동의 완료',                'accent': '#14b8a6', 'is_status': False},
    {'label': 'AI 추천 상태',      'sub': 'DynamoDB · 오늘 04:30 갱신',              'accent': '#16a34a', 'is_status': True},
    {'label': '누적 추천 이력',    'sub': 'Aurora customer_recommend_history',       'accent': '#1e293b', 'is_status': False},
    {'label': '누적 활동 로그',    'sub': 'Aurora customer_dashboard_log',           'accent': '#f59e0b', 'is_status': False},
    {'label': '추천 CTR (클릭률)', 'sub': 'SUM(clicked) / COUNT(*) · 전체 누적',     'accent': '#16a34a', 'is_status': False},
    {'label': '구매 전환율 (CVR)', 'sub': 'SUM(purchased) / COUNT(*) · 전체 누적',   'accent': '#3b82f6', 'is_status': False},
    {'label': 'Redis Cache 수',    'sub': 'rec:{global_id} · SCAN · TTL 6h',         'accent': '#dc2626', 'is_status': False},
]
_DASH_CLOUD3_CARDS = [
    {'badge': 'AWS', 'badge_bg': '#fef3c7', 'badge_color': '#d97706', 'title': 'AWS 클라우드'},
    {'badge': 'GCP', 'badge_bg': '#dbeafe', 'badge_color': '#2563eb', 'title': 'GCP 클라우드'},
    {'badge': 'ON',  'badge_bg': '#ccfbf1', 'badge_color': '#0f766e', 'title': '온프레미스'},
]
_DASH_S3_5_CARDS = [
    {'icon': '📁', 'label': 'Raw Bucket 총 파일'},
    {'icon': '📊', 'label': '금일 적재 건수'},
    {'icon': '⚡', 'label': '페이로드 데이터'},
    {'icon': '🔄', 'label': 'Processed 파일 수'},
    {'icon': '✨', 'label': 'Curated 마트 수'},
    {'icon': '💾', 'label': '그룹사 적재량'},
    {'icon': '⏱', 'label': '최근 업로드'},
]
_AI_KPI4_CARDS = [
    {'label': '추천 CTR (클릭률)', 'accent': '#16a34a'},
    {'label': '거래율 CVR (전환)', 'accent': '#3b82f6'},
    {'label': '마지막 배치 갱신',  'accent': '#1e293b'},
    {'label': '분석 대상 고객',    'accent': '#6366f1'},
]
_NET_TOPOLOGY = {
    'aws': [
        {'name': 'Platform VPC', 'bg': '#fef3c7', 'border': '#f59e0b', 'lines': ['Aurora, Redis,', 'DynamoDB, Lambda,', 'API Gateway, ALB']},
        {'name': 'Data VPC',     'bg': '#dbeafe', 'border': '#3b82f6', 'lines': ['Glue, EMR,', 'Kinesis,', 'Stream Lambda']},
        {'name': 'Group VM VPC', 'bg': '#dcfce7', 'border': '#16a34a', 'lines': ['BANK/CARD/SEC/INS/', 'ONINS/HLT/HOS EC2,', 'Wearable EC2']},
    ],
    'gcp':    {'name': 'GCP',                 'bg': '#fce7f3', 'border': '#ec4899', 'lines': ['VPC + PSC Endpoint', 'BigQuery / Vertex AI', 'Cloud Run']},
    'onprem': {'name': 'On-Prem (VirtualBox)', 'bg': '#e0e7ff', 'border': '#6366f1', 'lines': ['Local Lab', 'ls-db (MySQL)', 'ls-tokenz', 'ls-api (PrivateAPI)']},
}
_NET_AWS_PLATFORM     = {'title': 'AWS 플랫폼 VPC',   'badge': '',      'badge_bg': '',        'badge_color': ''}
_NET_AWS_DATA         = {'title': 'AWS 데이터 VPC',   'badge': 'PRIV',  'badge_bg': '#fef3c7', 'badge_color': '#d97706'}
_NET_AWS_GROUPVM      = {'title': 'AWS 그룹 VM VPC',  'badge': '',      'badge_bg': '',        'badge_color': ''}
_NET_AWS_WEARABLE     = {'title': 'AWS 웨어러블 VPC', 'badge': 'PRIV',  'badge_bg': '#fce7f3', 'badge_color': '#db2777'}
_NET_AWS_MANAGEMENT   = {'title': 'AWS 관리 VPC',     'badge': 'PRIV',  'badge_bg': '#e0e7ff', 'badge_color': '#4f46e5'}
_NET_AWS_CONNECTIVITY = {'title': 'AWS 연결 현황',    'badge': '',      'badge_bg': '',        'badge_color': ''}
_NET_GCP              = {'title': 'GCP',              'badge': '',      'badge_bg': '',        'badge_color': ''}
_NET_ONPREM           = {'title': '온프레미스 (VirtualBox)', 'badge': 'Local Lab', 'badge_bg': '#e0e7ff', 'badge_color': '#4f46e5'}


# ── Wearable 시연 엔진 부팅 (mock_wearable_batch.json 적재 + 3초 tick) ─
_wearable_batch_path = os.path.join(os.path.dirname(__file__), 'mock_wearable_batch.json')
try:
    wearable_engine.load_initial(_wearable_batch_path)
    wearable_engine.start_loop(interval=1.0)
except FileNotFoundError:
    pass   # 운영 단계에선 Kinesis consumer 로 교체 예정 — 파일 없어도 admin 부팅 OK


# ── DB / DynamoDB 헬퍼 ────────────────────────────────
def get_db():
    import pymysql
    return pymysql.connect(
        host=os.environ['AURORA_HOST'],
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASS', 'ChangeMe123!'),
        database=os.environ.get('DB_NAME', 'lifesync360'),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )


_dynamo        = None
_lambda_client = None


def get_dynamo_table():
    global _dynamo
    if _dynamo is None:
        _dynamo = boto3.resource('dynamodb', region_name=AWS_REGION)
    return _dynamo.Table(DYNAMO_TABLE)


def _get_lambda():
    global _lambda_client
    if _lambda_client is None:
        from botocore.config import Config
        # Lambda invoke 응답 안 오면 3초만 기다림 — 화면 hang 방지
        cfg = Config(connect_timeout=3, read_timeout=20, retries={'max_attempts': 1})
        _lambda_client = boto3.client('lambda', region_name=AWS_REGION, config=cfg)
    return _lambda_client


def _call_onprem(action, timeout=8, **kwargs):
    import urllib.request, urllib.parse, json as _j

    global_id = kwargs.get('global_id', '')
    try:
        _prev_gid = f"G{int(global_id[1:]) - 1:09d}" if global_id else ''
    except Exception:
        _prev_gid = ''

    _ROUTES = {
        'local_lab_status':      ('/internal/health/local-lab',              {}),
        'count_master_customer': ('/internal/count/master_customer',         {'status': 'ACTIVE'}),
        'count_users':           ('/internal/count/users',                   {'status': 'ACTIVE'}),
        'count_users_consented': ('/internal/count/users_consented',         {}),
        'get_consent':           (f'/internal/consent/{global_id}',          {}),
        'get_user_by_global':    (f'/internal/auth/user/by_global/{global_id}', {}),
        'get_profile':           (f'/internal/customer/{global_id}',         {}),
        'get_pii':               (f'/internal/pii/{global_id}',              {}),
        'get_profile_demo':      ('/internal/profile/list-all',              {'after': _prev_gid, 'size': '1'}),
        'get_identity_map':      (f'/internal/identity_map/{global_id}',     {}),
    }

    if ONPREM_QUERY_LAMBDA:
        resp   = _get_lambda().invoke(
            FunctionName=ONPREM_QUERY_LAMBDA,
            InvocationType='RequestResponse',
            Payload=_j.dumps({'action': action, **kwargs}),
        )
        result = _j.loads(resp['Payload'].read())
        if result.get('statusCode') != 200:
            return {}
        body = result.get('body', '{}')
        return _j.loads(body) if isinstance(body, str) else body

    if ONPREM_BASE_URL and action in _ROUTES:
        path, params = _ROUTES[action]
        qs = ('?' + urllib.parse.urlencode(params)) if params else ''
        url = f'{ONPREM_BASE_URL.rstrip("/")}{path}{qs}'
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as resp:
                return _j.loads(resp.read())
        except Exception:
            return {}

    return {}


def _load_consent_from_s3(global_id):
    """동의 스냅샷 일배치 결과 조회 (lifesync-raw/consent/dt=오늘/{gid}.json).

    consent_snapshot_aggregator Lambda 가 매일 KST 03:00 적재.
    오늘자 객체 없으면 어제 fallback. 둘 다 없으면 빈 결과.
    응답 구조: {global_id, ls_user_id, user_status, consents: [...], snapshot_dt}
    """
    import datetime as _dt
    bucket = os.environ.get('LIFESYNC_RAW_S3_BUCKET', '')
    if not bucket:
        return {'global_id': global_id, 'consents': []}
    kst = _dt.timezone(_dt.timedelta(hours=9))
    today = _dt.datetime.now(kst).date()
    for offset in (0, 1):    # 오늘 미적재 시 어제 fallback
        key = f"consent/dt={(today - _dt.timedelta(days=offset)).isoformat()}/{global_id}.json"
        try:
            import json as _j
            obj = _boto('s3').get_object(Bucket=bucket, Key=key)
            return _j.loads(obj['Body'].read())
        except Exception:
            continue
    return {'global_id': global_id, 'consents': []}


# ── boto3 ping 헬퍼 (운영 모니터링·Cloud Status용) ──────────
_boto_clients = {}


def _boto(service):
    if service not in _boto_clients:
        _boto_clients[service] = boto3.client(service, region_name=AWS_REGION)
    return _boto_clients[service]


def _ping_cloud_status():
    """Cloud Status 카드 — AWS 리소스 6종 describe."""
    out = []
    try:
        clusters = _boto('rds').describe_db_clusters().get('DBClusters', [])
        ok = sum(1 for c in clusters if c.get('Status') == 'available')
        out.append({'service': 'AWS Aurora', 'state': 'UP' if ok else 'DOWN', 'note': f'{ok}/{len(clusters)} clusters available'})
    except Exception as e:
        out.append({'service': 'AWS Aurora', 'state': 'ERR', 'note': str(e)[:60]})
    try:
        tables = _boto('dynamodb').list_tables().get('TableNames', [])
        out.append({'service': 'AWS DynamoDB', 'state': 'UP', 'note': f'{len(tables)} tables'})
    except Exception as e:
        out.append({'service': 'AWS DynamoDB', 'state': 'ERR', 'note': str(e)[:60]})
    try:
        caches = _boto('elasticache').describe_cache_clusters().get('CacheClusters', [])
        ok = sum(1 for c in caches if c.get('CacheClusterStatus') == 'available')
        out.append({'service': 'AWS ElastiCache', 'state': 'UP' if ok else 'DOWN', 'note': f'{ok}/{len(caches)} clusters'})
    except Exception as e:
        out.append({'service': 'AWS ElastiCache', 'state': 'ERR', 'note': str(e)[:60]})
    try:
        clusters = _boto('ecs').list_clusters().get('clusterArns', [])
        out.append({'service': 'AWS ECS', 'state': 'UP' if clusters else 'DOWN', 'note': f'{len(clusters)} clusters'})
    except Exception as e:
        out.append({'service': 'AWS ECS', 'state': 'ERR', 'note': str(e)[:60]})
    try:
        lbs = _boto('elbv2').describe_load_balancers().get('LoadBalancers', [])
        ok = sum(1 for l in lbs if l.get('State', {}).get('Code') == 'active')
        out.append({'service': 'AWS ALB', 'state': 'UP' if ok else 'DOWN', 'note': f'{ok}/{len(lbs)} active'})
    except Exception as e:
        out.append({'service': 'AWS ALB', 'state': 'ERR', 'note': str(e)[:60]})
    try:
        buckets = [b for b in _boto('s3').list_buckets().get('Buckets', []) if b.get('Name', '').startswith('lifesync')]
        out.append({'service': 'AWS S3', 'state': 'UP', 'note': f'{len(buckets)} buckets'})
    except Exception as e:
        out.append({'service': 'AWS S3', 'state': 'ERR', 'note': str(e)[:60]})
    return out


_RAW_DOMAIN_PREFIXES = (
    'bank/', 'card/', 'insurance/', 'securities/',
    'healthcare/', 'hospital/', 'wearable/', 'online_insurance/',
)


def _ping_s3_ingestion():
    """S3 Data Ingestion — raw bucket 적재 현황.

    전체 객체 수는 CloudWatch S3 NumberOfObjects metric (일배치, 1일 지연).
    today/iot/latest 는 도메인 prefix 별 MaxKeys=1000 조회 (페이지네이션 회피).
    """
    raw_bucket = os.environ.get('LIFESYNC_RAW_S3_BUCKET', 'lifesync-raw')
    from datetime import datetime, timezone, timedelta
    today_date = datetime.now(timezone(timedelta(hours=9))).date()  # KST 기준
    today_prefix = today_date.strftime('%Y-%m-%d')
    total = 0
    try:
        cw = _boto('cloudwatch')
        now = datetime.now(timezone.utc)
        resp = cw.get_metric_statistics(
            Namespace='AWS/S3', MetricName='NumberOfObjects',
            Dimensions=[{'Name': 'BucketName', 'Value': raw_bucket},
                        {'Name': 'StorageType', 'Value': 'AllStorageTypes'}],
            StartTime=now - timedelta(days=3), EndTime=now,
            Period=86400, Statistics=['Average'])
        pts = sorted(resp.get('Datapoints', []), key=lambda d: d['Timestamp'], reverse=True)
        total = int(pts[0]['Average']) if pts else 0
    except Exception:
        pass
    try:
        s3 = _boto('s3')
        paginator = s3.get_paginator('list_objects_v2')
        today = iot = 0
        total_size = 0
        latest = None
        for prefix in _RAW_DOMAIN_PREFIXES:
            for page in paginator.paginate(Bucket=raw_bucket, Prefix=prefix,
                                           PaginationConfig={'MaxItems': 500}):
                for o in page.get('Contents', []):
                    total_size += o.get('Size', 0)
                    if today_prefix in o['Key']:
                        today += 1
                    if 'wearable' in prefix or 'iot' in o['Key'].lower():
                        iot += 1
                    if latest is None or o['LastModified'] > latest['LastModified']:
                        latest = o
        processed_count = curated_count = 0
        try:
            proc_bucket = os.environ.get('LIFESYNC_PROCESSED_S3_BUCKET', 'lifesync-processed')
            proc_resp = s3.list_objects_v2(Bucket=proc_bucket, Delimiter='/')
            proc_prefixes = [p.get('Prefix', '') for p in proc_resp.get('CommonPrefixes', [])
                             if not p.get('Prefix', '').startswith('_')]
            for pp in proc_prefixes:
                for pg in paginator.paginate(Bucket=proc_bucket, Prefix=pp,
                                             PaginationConfig={'MaxItems': 200}):
                    processed_count += len(pg.get('Contents', []))
        except Exception:
            pass
        try:
            cur_bucket = os.environ.get('LIFESYNC_CURATED_S3_BUCKET', 'lifesync-curated')
            cur_resp = s3.list_objects_v2(Bucket=cur_bucket, Delimiter='/')
            curated_count = len([p for p in cur_resp.get('CommonPrefixes', [])
                                 if not p.get('Prefix', '').startswith('_')])
        except Exception:
            pass
        return {
            'raw_bucket_files': total,
            'today_ingested':   today,
            'iot_count':        iot,
            'total_size_bytes': total_size,
            'processed_count':  processed_count,
            'curated_count':    curated_count,
            'last_upload': {
                'time': latest['LastModified'].strftime('%H:%M') if latest else '-',
                'file': latest['Key'].split('/')[-1] if latest else '-',
                'size_mb': round(latest['Size'] / 1024 / 1024, 2) if latest else 0,
            } if latest else {},
            'failed_count': 0,
        }
    except Exception:
        return {'raw_bucket_files': total, 'today_ingested': 0, 'iot_count': 0,
                'processed_count': 0, 'curated_count': 0,
                'total_size_bytes': 0, 'last_upload': {}, 'failed_count': 0}


def _ping_vm_status():
    """Group/Wearable VM EC2 상태.

    lifesync-*-vpc 동적 발견 → 해당 VPC 내 EC2 만 매칭.
    group/wearable 구분은 VPC Name 키워드로 결정 (deploy_group 필드).
    """
    try:
        ec2  = _boto('ec2')
        vpcs = ec2.describe_vpcs(Filters=[
            {'Name': 'tag:Name', 'Values': ['lifesync-*-vpc']},
        ])
        vpc_map = {
            v['VpcId']: next((t['Value'] for t in v.get('Tags', []) if t['Key'] == 'Name'), '')
            for v in vpcs.get('Vpcs', [])
        }
        if not vpc_map:
            return []
        resp = ec2.describe_instances(Filters=[
            {'Name': 'vpc-id', 'Values': list(vpc_map.keys())},
            {'Name': 'instance-state-name', 'Values': ['running', 'pending', 'stopping', 'stopped']},
        ])
        out = []
        for r in resp.get('Reservations', []):
            for inst in r.get('Instances', []):
                tags     = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
                vpc_name = vpc_map.get(inst.get('VpcId'), '')
                if   'group'      in vpc_name: deploy_group = 'group-app'
                elif 'wearable'   in vpc_name: deploy_group = 'wearable-app'
                elif 'management' in vpc_name: deploy_group = 'management'
                elif 'lifesync'   in vpc_name: deploy_group = 'platform'
                else:                          deploy_group = 'other'
                out.append({
                    'vm_id':        inst['InstanceId'],
                    'name':         tags.get('Name', '-'),
                    'state':        inst['State']['Name'],
                    'deploy_group': deploy_group,
                    'vpc':          vpc_name,
                    'cpu_pct': 0,
                    'mem_pct': None,
                })
        _boost_vm_cpu(out)
        return out
    except Exception:
        return []


def _boost_vm_cpu(rows):
    """AWS/EC2 CPUUtilization + LifeSync/EC2 mem_used_percent 최근 10분 평균을 batch로 가져와 보강.

    get_metric_data 1회 호출로 CPU + 메모리 모든 인스턴스를 한꺼번에. 실패 시 기존값 유지.
    """
    if not rows:
        return
    from datetime import datetime, timezone, timedelta
    try:
        cw    = _boto('cloudwatch')
        now   = datetime.now(timezone.utc)
        start = now - timedelta(minutes=30)
        queries = []
        for i, r in enumerate(rows):
            queries.append({
                'Id': f'cpu{i}',
                'MetricStat': {
                    'Metric': {
                        'Namespace': 'AWS/EC2',
                        'MetricName': 'CPUUtilization',
                        'Dimensions': [{'Name': 'InstanceId', 'Value': r['vm_id']}],
                    },
                    'Period': 300, 'Stat': 'Average',
                },
                'ReturnData': True,
            })
            queries.append({
                'Id': f'mem{i}',
                'MetricStat': {
                    'Metric': {
                        'Namespace': 'LifeSync/EC2',
                        'MetricName': 'mem_used_percent',
                        'Dimensions': [{'Name': 'InstanceId', 'Value': r['vm_id']}],
                    },
                    'Period': 300, 'Stat': 'Average',
                },
                'ReturnData': True,
            })
        res = cw.get_metric_data(MetricDataQueries=queries, StartTime=start, EndTime=now)
        by_id = {m['Id']: m.get('Values') or [] for m in res.get('MetricDataResults', [])}
        for i, r in enumerate(rows):
            cpu_vals = by_id.get(f'cpu{i}', [])
            if cpu_vals:
                r['cpu_pct'] = round(cpu_vals[0], 1)
            mem_vals = by_id.get(f'mem{i}', [])
            if mem_vals:
                r['mem_pct'] = round(mem_vals[0], 1)
    except Exception:
        pass


def _list_lifesync_lambdas():
    """`LAMBDA_PREFIX_FILTER` (기본 `lifesync-`) prefix Lambda 함수 자동 발견.

    boto3 lambda.list_functions paginator — 신규 함수 배포 시 코드 변경 없이 자동 포함.
    실패 시 빈 list 반환 (호출처 fallback 처리).
    """
    prefix = os.environ.get('LAMBDA_PREFIX_FILTER', 'lifesync-')
    try:
        paginator = _boto('lambda').get_paginator('list_functions')
        names = []
        for page in paginator.paginate():
            for fn in page.get('Functions', []):
                name = fn.get('FunctionName', '')
                if name.startswith(prefix):
                    names.append(name)
        return sorted(names)
    except Exception:
        return []


def _ping_glue_last_run():
    """Glue Job 최근 run."""
    job = os.environ.get('GLUE_JOB_PHYSICAL_NAME', 'lifesync-etl')
    try:
        runs = _boto('glue').get_job_runs(JobName=job, MaxResults=1).get('JobRuns', [])
        if not runs:
            return {}
        r = runs[0]
        return {
            'job_name':     job,
            'state':        r.get('JobRunState'),
            'started_at':   r['StartedOn'].strftime('%Y-%m-%d %H:%M:%S') if r.get('StartedOn') else '-',
            'completed_at': r['CompletedOn'].strftime('%Y-%m-%d %H:%M:%S') if r.get('CompletedOn') else '-',
            'duration_sec': int(r.get('ExecutionTime') or 0),
        }
    except Exception:
        return {}


# ── 멀티클라우드 — TGW / VPN ping ───────────
def _ping_tgw():
    try:
        tgws = _boto('ec2').describe_transit_gateways().get('TransitGateways', [])
        if not tgws:
            return {}
        t = tgws[0]
        atts = _boto('ec2').describe_transit_gateway_attachments(
            Filters=[{'Name': 'transit-gateway-id', 'Values': [t['TransitGatewayId']]}]
        ).get('TransitGatewayAttachments', [])
        return {
            'id':           t['TransitGatewayId'],
            'state':        t.get('State', '-'),
            'attachments': len([a for a in atts if a.get('State') == 'available']),
            'note':         t.get('Description', '-'),
        }
    except Exception:
        return {}


def _ping_vpn():
    try:
        ec2  = _boto('ec2')
        conns = [c for c in ec2.describe_vpn_connections().get('VpnConnections', []) if c.get('State') != 'deleted']
        cgw_cache = {}
        out = []
        connections = []
        for c in conns:
            cgw_id = c.get('CustomerGatewayId', '')
            if cgw_id and cgw_id not in cgw_cache:
                try:
                    cgw = ec2.describe_customer_gateways(CustomerGatewayIds=[cgw_id]).get('CustomerGateways', [])
                    cgw_cache[cgw_id] = cgw[0] if cgw else {}
                except Exception:
                    cgw_cache[cgw_id] = {}
            cgw_info = cgw_cache.get(cgw_id, {})
            tag_name = next((t['Value'] for t in c.get('Tags', []) if t.get('Key') == 'Name'), '-')
            conn_tunnels = []
            for t in c.get('VgwTelemetry', []) or [{'OutsideIpAddress': '-', 'Status': '-'}]:
                tunnel = {
                    'id':               f"{c['VpnConnectionId']}-{t.get('OutsideIpAddress', '?')}",
                    'status':           t.get('Status', '-').upper(),
                    'bgp_asn':          str(cgw_info.get('BgpAsn', '-')),
                    'traffic_in_mbps':  0,
                    'traffic_out_mbps': 0,
                    'peer':             cgw_info.get('IpAddress', tag_name),
                }
                out.append(tunnel)
                conn_tunnels.append(tunnel)
            up = sum(1 for t in conn_tunnels if t.get('status') == 'UP')
            connections.append({
                'name':    tag_name,
                'id':      c.get('VpnConnectionId', ''),
                'peer':    cgw_info.get('IpAddress', '-'),
                'tunnels': conn_tunnels,
                'up':      up,
                'total':   len(conn_tunnels),
            })
        return {'tunnels': out, 'connections': connections}
    except Exception:
        return {}


def _ping_kinesis():
    """
    P1 r23, P4 r15,r16. Kinesis 스트림 상태 + 데이터 처리 지연.
    INGESTION_STREAM_NAME (default 'lifesync-kinesis-wearable-stream') 단건 조회.
    실패/스트림 없음 시 빈 dict.
    """
    from datetime import datetime, timezone, timedelta
    stream = os.environ.get('INGESTION_STREAM_NAME', 'lifesync-kinesis-wearable-stream')
    try:
        info = _boto('kinesis').describe_stream_summary(StreamName=stream).get('StreamDescriptionSummary', {})
    except Exception:
        return {}
    out = {
        'stream_name'  : info.get('StreamName', stream),
        'status'       : info.get('StreamStatus', 'UNKNOWN'),
        'shard_count'  : info.get('OpenShardCount', 0),
        'retention_hrs': info.get('RetentionPeriodHours', 0),
    }
    # CloudWatch 평균 IteratorAgeMilliseconds (최근 5분)
    try:
        cw    = _boto('cloudwatch')
        now   = datetime.now(timezone.utc)
        start = now - timedelta(minutes=5)
        stat  = cw.get_metric_statistics(
            Namespace='AWS/Kinesis', MetricName='GetRecords.IteratorAgeMilliseconds',
            Dimensions=[{'Name': 'StreamName', 'Value': stream}],
            StartTime=start, EndTime=now, Period=60, Statistics=['Average'],
        )
        pts = stat.get('Datapoints', [])
        out['iterator_age_avg_ms'] = round(sum(p['Average'] for p in pts) / len(pts), 1) if pts else 0
    except Exception:
        out['iterator_age_avg_ms'] = None
    return out


def _ping_wearable_metrics():
    """
    P4 r45~r52. Wearable custom namespace 'LifeSync/Wearable' 5분 평균.
    metrics: heart_rate / blood_pressure_sys / blood_pressure_dia / spo2 / steps / alerts.
    """
    from datetime import datetime, timezone, timedelta
    try:
        cw    = _boto('cloudwatch')
        now   = datetime.now(timezone.utc)
        start = now - timedelta(minutes=5)
    except Exception:
        return []
    out = []
    for metric, label in [
        ('heart_rate',        '심박수'),
        ('blood_pressure_sys','수축기혈압'),
        ('blood_pressure_dia','이완기혈압'),
        ('spo2',              '산소포화도'),
        ('steps',             '걸음수'),
        ('activity_kcal',     '활동칼로리'),
        ('alerts',            '이상이벤트'),
    ]:
        try:
            stat = cw.get_metric_statistics(
                Namespace='LifeSync/Wearable', MetricName=metric,
                StartTime=start, EndTime=now, Period=60, Statistics=['Average','Sum'],
            )
            pts = stat.get('Datapoints', [])
            if pts:
                avg = round(sum(p.get('Average', 0) for p in pts) / len(pts), 1)
                tot = round(sum(p.get('Sum', 0) for p in pts), 1)
                out.append({'metric': metric, 'label': label, 'avg': avg, 'sum': tot})
            else:
                out.append({'metric': metric, 'label': label, 'avg': None, 'sum': 0})
        except Exception:
            out.append({'metric': metric, 'label': label, 'avg': None, 'sum': 0})
    return out


def _ping_emr():
    """
    P4 r13. EMR 클러스터 상태 (lifesync 태그 또는 RUNNING/WAITING).
    """
    try:
        clusters = _boto('emr').list_clusters(
            ClusterStates=['STARTING','BOOTSTRAPPING','RUNNING','WAITING','TERMINATING']
        ).get('Clusters', [])
    except Exception:
        return []
    return [{
        'cluster_id'  : c.get('Id'),
        'name'        : c.get('Name'),
        'state'       : c.get('Status', {}).get('State'),
        'state_change_at': str(c.get('Status', {}).get('StateChangeReason', {}).get('Code') or ''),
    } for c in clusters]


def _ddb_score_distribution():
    """
    P3 r22. lifesync_customer_result Scan + dynamic_score 0~100 히스토그램.
    Scan 비용 주의 — 운영은 lambda 일배치 결과를 mart 테이블에 두고 read 권장.
    """
    try:
        items = get_dynamo_table().scan(ProjectionExpression='dynamic_score').get('Items', [])
    except Exception:
        return []
    buckets = [0]*10  # 0~9, 10~19, ..., 90~100
    for it in items:
        try:
            s = int(float(it.get('dynamic_score', 0)))
            idx = min(s // 10, 9)
            buckets[idx] += 1
        except Exception:
            continue
    return [{'bucket': f'{i*10}~{i*10+9}', 'count': buckets[i]} for i in range(10)]


def _ddb_prob_distribution():
    """
    P3 r8. lifesync_customer_result Scan + vip_prob/signup_prob/rec_prob 평균 + 0.0~1.0 히스토그램.
    """
    try:
        items = get_dynamo_table().scan(
            ProjectionExpression='vip_prob, signup_prob, rec_prob'
        ).get('Items', [])
    except Exception:
        return {}
    sums  = {'vip_prob': 0.0, 'signup_prob': 0.0, 'rec_prob': 0.0}
    cnts  = {'vip_prob': 0,   'signup_prob': 0,   'rec_prob': 0}
    bins  = {k: [0]*10 for k in sums}  # 0.0~0.1, ..., 0.9~1.0
    for it in items:
        for k in sums:
            try:
                v = float(it.get(k, 0))
                sums[k] += v
                cnts[k] += 1
                idx = min(int(v * 10), 9)
                bins[k][idx] += 1
            except Exception:
                continue
    return {
        'avg': {k: round(sums[k] / cnts[k], 3) if cnts[k] else 0 for k in sums},
        'histogram': {k: [{'bin': f'{i*0.1:.1f}~{(i+1)*0.1:.1f}', 'count': bins[k][i]} for i in range(10)] for k in bins},
    }


# ── GCP SDK 헬퍼 ────────────────────────────────────────────
# 인증: ADC (Application Default Credentials) — GOOGLE_APPLICATION_CREDENTIALS env
#   또는 Workload Identity Federation. 인증 없으면 모든 함수가 안전하게 [] / {} 반환.
GCP_BQ_DATASET  = os.environ.get('GCP_BQ_DATASET', 'lifesync_curated')
GCP_VERTEX_LOC  = os.environ.get('GCP_VERTEX_LOCATION', 'asia-northeast3')

def _gcp_project():
    return os.environ.get('GCP_PROJECT_ID', '')

_gcp_bq_client      = None
_gcp_aip_initialized= False
_gcp_mon_client     = None


def _get_bq():
    global _gcp_bq_client
    pid = _gcp_project()
    if not pid:
        return None
    if _gcp_bq_client is None:
        try:
            from google.cloud import bigquery as _bq
            _gcp_bq_client = _bq.Client(project=pid)
        except Exception:
            return None
    return _gcp_bq_client


def _init_aip():
    global _gcp_aip_initialized
    if not _gcp_project():
        return False
    if not _gcp_aip_initialized:
        try:
            from google.cloud import aiplatform
            aiplatform.init(project=_gcp_project(), location=GCP_VERTEX_LOC)
            _gcp_aip_initialized = True
        except Exception:
            return False
    return _gcp_aip_initialized


def _get_mon():
    global _gcp_mon_client
    if not _gcp_project():
        return None
    if _gcp_mon_client is None:
        try:
            from google.cloud import monitoring_v3 as _mon
            _gcp_mon_client = _mon.MetricServiceClient()
        except Exception:
            return None
    return _gcp_mon_client


def _gcp_reachable(host='monitoring.googleapis.com', port=443, timeout=2.0):
    import socket
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except Exception:
        return False


def _stub_gcp_status():
    """
    P4 r32~36 — GCP BigQuery / Vertex AI / Cloud Run 상태.
    Cloud Monitoring API 로 service 별 uptime/health 조회. 인증/호출 실패 시 빈 list.
    """
    if not _gcp_project():
        return []
    if not _gcp_reachable():
        return [
            {'service': 'BigQuery',  'state': 'UNKNOWN', 'error': 'GCP API unreachable from this network'},
            {'service': 'Vertex AI', 'state': 'UNKNOWN', 'error': 'GCP API unreachable from this network'},
            {'service': 'Cloud Run', 'state': 'UNKNOWN', 'error': 'GCP API unreachable from this network'},
        ]
    mon = _get_mon()
    if mon is None:
        return []
    try:
        from google.cloud import monitoring_v3 as _mon
        from google.protobuf import timestamp_pb2
        import time
        now      = int(time.time())
        interval = _mon.TimeInterval({
            'end_time':   timestamp_pb2.Timestamp(seconds=now),
            'start_time': timestamp_pb2.Timestamp(seconds=now - 7 * 86400),
        })
        out = []
        for service, metric in [
            ('BigQuery',  'bigquery.googleapis.com/query/count'),
            ('Vertex AI', 'aiplatform.googleapis.com/prediction/online/prediction_count'),
            ('Cloud Run', 'run.googleapis.com/request_count'),
        ]:
            try:
                req = _mon.ListTimeSeriesRequest({
                    'name':     f'projects/{_gcp_project()}',
                    'filter':   f'metric.type="{metric}"',
                    'interval': interval,
                    'view':     _mon.ListTimeSeriesRequest.TimeSeriesView.HEADERS,
                })
                series = list(mon.list_time_series(request=req, timeout=5.0))
                out.append({'service': service, 'state': 'UP', 'series_count': len(series)})
            except Exception as e:
                out.append({'service': service, 'state': 'UNKNOWN', 'error': str(e)[:80]})
        return out
    except Exception:
        return []


def _stub_vertex_metrics():
    """
    P3 r22 — Vertex AI 모델 평가 메트릭 (Precision/Recall 등).
    Model.list() → 최신 모델의 evaluation 가져옴.
    """
    if not _init_aip():
        return {}
    try:
        from google.cloud import aiplatform
        models = aiplatform.Model.list(order_by='create_time desc')
        if not models:
            return {}
        model_list = [
            {'model_id': m.resource_name, 'display_name': m.display_name, 'create_time': str(m.create_time)}
            for m in models[:10]
        ]
        latest = models[0]
        evals  = latest.list_model_evaluations()
        base = {
            'model_id'    : latest.resource_name,
            'display_name': latest.display_name,
            'create_time' : str(latest.create_time),
            'models'      : model_list,
        }
        if not evals:
            return {**base, 'evaluations': []}
        ev = list(evals)[0]
        return {**base, 'metrics': dict(ev.metrics) if hasattr(ev, 'metrics') else {}}
    except Exception:
        return {}


def _stub_bigquery_analytics(query_kind='recommendation_mart'):
    """
    P3 r17,r28 — BigQuery 마트 ad-hoc 조회.
      recommendation_mart : lifesync_curated.recommendation_mart GROUP BY name
      customer_summary    : lifesync_serving.v_customer_summary 샘플
      prediction_result   : lifesync_ml.*_prediction_result Precision/Recall
    """
    bq = _get_bq()
    if bq is None:
        return []
    try:
        if query_kind == 'recommendation_mart':
            sql = f"""SELECT recommendation_name, COUNT(*) AS cnt
                      FROM `{_gcp_project()}.{GCP_BQ_DATASET}.recommendation_mart`
                      GROUP BY recommendation_name ORDER BY cnt DESC LIMIT 20"""
        elif query_kind == 'customer_summary':
            sql = f"""SELECT * FROM `{_gcp_project()}.lifesync_serving.v_customer_summary` LIMIT 100"""
        elif query_kind == 'prediction_result':
            sql = f"""SELECT model_name,
                             COUNTIF(actual_label IS NOT NULL) AS labeled,
                             AVG(IF(predicted_label = actual_label, 1.0, 0.0)) AS accuracy
                      FROM `{_gcp_project()}.lifesync_ml.vip_prediction_result`
                      WHERE actual_label IS NOT NULL
                      GROUP BY model_name"""
        elif query_kind == 'model_metrics':
            sql = f"""SELECT model_name, auc, accuracy, precision, recall, mae, train_size, test_size, trained_at
                      FROM `{_gcp_project()}.lifesync_ml.model_metrics`
                      ORDER BY trained_at DESC"""
        else:
            return []
        return [dict(row) for row in bq.query(sql).result()]
    except Exception:
        return []


_redis_client = None

_ddb_ai_target_cache  = {'value': None, 'ts': 0.0}
_DDB_AI_TARGET_TTL    = 300
_aurora_ctr_cvr_cache = {'value': None, 'ts': 0.0}
_AURORA_CTR_CVR_TTL   = 300

_redis_rec_cache = {'value': None, 'ts': 0.0}
_REDIS_REC_TTL   = 300  # 5분

_onprem_counts_cache = {'value': None, 'ts': 0.0}
_ONPREM_COUNTS_TTL   = 300  # 5분 — on-prem count 3종 묶음 캐시

_aurora_dash_cache = {'value': None, 'ts': 0.0}
_AURORA_DASH_TTL   = 300  # 5분 — recommend_history 통계 + dashboard_log count

_dash_summary_cache = {'value': None, 'ts': 0.0}
_DASH_SUMMARY_TTL   = 300  # 5분 — 대시보드 KPI 전체 결과 캐시

def _get_redis():
    global _redis_client
    if _redis_client is None:
        host = os.environ.get('REDIS_HOST')
        if not host:
            return None
        try:
            import redis as _redis_lib
            _redis_client = _redis_lib.Redis(
                host=host,
                port=int(os.environ.get('REDIS_PORT', '6379')),
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
        except Exception:
            return None
    return _redis_client


def _stub_redis_personalized(global_id):
    r = _get_redis()
    if r is None:
        return {}
    try:
        key = f'rec:{global_id}'
        ktype = r.type(key)
        if ktype == 'zset':
            pairs = r.zrevrange(key, 0, 2, withscores=True)
            if not pairs:
                return {}
            return {
                'top': [{'product_id': pid} for pid, _ in pairs],
                'source': 'redis',
            }
        elif ktype == 'string':
            raw = r.get(key)
            if not raw:
                return {}
            ids = json.loads(raw)
            if not isinstance(ids, list) or not ids:
                return {}
            return {
                'top': [{'product_id': str(pid)} for pid in ids[:3]],
                'source': 'redis',
            }
        return {}
    except Exception:
        return {}


# ── analytics batch 결과 read 헬퍼 (P3 r10/r12/r13) ─────────────
def _aurora_recommend_trend_7day():
    """7일 추이 — customer_recommend_history GROUP BY DATE, 최신 7일만. V6 R10/R11."""
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT DATE(recommended_at) AS date, "
                "       COUNT(*) AS recommended, "
                "       SUM(clicked_flag IN ('Y','1')) AS clicked, "
                "       SUM(purchased_flag IN ('Y','1')) AS purchased, "
                "       ROUND(SUM(clicked_flag IN ('Y','1')) * 100.0 / COUNT(*), 2) AS ctr, "
                "       ROUND(SUM(purchased_flag IN ('Y','1')) * 100.0 / COUNT(*), 2) AS cvr "
                "FROM customer_recommend_history "
                "WHERE recommended_at >= DATE_SUB(CURDATE(), INTERVAL 8 DAY) "
                "GROUP BY DATE(recommended_at) "
                "ORDER BY date DESC LIMIT 7"
            )
            rows = list(reversed(cur.fetchall()))
        return [
            {
                'date':        r['date'].strftime('%m-%d') if r.get('date') else '',
                'recommended': int(r.get('recommended') or 0),
                'clicked':     int(r.get('clicked') or 0),
                'purchased':   int(r.get('purchased') or 0),
                'ctr':         float(r.get('ctr') or 0),
                'cvr':         float(r.get('cvr') or 0),
            }
            for r in rows
        ]
    except Exception:
        return []


def _aurora_recommend_top10():
    """상품별 추천 건수 TOP10 — 최근 7일. V6 AI추천 R12."""
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT p.product_name AS product, "
                "       cat.category_name AS category, "
                "       COUNT(*) AS recommended, "
                "       SUM(r.clicked_flag IN ('Y','1')) AS clicked, "
                "       SUM(r.purchased_flag IN ('Y','1')) AS purchased, "
                "       ROUND(SUM(r.clicked_flag IN ('Y','1')) * 100.0 / COUNT(*), 1) AS ctr, "
                "       ROUND(SUM(r.purchased_flag IN ('Y','1')) * 100.0 / COUNT(*), 1) AS cvr "
                "FROM customer_recommend_history r "
                "JOIN product_master p   ON r.product_id  = p.product_id "
                "JOIN category_master cat ON p.category_id = cat.category_id "
                "WHERE r.recommended_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) "
                "GROUP BY p.product_id, p.product_name, cat.category_name "
                "ORDER BY recommended DESC LIMIT 10"
            )
            rows = cur.fetchall()
        return [
            {
                'rank':        i + 1,
                'product':     r['product'],
                'category':    r['category'],
                'recommended': int(r.get('recommended') or 0),
                'clicked':     int(r.get('clicked') or 0),
                'purchased':   int(r.get('purchased') or 0),
                'ctr':         float(r.get('ctr') or 0),
                'cvr':         float(r.get('cvr') or 0),
            }
            for i, r in enumerate(rows)
        ]
    except Exception:
        return []


def _ddb_grade_dist():
    """DDB lifesync_customer_result.dynamic_grade 분포 (S~D 5단계)."""
    try:
        items = get_dynamo_table().scan(ProjectionExpression='dynamic_grade').get('Items', [])
    except Exception:
        return []
    counts, total = {}, 0
    for it in items:
        g = it.get('dynamic_grade') or ''
        if not g:
            continue
        counts[g] = counts.get(g, 0) + 1
        total += 1
    if not total:
        return []
    color_map = {'VIP': '#dc2626', 'GOLD': '#f59e0b', 'SILVER': '#3b82f6', 'BASIC': '#16a34a', 'CARE': '#94a3b8'}
    return [
        {'grade': g, 'count': c,
         'color': color_map.get(g, '#94a3b8'),
         'pct':   round(c * 100.0 / total, 1)}
        for g, c in sorted(counts.items())
    ]


def _aurora_action_code_rec_data():
    """action_code별 추천 수 — 최근 7일."""
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT action_code AS name, COUNT(*) AS count "
                "FROM customer_recommend_history "
                "WHERE recommended_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) "
                "GROUP BY action_code ORDER BY count DESC LIMIT 8"
            )
            return [{'name': r['name'] or '-', 'count': int(r['count'] or 0)} for r in cur.fetchall()]
    except Exception:
        return []


def _aurora_pr_models():
    """ml_model_evaluation_daily 최신 모델별 Precision."""
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT model_name AS name, "
                "       ROUND(precision_score * 100, 1) AS `precision` "
                "FROM ml_model_evaluation_daily "
                "ORDER BY eval_date DESC LIMIT 4"
            )
            return [
                {'name': r['name'], 'precision': float(r['precision'] or 0)}
                for r in cur.fetchall()
            ]
    except Exception:
        return []


def _aurora_ai_kpi():
    """AI KPI — customer_recommend_history 7일 평균 CTR/CVR + BigQuery model_metrics 최신 지표."""
    result = {'ctr_7d': None, 'cvr_7d': None, 'accuracy': None, 'precision': None}
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT ROUND(SUM(clicked_flag IN ('Y','1')) * 100.0 / COUNT(*), 1) AS ctr_7d, "
                "       ROUND(SUM(purchased_flag IN ('Y','1')) * 100.0 / COUNT(*), 1) AS cvr_7d "
                "FROM customer_recommend_history "
                "WHERE recommended_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
            )
            row = cur.fetchone() or {}
            if row.get('ctr_7d') is not None:
                result['ctr_7d'] = float(row['ctr_7d'])
            if row.get('cvr_7d') is not None:
                result['cvr_7d'] = float(row['cvr_7d'])
    except Exception:
        pass
    try:
        bq = _get_bq()
        if bq:
            proj = _gcp_project()
            sql = (
                f"SELECT ROUND(accuracy * 100, 1) AS accuracy, "
                f"       ROUND(precision, 4) AS precision_score "
                f"FROM `{proj}.lifesync_ml.model_metrics` "
                f"WHERE model_name = 'vip' "
                f"ORDER BY trained_at DESC LIMIT 1"
            )
            rows = list(bq.query(sql).result())
            if rows:
                row = dict(rows[0])
                if row.get('accuracy') is not None:
                    result['accuracy'] = float(row['accuracy'])
                if row.get('precision_score') is not None:
                    result['precision'] = float(row['precision_score'])
    except Exception:
        pass
    if result.get('accuracy') is None:
        try:
            with get_db() as db, db.cursor() as cur:
                cur.execute(
                    "SELECT ROUND(accuracy * 100, 1) AS accuracy, "
                    "       ROUND(precision_score, 4) AS precision_score "
                    "FROM ml_model_evaluation_daily "
                    "ORDER BY eval_date DESC LIMIT 1"
                )
                row = cur.fetchone() or {}
                if row.get('accuracy') is not None:
                    result['accuracy'] = float(row['accuracy'])
                if row.get('precision_score') is not None:
                    result['precision'] = float(row['precision_score'])
        except Exception:
            pass
    result.pop('recall', None)
    result.pop('pr_combined', None)
    return result


def _ddb_score_histogram_for_ai():
    """AI 예측 출현 분포 — dynamic_score 5-bucket 히스토그램 (chart histogram 용)."""
    try:
        items = get_dynamo_table().scan(ProjectionExpression='dynamic_score').get('Items', [])
    except Exception:
        return []
    buckets = [('0-20', '#ef4444'), ('20-40', '#f59e0b'), ('40-60', '#facc15'),
               ('60-80', '#3b82f6'), ('80-100', '#16a34a')]
    counts = [0, 0, 0, 0, 0]
    for it in items:
        try:
            v = float(it.get('dynamic_score') or 0)
        except Exception:
            continue
        idx = 4 if v >= 80 else 3 if v >= 60 else 2 if v >= 40 else 1 if v >= 20 else 0
        counts[idx] += 1
    return [{'bucket': b, 'count': c, 'color': col} for (b, col), c in zip(buckets, counts) if c]


def _ddb_query_today(table_name, sk_prefix=None, sk_attr='segment_key'):
    """analytics_* DDB 테이블 오늘 snapshot_date 조회. 오늘 데이터 없으면 최근 3일까지 fallback."""
    from datetime import date as _date, timedelta as _td
    from boto3.dynamodb.conditions import Key
    ddb_table = boto3.resource('dynamodb', region_name=AWS_REGION).Table(table_name)
    for delta in range(3):
        d = (_date.today() - _td(days=delta)).isoformat()
        try:
            kw = {'KeyConditionExpression': Key('snapshot_date').eq(d)}
            if sk_prefix:
                kw['KeyConditionExpression'] &= Key(sk_attr).begins_with(sk_prefix)
            result = ddb_table.query(**kw).get('Items', [])
            if result:
                return result
        except Exception:
            continue
    return []


def _aurora_customer_insight():
    """고객 인사이트 분석 — Aurora customer_recommend_history 전체 집계."""
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT global_id) AS active_customers, "
                "       ROUND(SUM(clicked_flag IN ('Y','1')) * 100.0 / COUNT(*), 1) AS avg_ctr, "
                "       ROUND(SUM(purchased_flag IN ('Y','1')) * 100.0 / COUNT(*), 1) AS avg_cvr, "
                "       COUNT(*) AS total_rec "
                "FROM customer_recommend_history"
            )
            row = cur.fetchone() or {}
        if not row or not row.get('total_rec'):
            return {'source': 'Aurora · customer_recommend_history', 'rows': []}
        return {
            'source': 'Aurora · customer_recommend_history (전체)',
            'rows': [
                {'label': '활성 고객', 'value': f"{int(row['active_customers'] or 0):,}명", 'sub': '추천 기록 보유'},
                {'label': '평균 CTR', 'value': f"{float(row['avg_ctr'] or 0):.1f}%", 'sub': '추천 클릭률'},
                {'label': '평균 CVR', 'value': f"{float(row['avg_cvr'] or 0):.1f}%", 'sub': '구매 전환율'},
                {'label': '총 추천', 'value': f"{int(row['total_rec'] or 0):,}건", 'sub': '7일 누적'},
            ],
        }
    except Exception:
        return {'source': '-', 'rows': []}


# ── Auth ──────────────────────────────────────────────
def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/health')
def health():
    return {'status': 'ok'}


@app.route('/debug/env')
def debug_env():
    import pymysql
    result = {
        'AURORA_HOST': os.environ.get('AURORA_HOST', 'NOT SET'),
        'DB_NAME': os.environ.get('DB_NAME', 'NOT SET'),
        'DB_USER': os.environ.get('DB_USER', 'NOT SET'),
    }
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS rec_count FROM customer_recommend_history WHERE recommended_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)")
            result['db_test'] = cur.fetchone()
    except Exception as e:
        result['db_error'] = str(e)
    return jsonify(result)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if (request.form.get('username') == ADMIN_USER and
                request.form.get('password') == ADMIN_PASS):
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        error = '아이디 또는 비밀번호가 올바르지 않습니다.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))


# 기존 /overview URL은 /dashboard 로 영구 이동
@app.route('/overview')
@login_required
def overview():
    return redirect(url_for('dashboard'))


# ── Executive Dashboard — 화이트 샘플 (8 KPI + Cloud3 + S3-5 + 업로드) ───
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html',
        active='dashboard',
        kpi=[dict(c, value='-') for c in _DASH_KPI_CARDS],
        cloud3=[dict(c, state='-', sub='-') for c in _DASH_CLOUD3_CARDS],
        s3_cards=[dict(c, value='-', note='-') for c in _DASH_S3_5_CARDS],
        uploads=[],
    )


# ── Customer 360 — 화이트 샘플 (검색 + 단일 프로필 + 좌3/우4 박스) ───
@app.route('/users')
@login_required
def users():
    q = request.args.get('q', '').strip()

    # q 없으면 빈 검색창만 표시
    if not q:
        return render_template('users.html', active='customer', q='',
                               profile=None, consent_gate=None)

    # 이름 검색: G로 시작하지 않고 2자 이상이면 onprem 이름 검색
    if not q.startswith('G'):
        r = _call_onprem('search_by_name', q=q)
        hits = (r or {}).get('results', [])
        if len(hits) == 1:
            from flask import redirect as _redir
            return _redir(f'/users?q={hits[0]["global_id"]}')
        return render_template('users.html', active='customer', q=q,
                               name_search_results=hits,
                               profile=None, consent_gate=None)

    # consent gate 먼저 확인 후 profile/pii 조회
    domain_label = {'BANK':'은행','CARD':'카드','INS':'보험','HLT':'헬스케어',
                    'HOS':'병원','WBL':'웨어러블','SEC':'증권','ONINS':'온라인보험'}
    _empty_profile = {
        'global_id': q, 'name_masked': '-', 'phone_masked': '-',
        'grade': '-', 'gender': '-', 'age_band': '-', 'region': '-',
        'income': '-', 'asset': '-',
        'ai_total_score': '-', 'ai_health_score': '-',
    }
    _empty_render = dict(
        active='customer', q=q,
        profile=_empty_profile, status_rows=[],
        consent_badges=[], owned_badges=[],
        topn=[], crosssell=[],
        nba={'action': '-', 'targets': [], 'response_prob': 0, 'updated_at': '-'},
        precision=[], recent_recommend=[], recent_activity=[],
    )

    # ① consent gate
    consent_gate   = 'ok'
    consent_badges = []
    try:
        consent    = (_call_onprem('get_consent', global_id=q) or {})
        ls_user_id = consent.get('ls_user_id') or ''
        if not ls_user_id:
            # get_consent 응답에 ls_user_id 없을 때 get_user_by_global 로 재확인
            user_info  = (_call_onprem('get_user_by_global', global_id=q) or {})
            ls_user_id = user_info.get('ls_user_id') or ''
        if not ls_user_id:
            consent_gate = 'not_registered'
        else:
            active = [c for c in (consent.get('consents') or [])
                      if c.get('consent_flag') == 'Y' or c.get('agreed')]
            if not active:
                consent_gate = 'not_consented'
            else:
                consent_badges = [domain_label.get(c.get('domain'), c.get('domain', c.get('key', '?')))
                                  for c in active]
    except Exception:
        consent_gate = 'not_registered'

    if consent_gate != 'ok':
        return render_template('users.html', consent_gate=consent_gate, **_empty_render)

    # ② profile + pii (gate 통과 후)
    profile     = dict(_empty_profile)
    owned_badges = []
    status_rows  = []
    try:
        onprem = (_call_onprem('get_profile', global_id=q) or {})
        if onprem.get('global_id'):
            profile['global_id'] = onprem['global_id']
            profile['grade']     = onprem.get('vip_grade', '-')
            prof = onprem.get('profile', {}) or {}
            profile['ai_total_score']  = prof.get('lifesync_score', '-')
            profile['ai_health_score'] = prof.get('health_score', '-')
            status_rows = [
                {'label': '그룹사 등록일', 'value': (onprem.get('first_created_dt','-') or '-').split('T')[0], 'sub': '', 'is_state': False},
                {'label': '최근 갱신일',   'value': (onprem.get('last_updated_dt','-') or '-').split('T')[0], 'sub': '', 'is_state': False},
                {'label': '고객 상태',     'value': onprem.get('customer_status', '-'), 'sub': '', 'is_state': True},
                {'label': '고객 유형',     'value': onprem.get('customer_type', '-'), 'sub': '', 'is_state': False},
            ]
            owned_badges = [domain_label.get(i.get('domain'), i.get('domain','?')) for i in onprem.get('identities', [])]
    except Exception:
        pass
    try:
        pii = (_call_onprem('get_pii', global_id=q) or {})
        name = pii.get('name', '') or ''
        if name:
            if len(name) <= 2:
                profile['name_masked'] = name[0] + '*'
            else:
                profile['name_masked'] = name[0] + '*' * (len(name) - 2) + name[-1]
        mobile = pii.get('mobile', '') or ''
        if mobile:
            digits = mobile.replace('-', '')
            if len(digits) >= 10:
                profile['phone_masked'] = f"{digits[:3]}-****-{digits[-4:]}"
    except Exception:
        pass
    try:
        demo_resp = (_call_onprem('get_profile_demo', global_id=q) or {})
        demo_items = demo_resp.get('items', [])
        if demo_items and demo_items[0].get('global_id') == q:
            d = demo_items[0]
            profile['gender']   = d.get('gender', '-') or '-'
            profile['age_band'] = d.get('age_band', '-') or '-'
            profile['region']   = d.get('region', '-') or '-'
            profile['income']   = d.get('income_grade', '-') or '-'
            profile['asset']    = d.get('asset_grade', '-') or '-'
    except Exception:
        pass

    # ③ Redis TOP-N
    topn = []
    try:
        personalized = _stub_redis_personalized(q)
        if personalized and personalized.get('top'):
            pids = [int(p['product_id']) for p in personalized['top']]
            _db = get_db()
            try:
                with _db.cursor() as _cur:
                    _ph = ','.join(['%s'] * len(pids))
                    _cur.execute(f'SELECT product_id, product_name FROM product_master WHERE product_id IN ({_ph})', pids)
                    _pm = {r['product_id']: r['product_name'] for r in _cur.fetchall()}
            finally:
                _db.close()
            for i, p in enumerate(personalized['top']):
                pid = int(p['product_id'])
                topn.append({'rank': i + 1, 'product': _pm.get(pid, f'상품 {pid}')})
    except Exception:
        pass

    # ④ 교차판매 (cross_sell_rule)
    crosssell = []
    try:
        _db = get_db()
        try:
            with _db.cursor() as _cur:
                _cs_grade = (profile.get('grade') or '').strip()
                if _cs_grade and _cs_grade != '-':
                    _cs_grade_sql = 'AND p.target_grade = %s '
                    _cs_params = (_cs_grade, q)
                else:
                    _cs_grade_sql = ''
                    _cs_params = (q,)
                _cur.execute(
                    'SELECT r.target_category, '
                    '(SELECT p.product_name FROM product_master p '
                    ' JOIN category_master c2 ON p.category_id = c2.category_id '
                    ' WHERE c2.category_code = r.target_category AND p.active_flag = "Y" '
                    + _cs_grade_sql +
                    ' ORDER BY p.priority_rank ASC LIMIT 1) AS product_name, '
                    '(SELECT c3.category_name FROM category_master c3 WHERE c3.category_code = r.target_category LIMIT 1) AS category_name '
                    'FROM cross_sell_rule r WHERE r.active_flag = "Y" '
                    '  AND r.base_category IN ('
                    '    SELECT cat.category_code FROM customer_recommend_history h '
                    '    JOIN product_master p ON h.product_id = p.product_id '
                    '    JOIN category_master cat ON p.category_id = cat.category_id '
                    '    WHERE h.global_id = %s AND h.purchased_flag IN (\'Y\', \'1\')'
                    '  ) '
                    'ORDER BY r.priority_rank ASC LIMIT 3',
                    _cs_params
                )
                for row in _cur.fetchall():
                    if row['product_name']:
                        crosssell.append({'product': row['product_name'], 'category': row['target_category'],
                                          'reason': f'{row["category_name"] or row["target_category"]} 교차 추천 룰'})
        finally:
            _db.close()
    except Exception:
        pass

    # ⑤ DynamoDB 점수·등급
    _scores = None
    try:
        from boto3.dynamodb.conditions import Key as _Key2
        _items = get_dynamo_table().query(
            KeyConditionExpression=_Key2('global_id').eq(q),
            ScanIndexForward=False, Limit=1
        ).get('Items', [])
        _scores = _items[0] if _items else None
    except Exception:
        pass

    _grade = (_scores or {}).get('dynamic_grade', 'BASIC')
    _dyn_score = float((_scores or {}).get('dynamic_score', 50))
    _vip_prob = float((_scores or {}).get('vip_prob', 0))
    _rec_prob = float((_scores or {}).get('rec_prob', 0))
    _signup_prob = float((_scores or {}).get('signup_prob', 0))
    _nba_action_map = {
        'VIP':    'VIP 전용 프리미엄 자산관리 서비스 가입 권유',
        'GOLD':   '우수 고객 혜택 패키지 안내',
        'SILVER': '중장기 재테크 상품 추천',
        'BASIC':  '기본 저축 상품 및 혜택 안내',
        'CARE':   '고객 니즈 파악 상담 진행',
    }
    nba = {
        'action': _nba_action_map.get(_grade, '-'),
        'targets': [
            {'label': 'VIP 전환 확률', 'state': f'{_vip_prob:.1%}'},
            {'label': '추천 반응 확률', 'state': f'{_rec_prob:.0%}'},
            {'label': '가입 확률', 'state': f'{_signup_prob:.0%}'},
        ] if _scores else [],
        'response_prob': min(int(_rec_prob * 100), 99),
        'updated_at': str((_scores or {}).get('update_time', '-'))[:16],
    }
    precision = []
    if _scores:
        precision = [
            {'label': 'AI 점수', 'value': f"{_dyn_score:.0f}", 'color': '#6366f1'},
            {'label': 'AI 등급', 'value': _grade, 'color': '#f59e0b'},
            {'label': 'VIP 전환 가능성', 'value': f'{_vip_prob:.1%}', 'color': '#14b8a6'},
        ]
        profile['grade']          = _grade
        profile['ai_total_score'] = f"{_dyn_score:.1f}"
        _hs = (_scores or {}).get('health_score')
        if _hs is not None:
            profile['ai_health_score'] = f"{float(_hs):.1f}"

    # ⑥ 최근 추천 활동 (Aurora customer_recommend_history)
    recent_recommend = []
    try:
        _db = get_db()
        try:
            with _db.cursor() as _cur:
                _cur.execute(
                    'SELECT p.product_name, h.recommended_at, h.clicked_flag, h.purchased_flag '
                    'FROM customer_recommend_history h '
                    'JOIN product_master p ON h.product_id = p.product_id '
                    'WHERE h.global_id = %s ORDER BY h.recommended_at DESC LIMIT 5',
                    (q,)
                )
                for row in _cur.fetchall():
                    if row['purchased_flag'] == 'Y':
                        state, bg, color = '구매', '#dcfce7', '#16a34a'
                    elif row['clicked_flag'] == 'Y':
                        state, bg, color = '클릭', '#dbeafe', '#1d4ed8'
                    else:
                        state, bg, color = '노출', '#f1f5f9', '#64748b'
                    recent_recommend.append({
                        'time': _kst(row['recommended_at']),
                        'product': row['product_name'],
                        'state': state, 'badge_bg': bg, 'badge_color': color,
                    })
        finally:
            _db.close()
    except Exception:
        pass

    # ⑦ 최근 행동 로그 (Aurora customer_dashboard_log)
    recent_activity = []
    try:
        _db = get_db()
        try:
            with _db.cursor() as _cur:
                _cur.execute(
                    'SELECT l.view_time, l.page_type, l.banner_click, l.product_click, p.product_name '
                    'FROM customer_dashboard_log l '
                    'LEFT JOIN product_master p ON l.click_product_id = p.product_id '
                    'WHERE l.global_id = %s ORDER BY l.view_time DESC LIMIT 5',
                    (q,)
                )
                for row in _cur.fetchall():
                    if row['product_click'] == 'Y' and row['product_name']:
                        event = f"{row['product_name']} 클릭"
                        badge, bg, color = '상품클릭', '#dbeafe', '#1d4ed8'
                    elif row['banner_click'] == 'Y':
                        event = f"배너 클릭 ({row['page_type']})"
                        badge, bg, color = '배너클릭', '#fef9c3', '#ca8a04'
                    else:
                        event = f"{row['page_type']} 페이지 방문"
                        badge, bg, color = '방문', '#f1f5f9', '#64748b'
                    recent_activity.append({
                        'time': _kst(row['view_time']),
                        'event': event,
                        'badge': badge, 'badge_bg': bg, 'badge_color': color,
                    })
        finally:
            _db.close()
    except Exception:
        pass

    return render_template('users.html',
        active='customer', q=q,
        consent_gate='ok',
        profile=profile, status_rows=status_rows,
        consent_badges=consent_badges, owned_badges=owned_badges,
        topn=topn, crosssell=crosssell,
        nba=nba, precision=precision,
        recent_recommend=recent_recommend, recent_activity=recent_activity,
    )


# ── User Detail ───────────────────────────────────────
@app.route('/users/<global_id>')
@login_required
def user_detail(global_id):
    # ① DynamoDB — 등급·점수 (SK=update_time 있으므로 query 사용)
    try:
        from boto3.dynamodb.conditions import Key as _Key
        items = get_dynamo_table().query(
            KeyConditionExpression=_Key('global_id').eq(global_id),
            ScanIndexForward=False, Limit=1
        ).get('Items', [])
        scores = items[0] if items else None
    except Exception:
        scores = None

    # ② S3 동의 스냅샷 (consent_snapshot_aggregator 가 매일 KST 03:00 적재)
    consents = _load_consent_from_s3(global_id).get('consents', [])

    # ③ Aurora — 추천 이력
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                'SELECT p.product_name, r.recommended_at, r.clicked_flag, r.purchased_flag '
                'FROM customer_recommend_history r '
                'JOIN product_master p ON r.product_id = p.product_id '
                'WHERE r.global_id = %s ORDER BY r.recommended_at DESC',
                (global_id,)
            )
            recommend_history = cur.fetchall()
    finally:
        db.close()

    # ④ 온프레 Lambda — 계열사 매핑 (customer_identity_map)
    identities = (_call_onprem('get_identity_map', global_id=global_id) or {}).get('identities', [])

    # 기본 유저 정보: Aurora users_ref 동기화 전까지 available 필드만 표시
    user = {
        'global_id':  global_id,
        'ls_user_id': '-',
        'name':       '-',
        'email':      '-',
        'grade':      scores.get('dynamic_grade', '-') if scores else '-',
    }

    # Redis Personalized Top 3 (ElastiCache 가동 후 활성)
    personalized = _stub_redis_personalized(global_id) or {}

    return render_template('user_detail.html',
        active='customer',
        user=user,
        scores=scores,
        consents=consents,
        recommend_history=recommend_history,
        identities=identities,
        personalized=personalized,
    )


# ── AI 추천 ───────────────────────────────────────────
@app.route('/ai')
@login_required
def ai():
    """ai 페이지 SSR — 실 호출 안 되는 영역은 빈 list 로.

    SSR 진입 시 Aurora SQL / DDB scan 직접 호출 X (5초+ 지연 원인 — ops 와 동일 패턴).
    실 데이터는 JS 폴링 (kpi4 + 차트 4) 가 /api/ai/* 로 fetch.
    """
    # Aurora 조회 (단일 쿼리 × 3, 지연 < 1s)
    # age_perf 는 On-Prem Lambda 호출이라 빈 list 유지 (5초+ 지연 방지)
    return render_template('ai.html',
        active='ai',
        kpi4=_ai_kpi4_from_aws(),
        trend_7d=_aurora_recommend_trend_7day(),
        top10=_aurora_recommend_top10(),
        cat_donut=_aurora_category_ctr_donut(),
        age_perf=[],
        grade_dist=_ddb_grade_dist(),
        feature_dist=_ddb_feature_importance(),
        rec_data=_aurora_action_code_rec_data(),
        insight=_aurora_customer_insight(),
        ddb_hist=_ddb_score_histogram_for_ai(),
        pr_models=_aurora_pr_models(),
    )


# ── 신규 admin JSON API — analytics batch 결과 read ─────────────
@app.route('/api/admin/recommend-trend')
@login_required
def api_admin_recommend_trend():
    """P3 r10. Aurora customer_recommend_history 최근 7일 GROUP BY DATE."""
    rows = _aurora_recommend_trend_7day()
    return jsonify(rows)


@app.route('/api/admin/segment-performance')
@login_required
def api_admin_segment_performance():
    """P3 r12. analytics_segment_daily 오늘자 — dim prefix 필터 가능 (?dim=gender)."""
    dim = request.args.get('dim')  # gender / age_band / region / income / asset
    prefix = f'{dim}#' if dim else None
    rows = _ddb_query_today(DDB_SEGMENT_TABLE, sk_prefix=prefix)
    return jsonify(rows)


@app.route('/api/admin/demographic-summary')
@login_required
def api_admin_demographic_summary():
    """P3 r13. analytics_demographic_daily 오늘자 — dim prefix 필터 가능."""
    dim = request.args.get('dim')
    prefix = f'{dim}#' if dim else None
    rows = _ddb_query_today(DDB_DEMOGRAPHIC_TABLE, sk_prefix=prefix, sk_attr='demographic_key')
    return jsonify(rows)


@app.route('/api/local/status')                  # 설계서 V3 P4 r60 정합
@app.route('/api/admin/local-lab-status')        # admin 내부 alias
@login_required
def api_admin_local_lab_status():
    """P4 r38~43, r60. 온프레 환경/서비스 종합 헬스 — Lambda onprem-query 'local_lab_status' 경유."""
    data = _call_onprem('local_lab_status')
    return jsonify(data or {'status': 'fail', 'environments': [], 'checks': {}, 'output': 'onprem lambda unavailable'})


# ── 시트 정의 helper (설계서 V3 Backend 구현 명세 정합) ─────────────────────────

def _stub_aurora_summary():
    """P1 r29 — KPI 9 카드 list (시연↔운영 동일 구조).

    응답 스키마: _DASH_KPI_CARDS 와 동일 9-element list — 각 요소 `{label, value, sub, accent, is_status}`.
    실 호출 결과로 value 만 덮어씀. 실패한 카드는 '-' 표시.
    """
    _rc = _get_redis()
    if _rc:
        try:
            _cached = _rc.get('cache:dash_summary')
            if _cached:
                return json.loads(_cached)
        except Exception:
            pass

    cards = [dict(c, value='-') for c in _DASH_KPI_CARDS]

    # KPI 1~3: On-Prem Lambda (VPN 연결 필요) — TTL 캐시 + 병렬 호출
    import concurrent.futures as _cf

    _now_op = time.time()
    if (_onprem_counts_cache['value'] is not None
            and _now_op - _onprem_counts_cache['ts'] < _ONPREM_COUNTS_TTL):
        for idx, c in enumerate(_onprem_counts_cache['value']):
            if c is not None:
                cards[idx]['value'] = f'{c:,}'
    else:
        def _fetch_onprem_count(action, tout):
            try:
                c = (_call_onprem(action, timeout=tout) or {}).get('count')
                return int(c) if c is not None else None
            except Exception:
                return None

        with _cf.ThreadPoolExecutor(max_workers=3) as _ex:
            _f0 = _ex.submit(_fetch_onprem_count, 'count_master_customer', 8)
            _f1 = _ex.submit(_fetch_onprem_count, 'count_users', 8)
            _f2 = _ex.submit(_fetch_onprem_count, 'count_users_consented', 20)
            _counts = [_f0.result(), _f1.result(), _f2.result()]
        _onprem_counts_cache['value'] = _counts
        _onprem_counts_cache['ts']    = time.time()
        for idx, c in enumerate(_counts):
            if c is not None:
                cards[idx]['value'] = f'{c:,}'

    # KPI 4: AI 추천 상태 — DDB 최신 update_time
    try:
        items = get_dynamo_table().scan(ProjectionExpression='update_time', Limit=1).get('Items', [])
        if items and items[0].get('update_time'):
            cards[3]['value'] = 'Vertex AI'
            cards[3]['sub'] = f"DynamoDB · 최근 갱신 {items[0]['update_time']}"
    except Exception:
        pass

    # KPI 5~8: Aurora 추천 통계 — TTL 캐시
    _now_au = time.time()
    if (_aurora_dash_cache['value'] is not None
            and _now_au - _aurora_dash_cache['ts'] < _AURORA_DASH_TTL):
        _ac = _aurora_dash_cache['value']
        if _ac.get('tot'):
            cards[4]['value'] = f"{_ac['tot']:,}"
            cards[6]['value'] = f"{_ac['ctr']:.1f}%"
            cards[7]['value'] = f"{_ac['cvr']:.1f}%"
        if _ac.get('log_cnt') is not None:
            n = _ac['log_cnt']
            cards[5]['value'] = f"{n/1e6:.1f}M" if n >= 1_000_000 else f"{n:,}"
    else:
        _ac = {}
        try:
            with get_db() as db, db.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS total, "
                    "SUM(clicked_flag IN ('Y','1')) AS clicked, "
                    "SUM(purchased_flag IN ('Y','1')) AS purchased "
                    "FROM customer_recommend_history"
                )
                r = cur.fetchone()
                if r and r['total']:
                    tot = int(r['total'])
                    clk = float(r['clicked'] or 0)
                    pur = float(r['purchased'] or 0)
                    _ac['tot'] = tot
                    _ac['ctr'] = clk / tot * 100
                    _ac['cvr'] = pur / tot * 100
                    cards[4]['value'] = f"{tot:,}"
                    cards[6]['value'] = f"{_ac['ctr']:.1f}%"
                    cards[7]['value'] = f"{_ac['cvr']:.1f}%"
        except Exception:
            pass
        try:
            with get_db() as db, db.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM customer_dashboard_log")
                r = cur.fetchone()
                if r:
                    n = int(r['cnt'])
                    _ac['log_cnt'] = n
                    cards[5]['value'] = f"{n/1e6:.1f}M" if n >= 1_000_000 else f"{n:,}"
        except Exception:
            pass
        if _ac:
            _aurora_dash_cache['value'] = _ac
            _aurora_dash_cache['ts']    = time.time()

    # KPI 9: Redis rec:* 키 수 (추천 캐시만 집계) — TTL 캐시로 매 갱신 시 scan 방지
    try:
        rc = _get_redis()
        if rc:
            _now = time.time()
            if (_redis_rec_cache['value'] is not None
                    and _now - _redis_rec_cache['ts'] < _REDIS_REC_TTL):
                _rcnt = _redis_rec_cache['value']
            else:
                _rcnt = sum(1 for _ in rc.scan_iter('rec:*'))
                _redis_rec_cache['value'] = _rcnt
                _redis_rec_cache['ts']    = _now
            cards[8]['value'] = f'{_rcnt:,}'
    except Exception:
        pass

    if _rc:
        try:
            _rc.setex('cache:dash_summary', _DASH_SUMMARY_TTL, json.dumps(cards))
        except Exception:
            pass
    return cards


def _stub_aurora_history(global_id, limit=50):
    """P2 r47 — Aurora customer_recommend_history WHERE global_id."""
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT p.product_name, r.recommended_at, r.clicked_flag, r.purchased_flag "
                "FROM customer_recommend_history r "
                "JOIN product_master p ON r.product_id = p.product_id "
                "WHERE r.global_id=%s ORDER BY r.recommended_at DESC LIMIT %s",
                (global_id, limit),
            )
            return [{**r, 'recommended_at': str(r['recommended_at'])} for r in cur.fetchall()]
    except Exception:
        return []


def _stub_aurora_activity(global_id, limit=50):
    """P2 r48 — Aurora customer_dashboard_log WHERE global_id."""
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT view_time, page_type, banner_click, product_click, click_product_id, session_id "
                "FROM customer_dashboard_log WHERE global_id=%s "
                "ORDER BY view_time DESC LIMIT %s",
                (global_id, limit),
            )
            return [{**r, 'view_time': str(r['view_time'])} for r in cur.fetchall()]
    except Exception:
        return []


def _stub_recommend_stats():
    """P3 r27 — CTR/CVR/상품 TOP10/7일 추이/세그먼트별 성과 종합."""
    return {
        'kpi'              : _aurora_ai_kpi(),
        'trend_7day'       : _aurora_recommend_trend_7day(),
        'segment_today'    : _ddb_query_today(DDB_SEGMENT_TABLE),
        'prob_distribution': _ddb_prob_distribution(),
    }


def _stub_ai_summary():
    """P3 r29 — AI 출력 분포 + 모델 평가 (Precision/Recall/Accuracy)."""
    return {
        'ai_kpi'        : _aurora_ai_kpi(),
        'vertex_metrics': _stub_vertex_metrics() or {},
        'score_dist'    : _ddb_score_distribution(),
    }


# ── 시트 정의 /api/* 라우트 — helper 호출 wrap ─────────────────────────────

@app.route('/api/dashboard/summary')
@login_required
def api_dashboard_summary():
    """P1 r29 — _stub_aurora_summary() JSON wrap."""
    return jsonify(_stub_aurora_summary())


def _s3_status_cards():
    """P1 r30 — S3 적재 7 카드 list (raw/today/iot/processed/curated/size/lastupload).

    응답: _DASH_S3_5_CARDS 와 동일 7-element list — `{icon, label, value, note}`.
    """
    raw = _ping_s3_ingestion() or {}
    last = raw.get('last_upload') or {}
    iot  = raw.get('iot_count', 0)
    size_gb = (raw.get('total_size_bytes', 0) / 1024 / 1024 / 1024) if raw.get('total_size_bytes') else 0

    cards = [dict(c, value='-', note='-') for c in _DASH_S3_5_CARDS]
    if raw.get('raw_bucket_files'):  cards[0]['value'] = f"{raw['raw_bucket_files']:,}"; cards[0]['note'] = 'lifesync-raw'
    if raw.get('today_ingested'):    cards[1]['value'] = f"{raw['today_ingested']:,}";   cards[1]['note'] = 'dt=오늘'
    if iot:                          cards[2]['value'] = f"{iot:,}";                     cards[2]['note'] = 'Kinesis · wearable'
    if raw.get('processed_count'):   cards[3]['value'] = f"{raw['processed_count']:,}";  cards[3]['note'] = 'lifesync-processed'
    if raw.get('curated_count'):     cards[4]['value'] = f"{raw['curated_count']:,}";    cards[4]['note'] = 'lifesync-curated'
    if size_gb:                      cards[5]['value'] = f"{size_gb:.1f} GB";            cards[5]['note'] = 'raw 전체 합산'
    if last.get('time'):
        cards[6]['value'] = last['time']
        cards[6]['note']  = last.get('file', '-')
    return cards


@app.route('/api/s3/status')
@login_required
def api_s3_status():
    """P1 r30. S3 적재 현황 — 5 카드 list 응답 (시연↔운영 통일)."""
    return jsonify(_s3_status_cards())


@app.route('/api/cloud/status')
@login_required
def api_cloud_status():
    """P1 r31. AWS/GCP 헬스 종합."""
    return jsonify({'aws': _ping_cloud_status(), 'gcp': _stub_gcp_status()})


def _cloud3_from_aws():
    """AWS / GCP / On-Prem 3 카드 + 서비스별 details. 안 들어오는 데이터는 '-' 로 비워둠."""
    aws_list = _ping_cloud_status() or []
    cards = [dict(c, state='-', sub='-', details=[]) for c in _DASH_CLOUD3_CARDS]

    if aws_list:
        up = sum(1 for x in aws_list if x.get('state') == 'UP')
        cards[0]['state'] = f'{up} / {len(aws_list)} 정상'
        cards[0]['sub']   = ' · '.join(x['service'].replace('AWS ', '') for x in aws_list[:6])
        cards[0]['details'] = [
            {'name': x.get('service', '?').replace('AWS ', ''),
             'state': x.get('state', '?'),
             'note':  x.get('note', '-')}
            for x in aws_list
        ]

    # GCP — _stub_gcp_status() 는 list 반환
    gcp_list = _stub_gcp_status() or []
    if gcp_list:
        up   = sum(1 for g in gcp_list if g.get('state') == 'UP')
        unk  = sum(1 for g in gcp_list if g.get('state') == 'UNKNOWN')
        if unk == len(gcp_list):
            cards[1]['state'] = 'UNKNOWN'
        elif up == len(gcp_list):
            cards[1]['state'] = f'{up} / {len(gcp_list)} 정상'
        else:
            cards[1]['state'] = f'{up} / {len(gcp_list)} 정상'
        cards[1]['sub']     = ' · '.join(g['service'] for g in gcp_list[:3])
        cards[1]['details'] = [
            {'name': g['service'], 'state': g['state'],
             'note': g.get('error', '') or f"series={g.get('series_count', '-')}"}
            for g in gcp_list
        ]

    # On-Prem — VM 단위 묶음: vm:ls-* + 그 위 service 합산 (DOWN 하나라도 있으면 DOWN)
    try:
        lab    = _call_onprem('local_lab_status') or {}
        checks = lab.get('checks', {}) or {}
        envs   = lab.get('environments', []) or []
        vm_specs = [
            ('ls-db',    'MySQL',        'vm:ls-db',    'service:mysql'),
            ('ls-token', 'Tokenization', 'vm:ls-token', 'service:tokenization'),
            ('ls-api',   'PrivateAPI',   'vm:ls-api',   None),
        ]
        rows = []
        for vm_id, svc_name, vm_key, svc_key in vm_specs:
            vm  = (checks.get(vm_key)  or [{}])[0] if checks.get(vm_key)  else {}
            svc = (checks.get(svc_key) or [{}])[0] if svc_key and checks.get(svc_key) else {}
            statuses = [s for s in (vm.get('status'), svc.get('status')) if s]
            if any(s == 'fail' for s in statuses):
                state = 'DOWN'
            elif any(s == 'warn' for s in statuses):
                state = 'WARN'
            elif statuses:
                state = 'UP'
            else:
                state = 'WARN'
            ip      = (vm.get('observedValue', '') or '').split(':')[0] or '-'
            note_sv = svc.get('observedValue', '') or ''
            # svc observedValue 가 http URL / ip:port (중복) 면 ip 만, 그 외 (예: '11 tables') 는 ip · note
            if note_sv and not note_sv.startswith('http') and not note_sv.startswith(ip):
                note = f'{ip} · {note_sv}'
            else:
                note = ip
            rows.append({
                'name':  f'{vm_id} ({svc_name})',
                'state': state,
                'note':  note,
            })
        if rows:
            up = sum(1 for r in rows if r['state'] == 'UP')
            cards[2]['state']   = f'{up} / {len(rows)} 정상'
            cards[2]['sub']     = ' · '.join(e.get('env', '?').split('·')[-1].strip() for e in envs[:3]) or '-'
            cards[2]['details'] = rows
    except Exception:
        pass
    return cards


@app.route('/api/dashboard/cloud3')
@login_required
def api_dashboard_cloud3():
    """dashboard.html 3카드 (AWS / GCP / On-Prem) — list of 3.

    `_ping_cloud_status` 결과를 AWS 카드 1개로 집계.
    """
    return jsonify(_cloud3_from_aws())


_BADGE_MAP = {
    'bank':       {'badge': 'BANK', 'badge_bg': '#dbeafe', 'badge_color': '#2563eb'},
    'card':       {'badge': 'CARD', 'badge_bg': '#fef3c7', 'badge_color': '#d97706'},
    'insurance':  {'badge': 'INS',  'badge_bg': '#fef9c3', 'badge_color': '#a16207'},
    'securities': {'badge': 'SEC',  'badge_bg': '#ede9fe', 'badge_color': '#7c3aed'},
    'healthcare': {'badge': 'HLT',  'badge_bg': '#dcfce7', 'badge_color': '#16a34a'},
    'hospital':   {'badge': 'HOS',  'badge_bg': '#fce7f3', 'badge_color': '#be185d'},
    'wearable':   {'badge': 'IOT',  'badge_bg': '#e0e7ff', 'badge_color': '#4338ca'},
    'online_insurance': {'badge': 'ONI', 'badge_bg': '#ccfbf1', 'badge_color': '#0f766e'},
}


def _uploads_from_s3(limit=10):
    """S3 raw bucket 최근 업로드 N건 — 도메인 prefix 별 MaxKeys=50 후 합산 정렬."""
    raw_bucket = os.environ.get('LIFESYNC_RAW_S3_BUCKET', 'lifesync-raw')
    try:
        s3 = _boto('s3')
        objs = []
        for prefix in _RAW_DOMAIN_PREFIXES:
            resp = s3.list_objects_v2(Bucket=raw_bucket, Prefix=prefix, MaxKeys=50)
            objs.extend(resp.get('Contents', []))
        objs.sort(key=lambda o: o['LastModified'], reverse=True)
        out = []
        for o in objs[:limit]:
            key = o['Key']
            prefix = key.split('/')[0].lower() if '/' in key else ''
            badge = _BADGE_MAP.get(prefix, {'badge': prefix.upper()[:4] or '?', 'badge_bg': '#f1f5f9', 'badge_color': '#64748b'})
            size_mb = o['Size'] / 1024 / 1024
            out.append({
                'time': o['LastModified'].strftime('%H:%M:%S'),
                'file': key.split('/')[-1],
                'badge':       badge['badge'],
                'badge_bg':    badge['badge_bg'],
                'badge_color': badge['badge_color'],
                'size': f'{size_mb:.1f} MB' if size_mb >= 0.1 else f'{o["Size"]/1024:.1f} KB',
            })
        return out
    except Exception:
        return []


@app.route('/api/dashboard/uploads')
@login_required
def api_dashboard_uploads():
    """dashboard.html 최근 업로드 파일 표.

    lifesync-raw bucket 의 `list_objects_v2` 결과 최신 10건.
    """
    return jsonify(_uploads_from_s3(limit=10))


def _ai_kpi4_from_aws():
    """ai.html KPI 4 — Lambda CloudWatch metric 활용. Aurora 실패 시 mock fallback."""
    # 안 들어오는 항목은 '-' 로 비워둠
    cards = [dict(c, value='-', sub='-') for c in _AI_KPI4_CARDS]
    try:
        import time as _time
        _now = _time.time()
        if _aurora_ctr_cvr_cache['value'] is not None and _now - _aurora_ctr_cvr_cache['ts'] < _AURORA_CTR_CVR_TTL:
            _cached = _aurora_ctr_cvr_cache['value']
            cards[0]['value'] = _cached['ctr']
            cards[0]['sub']   = _cached['sub0']
            cards[1]['value'] = _cached['cvr']
            cards[1]['sub']   = _cached['sub1']
        else:
            with get_db() as _db, _db.cursor() as _cur:
                _cur.execute(
                    "SELECT CURDATE() AS date, "
                    "  ROUND(SUM(clicked_flag IN ('Y','1')) * 100.0 / COUNT(*), 1) AS ctr, "
                    "  ROUND(SUM(purchased_flag IN ('Y','1')) * 100.0 / COUNT(*), 1) AS cvr "
                    "FROM customer_recommend_history "
                    "WHERE recommended_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
                )
                _row = _cur.fetchone()
                if _row and _row.get('ctr') is not None:
                    _v0 = f"{float(_row['ctr'] or 0):.1f}%"
                    _s0 = f"최근 7일 평균 · customer_recommend_history · {_row['date']}"
                    _v1 = f"{float(_row['cvr'] or 0):.1f}%"
                    _s1 = f"최근 7일 평균 · customer_recommend_history · {_row['date']}"
                    _aurora_ctr_cvr_cache['value'] = {'ctr': _v0, 'sub0': _s0, 'cvr': _v1, 'sub1': _s1}
                    _aurora_ctr_cvr_cache['ts'] = _now
                    cards[0]['value'] = _v0
                    cards[0]['sub']   = _s0
                    cards[1]['value'] = _v1
                    cards[1]['sub']   = _s1
    except Exception:
        pass
    try:
        _ddb_r = boto3.resource('dynamodb', region_name=AWS_REGION)
        _resp  = _ddb_r.Table('lifesync_customer_result').scan(
            ProjectionExpression='update_time', Limit=1,
        )
        _ut = (_resp.get('Items') or [{}])[0].get('update_time', '')
        if _ut:
            cards[2]['value'] = str(_ut)[:16]
            cards[2]['sub']   = 'DynamoDB lifesync_customer_result · 배치 갱신 시각'
    except Exception:
        pass
    try:
        import time as _time
        _now = _time.time()
        if _ddb_ai_target_cache['value'] is not None and _now - _ddb_ai_target_cache['ts'] < _DDB_AI_TARGET_TTL:
            _cnt = _ddb_ai_target_cache['value']
        else:
            _ddb_c = boto3.client('dynamodb', region_name=AWS_REGION)
            _cnt = _ddb_c.describe_table(
                TableName='lifesync_customer_result'
            )['Table']['ItemCount']
            _ddb_ai_target_cache['value'] = _cnt
            _ddb_ai_target_cache['ts']    = _now
        cards[3]['value'] = f'{_cnt:,}'
        cards[3]['sub']   = 'DynamoDB lifesync_customer_result · AI 분석 완료 고객'
    except Exception:
        pass
    return cards


@app.route('/api/ai/kpi4')
@login_required
def api_ai_kpi4():
    """ai.html 상단 4 KPI.

    Lambda CloudWatch metric 일부 활용 (recommendation / ingest 1h invocations).
    """
    return jsonify(_ai_kpi4_from_aws())


# ── ai 차트 HTML fragment — Jinja2 partial 재사용 (server-rendered SVG) ───
@app.route('/api/ai/chart/trend')
@login_required
def api_ai_chart_trend():
    """7일 추이 SVG fragment. Aurora 실패하면 빈 차트."""
    try:    trend = _aurora_recommend_trend_7day() or []
    except: trend = []
    return render_template('_chart_ai_trend.j2', trend_7d=trend)


def _aurora_category_ctr_donut():
    """카테고리별 추천/클릭/CTR — recent 7d. V6 R19."""
    _colors = ['#6366f1', '#22d3ee', '#f59e0b', '#10b981', '#e11d48', '#8b5cf6', '#f97316', '#14b8a6']
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT cat.category_code AS label, "
                "       COUNT(*) AS recommended, "
                "       SUM(r.clicked_flag IN ('Y','1')) AS clicked, "
                "       ROUND(SUM(r.clicked_flag IN ('Y','1')) * 100.0 / COUNT(*), 1) AS ctr "
                "FROM customer_recommend_history r "
                "JOIN product_master p    ON r.product_id  = p.product_id "
                "JOIN category_master cat ON p.category_id = cat.category_id "
                "WHERE r.recommended_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) "
                "GROUP BY cat.category_code "
                "ORDER BY recommended DESC "
                "LIMIT 10"
            )
            rows = cur.fetchall()
        total = sum(int(r['recommended'] or 0) for r in rows)
        return [
            {
                'name': r['label'],
                'pct': round(int(r['recommended'] or 0) * 100.0 / total, 1) if total > 0 else 0,
                'ctr': float(r['ctr'] or 0),
                'recommended': int(r['recommended'] or 0),
                'clicked':     int(r['clicked'] or 0),
                'color': _colors[i % len(_colors)],
            }
            for i, r in enumerate(rows)
        ]
    except Exception:
        return []


@app.route('/api/ai/chart/donut')
@login_required
def api_ai_chart_donut():
    """카테고리별 도넛 SVG fragment."""
    cat = _aurora_category_ctr_donut()
    return render_template('_chart_ai_donut.j2', cat_donut=cat)


def _ai_age_perf_2step():
    """연령대별 추천 성과 — Lambda list_by_age_band 액션 우선, DDB fallback. V6 R21."""
    import json as _json
    try:
        if not ONPREM_QUERY_LAMBDA:
            raise ValueError("ONPREM_QUERY_LAMBDA not set")
        resp   = _get_lambda().invoke(
            FunctionName=ONPREM_QUERY_LAMBDA,
            InvocationType='RequestResponse',
            Payload=_json.dumps({'action': 'list_by_age_band'}),
        )
        result = _json.loads(resp['Payload'].read())
        if result.get('statusCode') != 200:
            raise ValueError(f"Lambda error: {result.get('statusCode')}")
        body       = result.get('body', '{}')
        data       = _json.loads(body) if isinstance(body, str) else body
        age_groups = data.get('age_groups', {})
        if not age_groups:
            raise ValueError("no age_groups from Lambda")
        out = []
        with get_db() as db, db.cursor() as cur:
            for age_band in ['20s', '30s', '40s', '50s', '60s+']:
                gids = age_groups.get(age_band, [])
                if not gids:
                    out.append({'age_band': age_band, 'recommended': 0,
                                'clicked': 0, 'purchased': 0, 'ctr': 0, 'cvr': 0})
                    continue
                placeholders = ','.join(['%s'] * len(gids))
                cur.execute(
                    f"SELECT COUNT(*) AS recommended, "
                    f"       SUM(clicked_flag IN ('Y','1')) AS clicked, "
                    f"       SUM(purchased_flag IN ('Y','1')) AS purchased "
                    f"FROM customer_recommend_history "
                    f"WHERE global_id IN ({placeholders}) "
                    f"  AND recommended_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)",
                    tuple(gids)
                )
                row = cur.fetchone() or {}
                rec = int(row.get('recommended') or 0)
                clk = int(row.get('clicked') or 0)
                pur = int(row.get('purchased') or 0)
                out.append({
                    'age_band': age_band, 'recommended': rec, 'clicked': clk, 'purchased': pur,
                    'ctr': round(clk * 100.0 / rec, 1) if rec else 0,
                    'cvr': round(pur * 100.0 / rec, 1) if rec else 0,
                })
        return out
    except Exception:
        pass
    # On-Prem 미연결 → DDB analytics_segment_performance age_band 데이터로 대체
    try:
        rows = _ddb_query_today(DDB_SEGMENT_TABLE, sk_prefix='age_band#')
        if not rows:
            return []
        order = ['20s', '30s', '40s', '50s', '60s+']
        out = []
        for row in sorted(rows, key=lambda r: order.index(r.get('value', '20s')) if r.get('value') in order else 99):
            out.append({
                'age_band':    str(row.get('value', '-')),
                'recommended': int(row.get('recommended') or 0),
                'clicked':     int(row.get('clicked') or 0),
                'purchased':   int(row.get('purchased') or 0),
                'ctr':         float(row.get('ctr') or 0),
                'cvr':         float(row.get('cvr') or 0),
            })
        return out
    except Exception:
        return []


def _ddb_feature_importance():
    """DDB vip_prob/rec_prob/signup_prob 평균 → feature importance 프록시."""
    try:
        items = get_dynamo_table().scan(
            ProjectionExpression='vip_prob, rec_prob, signup_prob'
        ).get('Items', [])
        if not items:
            return []
        fields = [
            ('vip_prob',    'VIP 전환 확률'),
            ('rec_prob',    '추천 반응 확률'),
            ('signup_prob', '가입 전환 확률'),
        ]
        results = []
        for key, label in fields:
            vals = [float(i[key]) for i in items if i.get(key) is not None]
            if vals:
                results.append({'name': label, 'pct': round(sum(vals) / len(vals), 3)})
        return sorted(results, key=lambda x: -x['pct'])
    except Exception:
        return []


@app.route('/api/ai/chart/age')
@login_required
def api_ai_chart_age():
    """연령대별 추천 성과 진행바."""
    raw = _ai_age_perf_2step()
    age = [{
        'age':         r.get('age_band', '-'),
        'recommended': int(r.get('recommended') or 0),
        'clicked':     int(r.get('clicked') or 0),
        'purchased':   int(r.get('purchased') or 0),
        'ctr':         r.get('ctr', 0),
        'cvr':         r.get('cvr', 0),
    } for r in raw]
    return render_template('_chart_ai_age.j2', age_perf=age)


@app.route('/api/ai/chart/histogram')
@login_required
def api_ai_chart_histogram():
    """AI 예측 출현 분포 히스토그램. DDB scan 결과 — 빈 응답이면 빈 차트."""
    try:
        items = get_dynamo_table().scan(ProjectionExpression='dynamic_score').get('Items', [])
        buckets = [('0-20', '#ef4444'), ('20-40', '#f59e0b'), ('40-60', '#facc15'),
                   ('60-80', '#3b82f6'), ('80-100', '#16a34a')]
        counts = [0, 0, 0, 0, 0]
        for it in items:
            v = float(it.get('dynamic_score') or 0)
            idx = 4 if v >= 80 else 3 if v >= 60 else 2 if v >= 40 else 1 if v >= 20 else 0
            counts[idx] += 1
        hist = [{'bucket': b, 'count': c, 'color': col} for (b, col), c in zip(buckets, counts) if c]
    except Exception:
        hist = []
    return render_template('_chart_ai_histogram.j2', ddb_hist=hist)


@app.route('/api/ops/wearable')
@login_required
def api_ops_wearable():
    """ops.html Wearable 실시간 — KPI 5 + RED/YELLOW/DEVICE 표.

    응답 스키마: `{kpi:[...5], red:[...], yellow:[...], device:[...]}`.
    SSE 비대응 클라이언트 폴백용 (실시간은 `/stream/wearable` 사용).
    """
    return jsonify(wearable_engine.snapshot())


@app.route('/stream/wearable')
@login_required
def stream_wearable():
    """Wearable 실시간 SSE — 3초마다 snapshot push.

    클라이언트: `new EventSource('/stream/wearable')`.
    운영: ALB / Nginx 의 proxy_buffering off 필요 (text/event-stream).
    """
    @stream_with_context
    def gen():
        while True:
            yield f"data: {json.dumps(wearable_engine.snapshot(), ensure_ascii=False)}\n\n"
            time.sleep(1)
    return Response(gen(), mimetype='text/event-stream', headers={
        'Cache-Control':     'no-cache',
        'X-Accel-Buffering': 'no',   # Nginx 버퍼링 비활성
    })



@app.route('/api/customer/profile/<global_id>')
@login_required
def api_customer_profile(global_id):
    """P2 r44. customer_pii_secure + customer_360_profile + master_customer + users + consent JOIN.

    응답 스키마: {global_id, customer: {...}, consents: [...]} — 시연↔운영 동일.
    운영: customer 는 PrivateAPI `get_profile` (master + identity + 360_profile), consents 는 S3 스냅샷.
    """
    customer = _call_onprem('get_profile', global_id=global_id) or {}
    consents = _load_consent_from_s3(global_id).get('consents', [])
    return jsonify({
        'global_id': global_id,
        'customer':  customer,
        'consents':  consents,
    })


@app.route('/api/customer/ai-result/<global_id>')
@login_required
def api_customer_ai_result(global_id):
    """P2 r45. DDB lifesync_customer_result — composite key (global_id HASH + update_time RANGE).

    Cloud Run 일배치 PutItem 으로 시계열 누적되므로 query + ScanIndexForward=False + Limit=1
    로 최신 1건 반환.
    """
    try:
        from boto3.dynamodb.conditions import Key
        resp = get_dynamo_table().query(
            KeyConditionExpression=Key('global_id').eq(global_id),
            ScanIndexForward=False,
            Limit=1,
        )
        items = resp.get('Items', [])
        return jsonify(items[0] if items else {})
    except Exception:
        return jsonify({})


@app.route('/api/customer/recommend/<global_id>')
@login_required
def api_customer_recommend(global_id):
    """P2 r46. Redis ZREVRANGE rec:{global_id} 0 N WITHSCORES."""
    data = _stub_redis_personalized(global_id)
    return jsonify(data or {})


@app.route('/api/customer/history/<global_id>')
@login_required
def api_customer_history(global_id):
    """P2 r47 — _stub_aurora_history() JSON wrap."""
    return jsonify(_stub_aurora_history(global_id))


@app.route('/api/customer/activity/<global_id>')
@login_required
def api_customer_activity(global_id):
    """P2 r48 — _stub_aurora_activity() JSON wrap."""
    return jsonify(_stub_aurora_activity(global_id))


@app.route('/api/ai/summary')
@login_required
def api_ai_summary():
    """P3 r29 — _stub_ai_summary() JSON wrap."""
    return jsonify(_stub_ai_summary())


@app.route('/api/ai/recommend-stats')
@login_required
def api_ai_recommend_stats():
    """P3 r27 — _stub_recommend_stats() JSON wrap."""
    return jsonify(_stub_recommend_stats())


@app.route('/api/bigquery/analytics')
@login_required
def api_bigquery_analytics():
    """P3 r28. BigQuery 마트 ad-hoc — ?kind=recommendation_mart|customer_summary|prediction_result."""
    kind = request.args.get('kind', 'recommendation_mart')
    return jsonify(_stub_bigquery_analytics(kind))


@app.route('/api/network/tgw')
@login_required
def api_network_tgw():
    """P4 r56. TGW + Attachment 상태."""
    return jsonify(_ping_tgw())


@app.route('/api/network/vpn')
@login_required
def api_network_vpn():
    """P4 r57. VPN 터널 상태 + CloudWatch 트래픽."""
    return jsonify(_ping_vpn())


def _ping_ecs_services():
    """ECS 클러스터 내 서비스 목록 + CloudWatch CPU/메모리 사용률 조회.

    AWS/ECS 네임스페이스 — CloudWatch Agent 없이 자동 수집.
    실패 시 빈 list 반환.
    """
    from datetime import datetime, timezone, timedelta
    try:
        ecs = _boto('ecs')
        cluster_arns = ecs.list_clusters().get('clusterArns', [])
        if not cluster_arns:
            return []

        services = []
        for cluster_arn in cluster_arns:
            cluster_name = cluster_arn.split('/')[-1]
            svc_arns = ecs.list_services(cluster=cluster_arn).get('serviceArns', [])
            if not svc_arns:
                continue
            descs = ecs.describe_services(cluster=cluster_arn, services=svc_arns).get('services', [])
            for svc in descs:
                services.append({
                    'cluster':  cluster_name,
                    'name':     svc['serviceName'],
                    'status':   svc['status'],
                    'running':  svc['runningCount'],
                    'desired':  svc['desiredCount'],
                    'cpu_pct':  None,
                    'mem_pct':  None,
                })

        if not services:
            return services

        cw    = _boto('cloudwatch')
        now   = datetime.now(timezone.utc)
        start = now - timedelta(minutes=15)
        queries = []
        for i, s in enumerate(services):
            dims = [
                {'Name': 'ClusterName', 'Value': s['cluster']},
                {'Name': 'ServiceName', 'Value': s['name']},
            ]
            queries.append({
                'Id': f'cpu{i}',
                'MetricStat': {
                    'Metric': {'Namespace': 'AWS/ECS', 'MetricName': 'CPUUtilization', 'Dimensions': dims},
                    'Period': 300, 'Stat': 'Average',
                },
                'ReturnData': True,
            })
            queries.append({
                'Id': f'mem{i}',
                'MetricStat': {
                    'Metric': {'Namespace': 'AWS/ECS', 'MetricName': 'MemoryUtilization', 'Dimensions': dims},
                    'Period': 300, 'Stat': 'Average',
                },
                'ReturnData': True,
            })

        res   = cw.get_metric_data(MetricDataQueries=queries, StartTime=start, EndTime=now)
        by_id = {m['Id']: m.get('Values') or [] for m in res.get('MetricDataResults', [])}
        for i, s in enumerate(services):
            cpu_vals = by_id.get(f'cpu{i}', [])
            mem_vals = by_id.get(f'mem{i}', [])
            if cpu_vals:
                s['cpu_pct'] = round(cpu_vals[0], 1)
            if mem_vals:
                s['mem_pct'] = round(mem_vals[0], 1)

        return services
    except Exception:
        return []


@app.route('/api/ecs/status')
@login_required
def api_ecs_status():
    """ECS 서비스 목록 + CPU/메모리 사용률."""
    return jsonify(_ping_ecs_services())


@app.route('/api/vm/platform')
@login_required
def api_vm_platform():
    """Platform VPC (lifesync-dev-lifesync-vpc) EC2 인스턴스."""
    rows = _ping_vm_status() or []
    return jsonify([r for r in rows if r.get('deploy_group') == 'platform'])


@app.route('/api/vm/group')
@login_required
def api_vm_group():
    """P4 r58. Group VM EC2 인스턴스 (tag Project=lifesync)."""
    rows = _ping_vm_status() or []
    return jsonify([r for r in rows if r.get('deploy_group') == 'group-app'])


@app.route('/api/vm/wearable')
@login_required
def api_vm_wearable():
    """P4 r59. Wearable VM + CloudWatch custom metric (LifeSync/Wearable)."""
    rows = _ping_vm_status()
    return jsonify({
        'instances': [r for r in rows if r.get('deploy_group') == 'wearable-app'],
        'metrics'  : _ping_wearable_metrics(),
    })


@app.route('/api/vm/management')
@login_required
def api_vm_management():
    """Management VPC EC2 인스턴스 (admin EC2)."""
    rows = _ping_vm_status() or []
    return jsonify([r for r in rows if r.get('deploy_group') == 'management'])


@app.route('/api/kinesis/status')
@login_required
def api_kinesis_status():
    """P1 r23, P4 r15. Kinesis stream 단건 상태."""
    return jsonify(_ping_kinesis())


@app.route('/api/emr/status')
@login_required
def api_emr_status():
    """P4 r13. EMR Cluster 목록 + 상태."""
    return jsonify(_ping_emr())


@app.route('/api/datavpc/status')
@login_required
def api_datavpc_status():
    """DataVPC 컴포넌트 통합 상태 — S3(raw/processed/curated) / Kinesis / Glue / EMR."""
    def _s3_state(bucket):
        try:
            _boto('s3').head_bucket(Bucket=bucket)
            return 'EXISTS'
        except Exception:
            return 'NOT_FOUND'

    raw_bucket  = os.environ.get('LIFESYNC_RAW_S3_BUCKET',       'lifesync-raw')
    proc_bucket = os.environ.get('LIFESYNC_PROCESSED_S3_BUCKET', 'lifesync-processed')
    cur_bucket  = os.environ.get('LIFESYNC_CURATED_S3_BUCKET',   'lifesync-curated')
    emr_list = _ping_emr()
    return jsonify({
        's3_bucket':      raw_bucket,
        's3_state':       _s3_state(raw_bucket),
        's3_proc_bucket': proc_bucket,
        's3_proc_state':  _s3_state(proc_bucket),
        's3_cur_bucket':  cur_bucket,
        's3_cur_state':   _s3_state(cur_bucket),
        'kinesis':        _ping_kinesis(),
        'glue':           _ping_glue_last_run(),
        'emr':            emr_list[0] if emr_list else {},
    })


@app.route('/api/admin/applications')
@login_required
def api_admin_applications():
    """
    상품 신청 내역 조회 — customer_product_application 테이블.
    Query params:
      status   : RECEIVED / IN_REVIEW / APPROVED / REJECTED / CANCELED (선택)
      gid      : 특정 global_id (선택)
      limit    : default 50, max 200
      offset   : default 0
    """
    status = request.args.get('status')
    gid    = request.args.get('gid')
    try:
        limit  = min(int(request.args.get('limit', '50')), 200)
        offset = max(int(request.args.get('offset', '0')), 0)
    except ValueError:
        return jsonify({'error': 'limit/offset must be int'}), 400

    where, args = ['1=1'], []
    if status:
        where.append('a.status = %s');     args.append(status)
    if gid:
        where.append('a.global_id = %s'); args.append(gid)
    where_sql = ' AND '.join(where)

    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM customer_product_application a WHERE {where_sql}",
                tuple(args),
            )
            total = cur.fetchone()['cnt']

            cur.execute(
                "SELECT a.application_id, a.global_id, a.ls_user_id, "
                "       p.product_code, p.product_name, "
                "       c.company_name, cat.category_name, "
                "       a.status, a.reviewer_id, a.reviewed_at, "
                "       a.applied_at AS created_at, a.updated_at "
                "FROM customer_product_application a "
                "LEFT JOIN product_master  p   ON a.product_id  = p.product_id "
                "LEFT JOIN company_master  c   ON p.company_id  = c.company_id "
                "LEFT JOIN category_master cat ON p.category_id = cat.category_id "
                f"WHERE {where_sql} "
                "ORDER BY a.applied_at DESC LIMIT %s OFFSET %s",
                tuple(args) + (limit, offset),
            )
            rows = []
            for r in cur.fetchall():
                rows.append({**r,
                    'reviewed_at': str(r['reviewed_at']) if r.get('reviewed_at') else None,
                    'created_at':  str(r['created_at'])  if r.get('created_at')  else None,
                    'updated_at':  str(r['updated_at'])  if r.get('updated_at')  else None,
                })
    except Exception as e:
        return jsonify({'error': f'조회 실패: {str(e)}'}), 500

    return jsonify({'total': total, 'limit': limit, 'offset': offset, 'rows': rows})


# ── 운영 모니터링 ─────────────────────────────────────
@app.route('/ops')
@login_required
def ops():
    """ops 페이지 — 토폴로지/VPC 카드는 정적, Wearable 만 메모리 엔진.

    _ping_* SSR 직접 호출 X (5초 지연 원인). 실 AWS 데이터는 API 라우트 (/api/network/tgw 등) 로 별도 노출.
    """
    wearable_snap = wearable_engine.snapshot()
    # VPC 카드는 JS 폴링 (30s) 으로 _ping_* 결과 채움. SSR 은 빈 카드 + 토폴로지/엔드포인트만 정적
    topology   = _NET_TOPOLOGY
    platform   = dict(_NET_AWS_PLATFORM,     rows=[])
    data       = dict(_NET_AWS_DATA,         rows=[])
    gvm        = dict(_NET_AWS_GROUPVM,      rows=[])
    wearable   = dict(_NET_AWS_WEARABLE,     rows=[])
    management = dict(_NET_AWS_MANAGEMENT,   rows=[])
    conn       = dict(_NET_AWS_CONNECTIVITY, rows=[])
    gcp        = dict(_NET_GCP,    rows=[])
    onprem     = dict(_NET_ONPREM, rows=[])

    return render_template('ops.html',
        active='ops',
        topology=topology,
        net_platform=platform, net_wearable=wearable, net_data=data,
        net_groupvm=gvm, net_management=management,
        net_conn=conn, net_gcp=gcp, net_onprem=onprem,
        wearable_kpi=wearable_snap['kpi'],
        wearable_red=wearable_snap['red'],
        wearable_yellow=wearable_snap['yellow'],
    )


@app.context_processor
def inject_config():
    return {
        'config': {'ADMIN_USER': ADMIN_USER},
        'consent_labels': CONSENT_LABELS,
    }


@app.route('/api/debug/cloud')
@login_required
def api_debug_cloud():
    """임시 디버그: boto3 raw 결과 + STS identity"""
    out = {}
    try:
        sts = boto3.client('sts', region_name=AWS_REGION)
        out['sts_identity'] = sts.get_caller_identity()
    except Exception as e:
        out['sts_identity'] = str(e)
    try:
        rds = boto3.client('rds', region_name=AWS_REGION)
        clusters = rds.describe_db_clusters().get('DBClusters', [])
        out['rds_clusters'] = [{'id': c.get('DBClusterIdentifier'), 'status': c.get('Status')} for c in clusters]
    except Exception as e:
        out['rds_clusters'] = str(e)
    try:
        ddb = boto3.client('dynamodb', region_name=AWS_REGION)
        out['ddb_tables'] = ddb.list_tables().get('TableNames', [])
    except Exception as e:
        out['ddb_tables'] = str(e)
    try:
        s3 = boto3.client('s3', region_name=AWS_REGION)
        raw_bucket = os.environ.get('LIFESYNC_RAW_S3_BUCKET', 'lifesync-raw')
        out['s3_head_raw'] = 'EXISTS'
        s3.head_bucket(Bucket=raw_bucket)
    except Exception as e:
        out['s3_head_raw'] = str(e)
    out['env_AWS_REGION'] = AWS_REGION
    out['env_AURORA_HOST'] = os.environ.get('AURORA_HOST', 'NOT SET')
    out['env_GCP_PROJECT_ID'] = os.environ.get('GCP_PROJECT_ID', 'NOT SET')
    out['boto_clients_keys'] = list(_boto_clients.keys())
    return jsonify(out)


if __name__ == '__main__':
    # threaded=True — SSE 장기 연결 + 일반 요청 동시 처리
    app.run(debug=True, port=5001, threaded=True)
