import sys, io, json, boto3, pymysql
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

d = json.loads(boto3.client('secretsmanager', region_name='ap-northeast-2')
    .get_secret_value(SecretId='/lifesync/dev/db/master')['SecretString'])
conn = pymysql.connect(host=d['host'], user=d['username'], password=d['password'],
    database=d['dbname'], charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor, connect_timeout=10)
cur = conn.cursor()

# company_master 구조
cur.execute('DESCRIBE company_master')
print('company_master cols:', [r['Field'] for r in cur.fetchall()])

# company_master 전체 (consent domain 연결 컬럼 찾기)
cur.execute('SELECT * FROM company_master LIMIT 10')
rows = cur.fetchall()
print('company_master sample:')
for r in rows:
    print(' ', r)

# product_master의 company_id 분포
cur.execute("SELECT company_id, COUNT(*) AS cnt FROM product_master WHERE active_flag='Y' GROUP BY company_id")
print('product company dist:', cur.fetchall())

conn.close()
