import sys, io, json, boto3, pymysql
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

d = json.loads(boto3.client('secretsmanager', region_name='ap-northeast-2')
    .get_secret_value(SecretId='/lifesync/dev/db/master')['SecretString'])
conn = pymysql.connect(host=d['host'], user=d['username'], password=d['password'],
    database=d['dbname'], charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor, connect_timeout=10)
cur = conn.cursor()

# 구매 이력 있는 distinct 고객 수
cur.execute("SELECT COUNT(DISTINCT global_id) AS cnt FROM customer_recommend_history WHERE purchased_flag IN ('Y','1')")
print('distinct customers with purchase:', cur.fetchone())

# 전체 distinct 고객 수 in recommend_history
cur.execute("SELECT COUNT(DISTINCT global_id) AS cnt FROM customer_recommend_history")
print('total distinct customers in history:', cur.fetchone())

# sample customers with purchases
cur.execute("SELECT DISTINCT global_id FROM customer_recommend_history WHERE purchased_flag IN ('Y','1') LIMIT 5")
print('sample purchased gids:', [r['global_id'] for r in cur.fetchall()])

# grade filter test: BASIC/GOLD 각 target category
for grade in ('BASIC', 'GOLD', 'SILVER'):
    cur.execute(
        "SELECT r.target_category, "
        "(SELECT p.product_name FROM product_master p "
        " JOIN category_master c2 ON p.category_id=c2.category_id "
        " WHERE c2.category_code=r.target_category AND p.active_flag='Y' "
        " AND p.target_grade=%s ORDER BY p.priority_rank ASC LIMIT 1) AS product_name "
        "FROM cross_sell_rule r WHERE r.active_flag='Y' "
        " AND r.base_category IN ("
        "  SELECT cat.category_code FROM customer_recommend_history h "
        "  JOIN product_master p2 ON h.product_id=p2.product_id "
        "  JOIN category_master cat ON p2.category_id=cat.category_id "
        "  WHERE h.global_id='G000004001' AND h.purchased_flag IN ('Y','1')"
        " ) ORDER BY r.priority_rank ASC LIMIT 3",
        (grade,)
    )
    rows = cur.fetchall()
    non_null = [r for r in rows if r['product_name']]
    print(f"grade={grade}: total={len(rows)}, non_null={len(non_null)}, sample={rows[:2]}")

conn.close()
