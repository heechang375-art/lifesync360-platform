import sys, io, json, boto3, pymysql
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

d = json.loads(boto3.client('secretsmanager', region_name='ap-northeast-2')
    .get_secret_value(SecretId='/lifesync/dev/db/master')['SecretString'])
conn = pymysql.connect(host=d['host'], user=d['username'], password=d['password'],
    database=d['dbname'], charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor, connect_timeout=10)
cur = conn.cursor()

# 이상 레코드 확인
cur.execute("SELECT COUNT(*) AS cnt FROM customer_recommend_history WHERE clicked_flag NOT IN ('Y','1') AND purchased_flag IN ('Y','1')")
before = cur.fetchone()['cnt']
print('BEFORE anomaly count:', before)

# clicked=N & purchased=Y → clicked_flag='Y' 로 수정
cur.execute("UPDATE customer_recommend_history SET clicked_flag='Y' WHERE clicked_flag NOT IN ('Y','1') AND purchased_flag IN ('Y','1')")
conn.commit()
print('UPDATED rows:', cur.rowcount)

# 검증
cur.execute("SELECT COUNT(*) AS cnt FROM customer_recommend_history WHERE clicked_flag NOT IN ('Y','1') AND purchased_flag IN ('Y','1')")
after = cur.fetchone()['cnt']
print('AFTER anomaly count:', after)

# CTR/CVR 재계산
cur.execute("SELECT COUNT(*) AS total, SUM(clicked_flag IN ('Y','1')) AS clicked, SUM(purchased_flag IN ('Y','1')) AS purchased FROM customer_recommend_history")
s = cur.fetchone()
clk = int(s['clicked'] or 0)
pur = int(s['purchased'] or 0)
tot = int(s['total'])
print(f'STATS total={tot} clicked={clk} purchased={pur}')
print(f'CTR={clk/tot*100:.1f}%  CVR={pur*100/clk:.1f}%' if clk else 'clk=0')

conn.close()
