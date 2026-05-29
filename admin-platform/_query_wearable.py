import os, json, sys
sys.path.insert(0, 'C:/admin-platform')

import boto3
secret = boto3.client('secretsmanager', region_name='ap-northeast-2')
d = json.loads(secret.get_secret_value(SecretId='/lifesync/dev/db/master')['SecretString'])

import pymysql
conn = pymysql.connect(
    host=d['host'], user=d['username'], password=d['password'],
    database=d['dbname'], cursorclass=pymysql.cursors.DictCursor, connect_timeout=10
)
cur = conn.cursor()

# wearable 관련 테이블 찾기
cur.execute("SHOW TABLES LIKE '%wear%'")
wearable_tables = [list(r.values())[0] for r in cur.fetchall()]

# 전체 테이블 목록도 확인
cur.execute("SHOW TABLES")
all_tables = [list(r.values())[0] for r in cur.fetchall()]

result = {'all_tables': all_tables, 'wearable_tables': wearable_tables}

# wearable 테이블 있으면 컬럼과 샘플 조회
for t in wearable_tables:
    cur.execute(f'DESCRIBE {t}')
    result[f'{t}_columns'] = [r['Field'] for r in cur.fetchall()]
    cur.execute(f'SELECT COUNT(*) AS n FROM {t}')
    result[f'{t}_count'] = cur.fetchone()['n']
    if result[f'{t}_count'] > 0:
        cur.execute(f'SELECT * FROM {t} ORDER BY 1 DESC LIMIT 3')
        result[f'{t}_sample'] = cur.fetchall()

conn.close()

out_path = 'C:/admin-platform/_query_wearable_out.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, default=str)
print('OK:' + out_path)
