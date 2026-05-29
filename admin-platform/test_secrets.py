import boto3, json, os

sm = boto3.client('secretsmanager', region_name='ap-northeast-2')

# DB secret
try:
    r = sm.get_secret_value(SecretId='/lifesync/dev/db/master')
    d = json.loads(r['SecretString'])
    print('DB secret keys:', list(d.keys()))
    print('DB host:', d.get('host', d.get('AURORA_HOST', 'NOT FOUND')))
except Exception as e:
    print('DB secret ERROR:', e)

# Try DB connection
try:
    import pymysql
    d_raw = json.loads(sm.get_secret_value(SecretId='/lifesync/dev/db/master')['SecretString'])
    host = d_raw.get('host') or d_raw.get('AURORA_HOST') or os.environ.get('AURORA_HOST','')
    user = d_raw.get('username') or d_raw.get('DB_USER') or os.environ.get('DB_USER','admin')
    pwd  = d_raw.get('password') or d_raw.get('DB_PASS') or os.environ.get('DB_PASS','')
    db   = d_raw.get('dbname') or d_raw.get('DB_NAME') or os.environ.get('DB_NAME','lifesync')
    print(f'Connecting: host={host}, user={user}, db={db}')
    conn = pymysql.connect(host=host, user=user, password=pwd, database=db,
                           cursorclass=pymysql.cursors.DictCursor, connect_timeout=5)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM customer_recommend_daily LIMIT 1")
        print('DB OK:', cur.fetchone())
    conn.close()
except Exception as e:
    print('DB connect ERROR:', e)
