import sys, os, json
sys.path.insert(0, 'C:/admin-platform')

os.environ['AURORA_HOST'] = 'auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com'
os.environ['DB_USER'] = 'admin'
os.environ['DB_PASS'] = 'ChangeMe123!'
os.environ['DB_NAME'] = 'lifesync360'

import pymysql

conn = pymysql.connect(
    host=os.environ['AURORA_HOST'],
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASS'],
    database=os.environ['DB_NAME'],
    cursorclass=pymysql.cursors.DictCursor,
    connect_timeout=10
)
cur = conn.cursor()

tables = [
    'customer_recommend_daily',
    'customer_recommend_history',
    'analytics_segment_performance',
    'ml_model_evaluation_daily',
    'master_customer',
    'users',
]

results = {}
for t in tables:
    try:
        cur.execute(f'SELECT COUNT(*) AS n FROM {t}')
        results[t] = cur.fetchone()['n']
    except Exception as e:
        results[t] = f'ERR: {e}'

# customer_recommend_daily 있으면 최신 1행 조회
if isinstance(results.get('customer_recommend_daily'), int) and results['customer_recommend_daily'] > 0:
    cur.execute('SELECT * FROM customer_recommend_daily ORDER BY date DESC LIMIT 3')
    results['recommend_daily_sample'] = cur.fetchall()

# analytics_segment_performance 있으면 최신 1행
if isinstance(results.get('analytics_segment_performance'), int) and results['analytics_segment_performance'] > 0:
    cur.execute('SELECT * FROM analytics_segment_performance ORDER BY dt DESC LIMIT 1')
    results['segment_sample'] = cur.fetchall()

conn.close()
print(json.dumps(results, indent=2, default=str))
