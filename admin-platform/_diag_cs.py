import sys, io, json, boto3, pymysql
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

d = json.loads(boto3.client('secretsmanager', region_name='ap-northeast-2')
    .get_secret_value(SecretId='/lifesync/dev/db/master')['SecretString'])
conn = pymysql.connect(host=d['host'], user=d['username'], password=d['password'],
    database=d['dbname'], charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor, connect_timeout=10)
cur = conn.cursor()
GID = 'G000106253'

# 1) recommend_history 레코드 존재 여부
cur.execute("SELECT COUNT(*) AS cnt FROM customer_recommend_history WHERE global_id=%s", (GID,))
print('history_count:', cur.fetchone()['cnt'])

cur.execute("SELECT COUNT(*) AS cnt FROM customer_recommend_history WHERE global_id=%s AND purchased_flag IN ('Y','1')", (GID,))
print('purchased_count:', cur.fetchone()['cnt'])

# 2) 추천 이력 카테고리 (fallback 경로)
cur.execute("""
    SELECT cat.category_code, COUNT(*) AS cnt
    FROM customer_recommend_history h
    JOIN product_master p ON h.product_id=p.product_id
    JOIN category_master cat ON p.category_id=cat.category_id
    WHERE h.global_id=%s
    GROUP BY cat.category_code
""", (GID,))
cats = cur.fetchall()
print('categories in history:', cats)

# 3) fallback cross-sell 쿼리 (purchased_flag 제약 없음)
cur.execute("""
    SELECT r.target_category,
      (SELECT p.product_name FROM product_master p
       JOIN category_master c2 ON p.category_id=c2.category_id
       WHERE c2.category_code=r.target_category AND p.active_flag='Y'
       ORDER BY p.priority_rank ASC LIMIT 1) AS product_name,
      (SELECT c3.category_name FROM category_master c3
       WHERE c3.category_code=r.target_category LIMIT 1) AS category_name
    FROM cross_sell_rule r
    WHERE r.active_flag='Y'
      AND r.base_category IN (
        SELECT cat.category_code FROM customer_recommend_history h
        JOIN product_master p ON h.product_id=p.product_id
        JOIN category_master cat ON p.category_id=cat.category_id
        WHERE h.global_id=%s
      )
    ORDER BY r.priority_rank ASC LIMIT 3
""", (GID,))
rows = cur.fetchall()
print('fallback_crosssell:', rows)
print('non_null:', [r for r in rows if r['product_name']])

conn.close()
