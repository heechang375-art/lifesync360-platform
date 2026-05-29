import json, boto3, pymysql, traceback

d = json.loads(boto3.client('secretsmanager', region_name='ap-northeast-2')
    .get_secret_value(SecretId='/lifesync/dev/db/master')['SecretString'])

conn = pymysql.connect(
    host=d['host'], user=d['username'], password=d['password'],
    database=d['dbname'], charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor, connect_timeout=10,
)

try:
    cur = conn.cursor()

    # 1) product_master 컬럼 목록
    cur.execute("DESCRIBE product_master")
    cols = [r['Field'] for r in cur.fetchall()]
    print("=== product_master cols ===")
    print(cols)

    # 2) cross_sell 쿼리에 쓰는 컬럼 존재 확인
    for col in ('priority_rank', 'target_grade', 'active_flag'):
        print(f"  {col}: {'O' if col in cols else 'X'}")

    # 3) purchased 있는 고객 1명 추출
    cur.execute("""
        SELECT h.global_id
        FROM customer_recommend_history h
        WHERE h.purchased_flag IN ('Y','1')
        LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        print("purchased 고객 없음")
    else:
        gid = row['global_id']
        print(f"\n=== test global_id: {gid} ===")

        # 4) 해당 고객의 구매 카테고리 확인
        cur.execute("""
            SELECT cat.category_code, cat.category_name
            FROM customer_recommend_history h
            JOIN product_master p ON h.product_id = p.product_id
            JOIN category_master cat ON p.category_id = cat.category_id
            WHERE h.global_id = %s AND h.purchased_flag IN ('Y','1')
        """, (gid,))
        cats = cur.fetchall()
        print("구매 카테고리:", cats)

        # 5) 해당 카테고리로 매핑되는 cross_sell_rule
        if cats:
            base_codes = [c['category_code'] for c in cats]
            fmt = ','.join(['%s'] * len(base_codes))
            cur.execute(f"""
                SELECT r.cross_id, r.base_category, r.target_category
                FROM cross_sell_rule r
                WHERE r.active_flag = 'Y' AND r.base_category IN ({fmt})
                ORDER BY r.priority_rank ASC LIMIT 10
            """, base_codes)
            rules = cur.fetchall()
            print("매핑 rules:", rules)

        # 6) 실제 cross_sell 쿼리 (priority_rank 없이 product_id ASC)
        cur.execute("""
            SELECT
                r.target_category,
                (SELECT p.product_name
                 FROM product_master p
                 JOIN category_master c2 ON p.category_id = c2.category_id
                 WHERE c2.category_code = r.target_category
                   AND p.active_flag = 'Y'
                 ORDER BY p.product_id ASC LIMIT 1) AS product_name,
                (SELECT c3.category_name
                 FROM category_master c3
                 WHERE c3.category_code = r.target_category LIMIT 1) AS category_name
            FROM cross_sell_rule r
            WHERE r.active_flag = 'Y'
              AND r.base_category IN (
                SELECT cat.category_code
                FROM customer_recommend_history h2
                JOIN product_master p2 ON h2.product_id = p2.product_id
                JOIN category_master cat ON p2.category_id = cat.category_id
                WHERE h2.global_id = %s AND h2.purchased_flag IN ('Y','1')
              )
            ORDER BY r.priority_rank ASC LIMIT 3
        """, (gid,))
        cross = cur.fetchall()
        print("cross_sell result:", cross)

    # 7) CTR/CVR 이상 — clicked=N & purchased=Y
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM customer_recommend_history
        WHERE clicked_flag NOT IN ('Y','1')
          AND purchased_flag IN ('Y','1')
    """)
    anomaly = cur.fetchone()
    print(f"\n=== CTR/CVR 이상 (clicked=N, purchased=Y): {anomaly['cnt']}건 ===")

    # 8) 전체 CTR/CVR
    cur.execute("""
        SELECT COUNT(*) AS total,
               SUM(clicked_flag IN ('Y','1')) AS clicked,
               SUM(purchased_flag IN ('Y','1')) AS purchased
        FROM customer_recommend_history
    """)
    s = cur.fetchone()
    clk = int(s['clicked'] or 0)
    pur = int(s['purchased'] or 0)
    tot = int(s['total'] or 0)
    print(f"total={tot}, clicked={clk}, purchased={pur}")
    print(f"CTR={clk/tot*100:.1f}%, CVR(pur/clk)={pur*100/clk:.1f}%" if clk else "clk=0")

except Exception:
    traceback.print_exc()
finally:
    conn.close()
