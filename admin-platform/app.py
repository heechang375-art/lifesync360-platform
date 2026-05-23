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
    """Secrets Manager /lifesync/dev/db/master + SSM Parameter Store → os.environ (미설정 항목만 주입)"""
    try:
        client = boto3.client('secretsmanager', region_name='ap-northeast-2')
        resp = client.get_secret_value(SecretId='/lifesync/dev/db/master')
        for k, v in json.loads(resp['SecretString']).items():
            if not os.environ.get(k):
                os.environ[k] = str(v)
    except Exception:
        pass
    try:
        ssm = boto3.client('ssm', region_name='ap-northeast-2')
        if not os.environ.get('GCP_PROJECT_ID'):
            r = ssm.get_parameter(Name='/lifesync/gcp_project_id', WithDecryption=True)
            os.environ['GCP_PROJECT_ID'] = r['Parameter']['Value']
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
ONPREM_QUERY_LAMBDA  = os.environ.get('ONPREM_QUERY_LAMBDA', '')

GRADES = ['VIP', 'GOLD', 'SILVER', 'BASIC', 'CARE']
CONSENT_LABELS = {
    'BANK':       '은행',
    'CARD':       '카드',
    'INSURANCE':  '보험',
    'SECURITIES': '증권',
    'HEALTHCARE': '헬스케어',
    'HOSPITAL':   '병원',
    'WEARABLE':   '웨어러블',
}

from mockup_data import (
    MOCKUP_GCP_STATUS_DETAIL,
    MOCKUP_AI_KPI,
    MOCKUP_REDIS_PERSONALIZED,
    MOCKUP_DASH_KPI, MOCKUP_DASH_CLOUD3, MOCKUP_DASH_S3_5, MOCKUP_DASH_RECENT_UPLOADS,
    MOCKUP_AI_KPI4,
    MOCKUP_NET_TOPOLOGY,
    MOCKUP_NET_AWS_PLATFORM, MOCKUP_NET_AWS_DATA, MOCKUP_NET_AWS_GROUPVM,
    MOCKUP_NET_AWS_CONNECTIVITY, MOCKUP_NET_GCP, MOCKUP_NET_ONPREM,
    MOCKUP_NET_API_ENDPOINTS,
)


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


def _call_onprem(action, **kwargs):
    if not ONPREM_QUERY_LAMBDA:
        return {}
    import json as _j
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


def _add_rates(funnel_rows):
    for row in funnel_rows:
        rec = row['recommended'] or 1
        row['click_rate']    = round(row['clicked']   / rec * 100)
        row['purchase_rate'] = round(row['purchased'] / rec * 100)
    return funnel_rows


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
    raw_bucket = os.environ.get('LIFESYNC_RAW_S3_BUCKET', '')
    if not raw_bucket:
        return {'raw_bucket_files': 0, 'today_ingested': 0, 'iot_count': 0,
                'last_upload': {}, 'failed_count': 0}
    from datetime import datetime, timezone, timedelta
    today_prefix = datetime.now(timezone.utc).strftime('%Y-%m-%d')
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
            for page in paginator.paginate(Bucket=raw_bucket, Prefix=prefix):
                for o in page.get('Contents', []):
                    total_size += o.get('Size', 0)
                    if today_prefix in o['Key']:
                        today += 1
                    if 'wearable' in prefix or 'iot' in o['Key'].lower():
                        iot += 1
                    if latest is None or o['LastModified'] > latest['LastModified']:
                        latest = o
        return {
            'raw_bucket_files': total,
            'today_ingested':   today,
            'iot_count':        iot,
            'total_size_bytes': total_size,
            'last_upload': {
                'time': latest['LastModified'].strftime('%H:%M') if latest else '-',
                'file': latest['Key'].split('/')[-1] if latest else '-',
                'size_mb': round(latest['Size'] / 1024 / 1024, 2) if latest else 0,
            } if latest else {},
            'failed_count': 0,
        }
    except Exception:
        return {'raw_bucket_files': total, 'today_ingested': 0, 'iot_count': 0,
                'total_size_bytes': 0, 'last_upload': {}, 'failed_count': 0}


def _ping_domain_flow():
    """도메인별 S3 prefix 적재 현황 — 7 도메인."""
    raw_bucket = os.environ.get('LIFESYNC_RAW_S3_BUCKET', '')
    stream     = os.environ.get('INGESTION_STREAM_NAME', 'lifesync-kinesis-wearable-stream')
    domains    = [
        ('BANK',       'LS 은행',     'bank/'),
        ('CARD',       'LS 카드',     'card/'),
        ('INSURANCE',  'LS 보험',     'insurance/'),
        ('SECURITIES', 'LS 증권',     'securities/'),
        ('HEALTHCARE', 'LS 헬스케어', 'healthcare/'),
        ('HOSPITAL',   'LS 병원',     'hospital/'),
    ]
    out = []
    if not raw_bucket:
        return out
    from datetime import datetime, timezone, timedelta
    today_prefix = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    warn_threshold = datetime.now(timezone.utc) - timedelta(hours=1)
    s3 = _boto('s3')
    paginator = s3.get_paginator('list_objects_v2')
    for code, label, prefix in domains:
        try:
            files = []
            for page in paginator.paginate(Bucket=raw_bucket, Prefix=prefix):
                files.extend(page.get('Contents', []))
            today_count = sum(1 for f in files if today_prefix in f['Key'])
            latest      = max(files, key=lambda f: f['LastModified']) if files else None
            state = 'OK' if latest and latest['LastModified'] > warn_threshold else ('WARN' if latest else 'DOWN')
            out.append({
                'domain': code, 'label': label,
                'last_upload_at': latest['LastModified'].strftime('%H:%M:%S') if latest else '-',
                'files_today':   today_count, 'state': state,
                'source':        f's3://{raw_bucket}/{prefix}',
            })
        except Exception:
            out.append({'domain': code, 'label': label, 'last_upload_at': '-', 'files_today': 0, 'state': 'ERR', 'source': '-'})
    # WEARABLE: Kinesis IncomingRecords (last 5min)
    try:
        from datetime import datetime, timezone, timedelta
        cw    = _boto('cloudwatch')
        now   = datetime.now(timezone.utc)
        stats = cw.get_metric_statistics(
            Namespace='AWS/Kinesis', MetricName='IncomingRecords',
            Dimensions=[{'Name': 'StreamName', 'Value': stream}],
            StartTime=now - timedelta(minutes=5), EndTime=now, Period=60, Statistics=['Sum'],
        )
        total = sum(p.get('Sum', 0) for p in stats.get('Datapoints', []))
        out.append({'domain': 'WEARABLE', 'label': '웨어러블',
                    'last_upload_at': now.strftime('%H:%M:%S'),
                    'files_today': int(total),
                    'state': 'OK' if total > 0 else 'WARN',
                    'source': f'Kinesis: {stream}'})
    except Exception:
        out.append({'domain': 'WEARABLE', 'label': '웨어러블', 'last_upload_at': '-',
                    'files_today': 0, 'state': 'ERR', 'source': f'Kinesis: {stream}'})
    return out


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
                if   'group'    in vpc_name: deploy_group = 'group-app'
                elif 'wearable' in vpc_name: deploy_group = 'wearable-app'
                elif 'lifesync' in vpc_name: deploy_group = 'platform'
                else:                        deploy_group = 'other'
                out.append({
                    'vm_id':        inst['InstanceId'],
                    'name':         tags.get('Name', '-'),
                    'state':        inst['State']['Name'],
                    'deploy_group': deploy_group,
                    'vpc':          vpc_name,
                    'cpu_pct': 0,
                    'mem_pct': None,  # CWAgent 미설치 — 별도 배포 후 보강
                })
        _boost_vm_cpu(out)
        return out
    except Exception:
        return []


def _boost_vm_cpu(rows):
    """AWS/EC2 CPUUtilization 최근 10분 평균을 batch 로 가져와 cpu_pct 보강.

    get_metric_data 1 회 호출로 모든 인스턴스를 한꺼번에. 실패 시 0 유지.
    """
    if not rows:
        return
    from datetime import datetime, timezone, timedelta
    try:
        cw    = _boto('cloudwatch')
        now   = datetime.now(timezone.utc)
        start = now - timedelta(minutes=10)
        queries = [{
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
        } for i, r in enumerate(rows)]
        res = cw.get_metric_data(MetricDataQueries=queries, StartTime=start, EndTime=now)
        by_id = {m['Id']: m.get('Values') or [] for m in res.get('MetricDataResults', [])}
        for i, r in enumerate(rows):
            vals = by_id.get(f'cpu{i}', [])
            if vals:
                r['cpu_pct'] = round(vals[0], 1)
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


def _ping_lambda_metrics():
    """V4 P4 r6 — `lifesync-` prefix Lambda 함수 자동 발견 + CloudWatch 1h 메트릭.

    Invocations / Errors / Duration 합산. 신규 함수 배포 시 자동 포함.
    """
    from datetime import datetime, timezone, timedelta
    fns = _list_lifesync_lambdas()
    if not fns:
        return []
    cw  = _boto('cloudwatch')
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=1)
    out = []
    for fn in fns:
        try:
            inv = cw.get_metric_statistics(
                Namespace='AWS/Lambda', MetricName='Invocations',
                Dimensions=[{'Name': 'FunctionName', 'Value': fn}],
                StartTime=start, EndTime=now, Period=3600, Statistics=['Sum'],
            )
            err = cw.get_metric_statistics(
                Namespace='AWS/Lambda', MetricName='Errors',
                Dimensions=[{'Name': 'FunctionName', 'Value': fn}],
                StartTime=start, EndTime=now, Period=3600, Statistics=['Sum'],
            )
            dur = cw.get_metric_statistics(
                Namespace='AWS/Lambda', MetricName='Duration',
                Dimensions=[{'Name': 'FunctionName', 'Value': fn}],
                StartTime=start, EndTime=now, Period=3600, Statistics=['Average'],
            )
            out.append({
                'fn': fn,
                'invocations_1h':  int(sum(p['Sum']     for p in inv.get('Datapoints', []))),
                'errors_1h':       int(sum(p['Sum']     for p in err.get('Datapoints', []))),
                'avg_duration_ms': int(sum(p['Average'] for p in dur.get('Datapoints', [])) / max(1, len(dur.get('Datapoints', [])))),
            })
        except Exception:
            out.append({'fn': fn, 'invocations_1h': 0, 'errors_1h': 0, 'avg_duration_ms': 0})
    return out


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


def _ping_next_batch():
    """EventBridge 다음 배치 예정."""
    rule = os.environ.get('GLUE_SCHEDULE_RULE', 'lifesync-daily-etl-rule')
    try:
        info = _boto('events').describe_rule(Name=rule)
        return {
            'rule_name':         rule,
            'schedule':          info.get('ScheduleExpression', '-'),
            'next_scheduled_at': '-',  # AWS는 next fire time API 없음 — UI에서 schedule expression만 표시
        }
    except Exception:
        return {}


# ── 멀티클라우드 — TGW / VPN / VPC Peering ping ───────────
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
            for t in c.get('VgwTelemetry', []) or [{'OutsideIpAddress': '-', 'Status': '-'}]:
                out.append({
                    'id':               f"{c['VpnConnectionId']}-{t.get('OutsideIpAddress', '?')}",
                    'status':           t.get('Status', '-').upper(),
                    'bgp_asn':          str(cgw_info.get('BgpAsn', '-')),
                    'traffic_in_mbps':  0,
                    'traffic_out_mbps': 0,
                    'peer':             cgw_info.get('IpAddress', tag_name),
                })
        return {'tunnels': out}
    except Exception:
        return {}


def _ping_vpc_peering():
    try:
        peers = _boto('ec2').describe_vpc_peering_connections().get('VpcPeeringConnections', [])
        return [
            {
                'id':        p['VpcPeeringConnectionId'],
                'state':     p.get('Status', {}).get('Code', '-'),
                'requester': p.get('RequesterVpcInfo', {}).get('VpcId', '-'),
                'accepter':  p.get('AccepterVpcInfo', {}).get('VpcId', '-'),
            }
            for p in peers
        ]
    except Exception:
        return []


def _ping_wearable_realtime():
    """Wearable CloudWatch custom metric (hr/bp/spo2/steps/alerts/send)."""
    from datetime import datetime, timezone, timedelta
    cw    = _boto('cloudwatch')
    now   = datetime.now(timezone.utc)
    start = now - timedelta(minutes=5)
    metrics = [
        ('심박수',        'wearable_hr',      'bpm',     '60-100'),
        ('혈압',          'wearable_bp_sys',  '',        '< 120/80'),
        ('산소포화도',    'wearable_spo2',    '%',       '≥ 95'),
        ('운동량 (steps)','wearable_steps',   '',        '—'),
        ('이상 이벤트',   'wearable_alerts',  '24h',     '24h'),
        ('데이터 송신',   'wearable_send',    '/min',    '—'),
    ]
    out = []
    for label, m, suffix, rng in metrics:
        try:
            stats = cw.get_metric_statistics(
                Namespace='LifeSync/Wearable', MetricName=m,
                StartTime=start, EndTime=now, Period=60, Statistics=['Average'],
            )
            pts = stats.get('Datapoints', [])
            v = round(pts[-1]['Average'], 1) if pts else 0
            out.append({'metric': label, 'current': f'{v}{suffix}', 'range': rng,
                        'state': 'OK', 'source': f'CW · {m}'})
        except Exception:
            out.append({'metric': label, 'current': '-', 'range': rng,
                        'state': 'ERR', 'source': f'CW · {m}'})
    return out


def _ping_local_lab():
    """Local Lab 상태 — onprem Lambda action 'local_lab_status'."""
    try:
        data = _call_onprem('local_lab_status')
        return data.get('environments', [])
    except Exception:
        return []


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
GCP_PROJECT_ID  = os.environ.get('GCP_PROJECT_ID', '')
GCP_BQ_DATASET  = os.environ.get('GCP_BQ_DATASET', 'lifesync_curated')
GCP_VERTEX_LOC  = os.environ.get('GCP_VERTEX_LOCATION', 'asia-northeast3')

_gcp_bq_client      = None
_gcp_aip_initialized= False
_gcp_mon_client     = None


def _get_bq():
    global _gcp_bq_client
    if not GCP_PROJECT_ID:
        return None
    if _gcp_bq_client is None:
        try:
            from google.cloud import bigquery as _bq
            _gcp_bq_client = _bq.Client(project=GCP_PROJECT_ID)
        except Exception:
            return None
    return _gcp_bq_client


def _init_aip():
    global _gcp_aip_initialized
    if not GCP_PROJECT_ID:
        return False
    if not _gcp_aip_initialized:
        try:
            from google.cloud import aiplatform
            aiplatform.init(project=GCP_PROJECT_ID, location=GCP_VERTEX_LOC)
            _gcp_aip_initialized = True
        except Exception:
            return False
    return _gcp_aip_initialized


def _get_mon():
    global _gcp_mon_client
    if not GCP_PROJECT_ID:
        return None
    if _gcp_mon_client is None:
        try:
            from google.cloud import monitoring_v3 as _mon
            _gcp_mon_client = _mon.MetricServiceClient()
        except Exception:
            return None
    return _gcp_mon_client


def _stub_gcp_status():
    """
    P4 r32~36 — GCP BigQuery / Vertex AI / Cloud Run 상태.
    Cloud Monitoring API 로 service 별 uptime/health 조회. 인증/호출 실패 시 빈 list.
    """
    mon = _get_mon()
    if mon is None:
        return []
    try:
        # BQ 쿼리 잡 카운트 (최근 7일) — Monitoring 'bigquery.googleapis.com/job/num_in_flight'
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
                    'name':     f'projects/{GCP_PROJECT_ID}',
                    'filter':   f'metric.type="{metric}"',
                    'interval': interval,
                    'view':     _mon.ListTimeSeriesRequest.TimeSeriesView.HEADERS,
                })
                series = list(mon.list_time_series(request=req))
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
        latest = models[0]
        evals  = latest.list_model_evaluations()
        if not evals:
            return {'model_id': latest.resource_name, 'evaluations': []}
        ev = list(evals)[0]
        return {
            'model_id'   : latest.resource_name,
            'display_name': latest.display_name,
            'create_time': str(latest.create_time),
            'metrics'    : dict(ev.metrics) if hasattr(ev, 'metrics') else {},
        }
    except Exception:
        return {}


def _stub_feature_importance():
    """
    P3 r9 — Feature Importance: BigQuery lifesync_curated.ai_feature_table 컬럼별 분포.
    """
    bq = _get_bq()
    if bq is None:
        return []
    try:
        sql = f"""
            SELECT column_name, AVG(value) AS avg_val, STDDEV(value) AS std_val
            FROM `{GCP_PROJECT_ID}.{GCP_BQ_DATASET}.ai_feature_table`
            GROUP BY column_name
            ORDER BY ABS(avg_val) DESC
            LIMIT 20
        """
        return [dict(row) for row in bq.query(sql).result()]
    except Exception:
        return []


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
                      FROM `{GCP_PROJECT_ID}.{GCP_BQ_DATASET}.recommendation_mart`
                      GROUP BY recommendation_name ORDER BY cnt DESC LIMIT 20"""
        elif query_kind == 'customer_summary':
            sql = f"""SELECT * FROM `{GCP_PROJECT_ID}.lifesync_serving.v_customer_summary` LIMIT 100"""
        elif query_kind == 'prediction_result':
            sql = f"""SELECT model_name,
                             COUNTIF(actual_label IS NOT NULL) AS labeled,
                             AVG(IF(predicted_label = actual_label, 1.0, 0.0)) AS accuracy
                      FROM `{GCP_PROJECT_ID}.lifesync_ml.vip_prediction_result`
                      WHERE actual_label IS NOT NULL
                      GROUP BY model_name"""
        else:
            return []
        return [dict(row) for row in bq.query(sql).result()]
    except Exception:
        return []


_redis_client = None


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
    """
    Redis Personalized Top 3 — ZREVRANGE rec:{global_id} 0 N WITHSCORES (TTL 6h).
    miss/실패 시 빈 dict 반환 → /users/<id> 라우트에서 MOCKUP_REDIS_PERSONALIZED fallback.
    """
    r = _get_redis()
    if r is None:
        return {}
    try:
        pairs = r.zrevrange(f'rec:{global_id}', 0, 2, withscores=True)
        if not pairs:
            return {}
        return {
            'top': [{'product_id': pid, 'score': float(score)} for pid, score in pairs],
            'source': 'redis',
        }
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
    color_map = {'S': '#dc2626', 'A': '#f59e0b', 'B': '#3b82f6', 'C': '#16a34a', 'D': '#94a3b8'}
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
    """ml_model_evaluation_daily 최신 모델별 Precision/Recall."""
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT model_name AS name, "
                "       ROUND(precision_score * 100, 1) AS `precision`, "
                "       ROUND(recall_score    * 100, 1) AS recall "
                "FROM ml_model_evaluation_daily "
                "ORDER BY eval_date DESC LIMIT 4"
            )
            return [
                {'name': r['name'], 'precision': float(r['precision'] or 0), 'recall': float(r['recall'] or 0)}
                for r in cur.fetchall()
            ]
    except Exception:
        return []


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
    """고객 인사이트 분석 — Aurora customer_recommend_history 7일 집계."""
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT global_id) AS active_customers, "
                "       ROUND(SUM(clicked_flag IN ('Y','1')) * 100.0 / COUNT(*), 1) AS avg_ctr, "
                "       ROUND(SUM(purchased_flag IN ('Y','1')) * 100.0 / COUNT(*), 1) AS avg_cvr, "
                "       COUNT(*) AS total_rec "
                "FROM customer_recommend_history "
                "WHERE recommended_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
            )
            row = cur.fetchone() or {}
        if not row or not row.get('total_rec'):
            return {'source': 'Aurora · customer_recommend_history', 'rows': []}
        return {
            'source': 'Aurora · customer_recommend_history (최근 7일)',
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
        kpi=[dict(c, value='-') for c in MOCKUP_DASH_KPI],
        cloud3=[dict(c, state='-', sub='-') for c in MOCKUP_DASH_CLOUD3],
        s3_cards=[dict(c, value='-', note='-') for c in MOCKUP_DASH_S3_5],
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
            profile['name_masked'] = name[0] + '*' * (len(name) - 1)
        mobile = pii.get('mobile', '') or ''
        if len(mobile) >= 11:
            profile['phone_masked'] = f"{mobile[:3]}-****-{mobile[-4:]}"
        profile['gender'] = pii.get('gender', '-') or '-'
        birth = pii.get('birth_date', '') or ''
        if birth:
            try:
                from datetime import datetime as _dt
                age = _dt.now().year - int(birth.split('-')[0])
                profile['age_band'] = f'{(age // 10) * 10}대'
            except Exception:
                pass
        addr = pii.get('address', '') or ''
        if addr:
            profile['region'] = addr.split()[0]
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
                topn.append({'rank': i + 1, 'product': _pm.get(pid, f'상품 {pid}'), 'score': f"{float(p['score']):.2f}"})
    except Exception:
        pass

    # ④ 교차판매 (cross_sell_rule)
    crosssell = []
    try:
        _db = get_db()
        try:
            with _db.cursor() as _cur:
                _cur.execute(
                    'SELECT r.target_category, '
                    '(SELECT p.product_name FROM product_master p '
                    ' JOIN category_master c2 ON p.category_id = c2.category_id '
                    ' WHERE c2.category_code = r.target_category AND p.active_flag = "Y" '
                    ' ORDER BY p.priority_rank ASC LIMIT 1) AS product_name, '
                    '(SELECT c3.category_name FROM category_master c3 WHERE c3.category_code = r.target_category LIMIT 1) AS category_name '
                    'FROM cross_sell_rule r WHERE r.active_flag = "Y" ORDER BY r.priority_rank ASC LIMIT 3'
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

    _grade = (_scores or {}).get('dynamic_grade', 'C')
    _dyn_score = float((_scores or {}).get('dynamic_score', 50))
    _vip_prob = float((_scores or {}).get('vip_prob', 0))
    _rec_prob = float((_scores or {}).get('rec_prob', 0))
    _signup_prob = float((_scores or {}).get('signup_prob', 0))
    _nba_action_map = {
        'S': 'VIP 전용 프리미엄 자산관리 서비스 가입 권유',
        'A': '우수 고객 혜택 패키지 안내',
        'B': '중장기 재테크 상품 추천',
        'C': '기본 저축 상품 및 혜택 안내',
        'D': '고객 니즈 파악 상담 진행',
    }
    nba = {
        'action': _nba_action_map.get(_grade, '-'),
        'targets': [
            {'label': 'VIP 전환 확률', 'state': f'{_vip_prob:.0%}'},
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
            {'label': 'VIP 확률', 'value': f'{_vip_prob:.0%}', 'color': '#14b8a6'},
        ]

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
    personalized = _stub_redis_personalized(global_id) or MOCKUP_REDIS_PERSONALIZED

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
    """P3 r10. Aurora customer_recommend_daily 최근 7일 + 평균."""
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

    응답 스키마: MOCKUP_DASH_KPI 와 동일 9-element list — 각 요소 `{label, value, sub, accent, is_status}`.
    실 호출 결과로 value 만 덮어쓰고, 실패한 카드는 mockup 값 fallback.
    """
    cards = [dict(c, value='-') for c in MOCKUP_DASH_KPI]

    # KPI 1~3: On-Prem Lambda (VPN 연결 필요)
    for idx, action in [(0, 'count_master_customer'), (1, 'count_users'), (2, 'count_users_consented')]:
        try:
            c = (_call_onprem(action) or {}).get('count')
            if c is not None:
                cards[idx]['value'] = f'{int(c):,}'
        except Exception:
            pass

    # KPI 4: AI 추천 상태 — DDB 최신 update_time
    try:
        items = get_dynamo_table().scan(ProjectionExpression='update_time', Limit=1).get('Items', [])
        if items and items[0].get('update_time'):
            cards[3]['value'] = 'Vertex AI'
            cards[3]['sub'] = f"DynamoDB · 최근 갱신 {items[0]['update_time']}"
    except Exception:
        pass

    # KPI 5~8: Aurora 추천 통계
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
                cards[4]['value'] = f"{int(r['total']):,}"
                ctr = (r['clicked'] or 0) / r['total'] * 100
                cvr = (r['purchased'] or 0) / r['total'] * 100
                cards[6]['value'] = f"{ctr:.1f}%"
                cards[7]['value'] = f"{cvr:.1f}%"
    except Exception:
        pass

    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM customer_dashboard_log")
            r = cur.fetchone()
            if r:
                n = int(r['cnt'])
                cards[5]['value'] = f"{n/1e6:.1f}M" if n >= 1_000_000 else f"{n:,}"
    except Exception:
        pass

    # KPI 9: Redis DBSIZE
    try:
        rc = _get_redis()
        if rc:
            cards[8]['value'] = f"{rc.dbsize():,}"
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
        'kpi'              : MOCKUP_AI_KPI,
        'trend_7day'       : _aurora_recommend_trend_7day(),
        'segment_today'    : _ddb_query_today(DDB_SEGMENT_TABLE),
        'prob_distribution': _ddb_prob_distribution(),
    }


def _stub_ai_summary():
    """P3 r29 — AI 출력 분포 + 모델 평가 (Precision/Recall/Accuracy)."""
    return {
        'ai_kpi'        : MOCKUP_AI_KPI,
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
    """P1 r30 — S3 적재 5 카드 list (시연↔운영 동일 구조).

    응답: MOCKUP_DASH_S3_5 와 동일 5-element list — `{icon, label, value, note}`.
    """
    raw = _ping_s3_ingestion() or {}
    last = raw.get('last_upload') or {}
    iot  = raw.get('iot_count', 0)
    size_gb = (raw.get('total_size_bytes', 0) / 1024 / 1024 / 1024) if raw.get('total_size_bytes') else 0

    # 카드 5개 구조 유지 + value/note 빈 값으로 초기화 (안 들어오는 항목은 그대로 비어 보임)
    cards = [dict(c, value='-', note='-') for c in MOCKUP_DASH_S3_5]
    if raw.get('raw_bucket_files'): cards[0]['value'] = f"{raw['raw_bucket_files']:,}"
    if raw.get('today_ingested'):   cards[1]['value'] = f"{raw['today_ingested']:,}"
    if iot:                         cards[2]['value'] = f"{iot:,}"
    if size_gb:                     cards[3]['value'] = f"{size_gb:.1f} GB"
    if last.get('time'):
        cards[4]['value'] = last['time']
        cards[4]['note']  = last.get('file', '-')
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
    return jsonify({'aws': _ping_cloud_status(), 'gcp': _stub_gcp_status() or MOCKUP_GCP_STATUS_DETAIL})


def _cloud3_from_aws():
    """AWS / GCP / On-Prem 3 카드 + 서비스별 details. 안 들어오는 데이터는 '-' 로 비워둠."""
    aws_list = _ping_cloud_status() or []
    cards = [dict(c, state='-', sub='-', details=[]) for c in MOCKUP_DASH_CLOUD3]

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

    # GCP — stub 응답 (자격증명 없으면 빈 dict → state '-' 유지)
    gcp = _stub_gcp_status() or {}
    if gcp.get('state'):
        cards[1]['state'] = gcp['state']
        cards[1]['sub']   = gcp.get('note', '-')

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
    raw_bucket = os.environ.get('LIFESYNC_RAW_S3_BUCKET', '')
    if not raw_bucket:
        return MOCKUP_DASH_RECENT_UPLOADS
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
        return out or MOCKUP_DASH_RECENT_UPLOADS
    except Exception:
        return MOCKUP_DASH_RECENT_UPLOADS


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
    cards = [dict(c, value='-', sub='-') for c in MOCKUP_AI_KPI4]
    try:
        with get_db() as _db, _db.cursor() as _cur:
            _cur.execute('SELECT ctr, cvr, date FROM customer_recommend_daily ORDER BY date DESC LIMIT 1')
            _row = _cur.fetchone()
            if _row:
                cards[0]['value'] = f"{float(_row['ctr'] or 0):.1f}%"
                cards[0]['sub']   = f"lifesync-recommendation-engine · {_row['date']}"
                cards[1]['value'] = f"{float(_row['cvr'] or 0):.1f}%"
                cards[1]['sub']   = f"lifesync-ingest · {_row['date']}"
    except Exception:
        pass
    try:
        import boto3 as _boto3
        _ddb = _boto3.resource('dynamodb', region_name=AWS_REGION)
        _tbl = _ddb.Table('lifesync_customer_result')
        _resp = _tbl.scan(
            ProjectionExpression='vip_prob, rec_prob, signup_prob',
            Limit=200,
        )
        _items = _resp.get('Items', [])
        if _items:
            _avg = lambda k: sum(float(i.get(k, 0) or 0) for i in _items) / len(_items)
            _score_avg = round((_avg('vip_prob') + _avg('rec_prob') + _avg('signup_prob')) / 3, 2)
            cards[2]['value'] = str(_score_avg)
            cards[2]['sub'] = 'vip_prob / rec_prob / signup_prob 평균'
            cards[3]['value'] = f'{len(_items):,}'
            cards[3]['sub'] = 'DynamoDB lifesync_customer_result · 분석 대상'
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
    """연령대별 추천 성과 — On-Prem 2-step, DDB analytics_segment fallback. V6 R20."""
    try:
        result = _call_onprem('list_by_age_band') or {}
        age_groups = result.get('age_groups', {})
        if age_groups and all(age_groups.get(b) for b in ['20s', '30s', '40s', '50s', '60s+']):
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
                        'cvr': round(pur * 100.0 / clk, 1) if clk else 0,
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
    age = [{'age': r.get('age_band', '-'), 'ctr': r.get('ctr', 0), 'cvr': r.get('cvr', 0)} for r in raw]
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
    """DataVPC 4개 컴포넌트 통합 상태 — S3 / Kinesis / Glue / EMR."""
    raw_bucket = os.environ.get('LIFESYNC_RAW_S3_BUCKET', 'lifesync-354-raw')
    try:
        _boto('s3').head_bucket(Bucket=raw_bucket)
        s3_state = 'EXISTS'
    except Exception:
        s3_state = 'NOT_FOUND'
    emr_list = _ping_emr()
    return jsonify({
        's3_bucket': raw_bucket,
        's3_state':  s3_state,
        'kinesis':   _ping_kinesis(),
        'glue':      _ping_glue_last_run(),
        'emr':       emr_list[0] if emr_list else {},
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
    topology = MOCKUP_NET_TOPOLOGY                # 토폴로지는 디자인 (인프라 그림) — 정적
    endpoints = MOCKUP_NET_API_ENDPOINTS          # API 라우트 listing — 정적 디자인
    platform = dict(MOCKUP_NET_AWS_PLATFORM, rows=[])  # 제목 유지, rows 빈
    data     = dict(MOCKUP_NET_AWS_DATA,     rows=[])
    gvm      = dict(MOCKUP_NET_AWS_GROUPVM,  rows=[])
    conn     = dict(MOCKUP_NET_AWS_CONNECTIVITY, rows=[])
    gcp      = dict(MOCKUP_NET_GCP,    rows=[])
    onprem   = dict(MOCKUP_NET_ONPREM, rows=[])

    return render_template('ops.html',
        active='ops',
        topology=topology,
        net_platform=platform, net_data=data, net_groupvm=gvm,
        net_conn=conn, net_gcp=gcp, net_onprem=onprem,
        wearable_kpi=wearable_snap['kpi'],
        wearable_red=wearable_snap['red'],
        wearable_yellow=wearable_snap['yellow'],
        endpoints=endpoints,
    )


@app.context_processor
def inject_config():
    return {
        'config': {'ADMIN_USER': ADMIN_USER},
        'consent_labels': CONSENT_LABELS,
    }


if __name__ == '__main__':
    # threaded=True — SSE 장기 연결 + 일반 요청 동시 처리
    app.run(debug=True, port=5001, threaded=True)
