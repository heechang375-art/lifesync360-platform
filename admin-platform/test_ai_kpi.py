import boto3, json, os, sys

# bootstrap_secrets 로직 실행
sm = boto3.client('secretsmanager', region_name='ap-northeast-2')
try:
    d = json.loads(sm.get_secret_value(SecretId='/lifesync/dev/db/master')['SecretString'])
    _alias = {'host': 'AURORA_HOST', 'username': 'DB_USER', 'password': 'DB_PASS', 'dbname': 'DB_NAME'}
    for src, dst in _alias.items():
        if src in d:
            os.environ[dst] = str(d[src])
    print('AURORA_HOST:', os.environ.get('AURORA_HOST'))
    print('DB_NAME:', os.environ.get('DB_NAME'))
except Exception as e:
    print('bootstrap ERROR:', e)
    sys.exit(1)

import pymysql

def get_db():
    return pymysql.connect(
        host=os.environ['AURORA_HOST'],
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASS', ''),
        database=os.environ.get('DB_NAME', 'lifesync360'),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )

# CTR/CVR 쿼리
try:
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            "SELECT ROUND(AVG(ctr), 1) AS ctr_7d, ROUND(AVG(cvr), 1) AS cvr_7d "
            "FROM (SELECT ctr, cvr FROM customer_recommend_daily ORDER BY date DESC LIMIT 7) t"
        )
        row = cur.fetchone() or {}
        print('CTR/CVR:', row)
except Exception as e:
    print('CTR/CVR ERROR:', e)

# BQ 정밀도 쿼리
try:
    gcp = json.loads(sm.get_secret_value(SecretId='lifesync/gcp/service-account-key')['SecretString'])
    import tempfile
    t = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(gcp, t); t.close()
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = t.name
    from google.cloud import bigquery
    bq = bigquery.Client(project=gcp['project_id'])
    proj = gcp['project_id']
    sql = (f"SELECT ROUND(accuracy * 100, 1) AS accuracy, ROUND(precision, 4) AS precision_score "
           f"FROM `{proj}.lifesync_ml.model_metrics` WHERE model_name = 'vip' ORDER BY trained_at DESC LIMIT 1")
    rows = list(bq.query(sql).result())
    print('BQ model_metrics vip:', [dict(r) for r in rows])
except Exception as e:
    print('BQ ERROR:', e)
