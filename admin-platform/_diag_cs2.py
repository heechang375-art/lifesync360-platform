import sys, io, json, boto3, pymysql
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

d = json.loads(boto3.client('secretsmanager', region_name='ap-northeast-2')
    .get_secret_value(SecretId='/lifesync/dev/db/master')['SecretString'])
conn = pymysql.connect(host=d['host'], user=d['username'], password=d['password'],
    database=d['dbname'], charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor, connect_timeout=10)
cur = conn.cursor()

GID = 'G000106253'
DOMAINS = ('BANK', 'HLT')  # 동의한 계열사

# 1) 동의 계열사에 속한 target_category 상품이 있는 cross_sell_rule
fmt = ','.join(['%s'] * len(DOMAINS))
cur.execute(f"""
    SELECT r.cross_id, r.base_category, r.target_category,
      (SELECT p.product_name FROM product_master p
       JOIN category_master c2 ON p.category_id=c2.category_id
       JOIN company_master cm ON p.company_id=cm.company_id
       WHERE c2.category_code=r.target_category AND p.active_flag='Y'
         AND cm.company_code IN ({fmt})
       ORDER BY p.priority_rank ASC LIMIT 1) AS product_name
    FROM cross_sell_rule r WHERE r.active_flag='Y'
    ORDER BY r.priority_rank ASC
""", DOMAINS)
rules = cur.fetchall()
has_product = [r for r in rules if r['product_name']]
no_product  = [r for r in rules if not r['product_name']]
print(f'전체 active rule: {len(rules)}개')
print(f'BANK/HLT 상품 있는 rule: {len(has_product)}개')
print(f'BANK/HLT 상품 없는 rule: {len(no_product)}개')
print('상품 있는 rule 목록:')
for r in has_product:
    print(f"  base={r['base_category']} -> target={r['target_category']}: {r['product_name']}")

# 2) G000106253의 추천 이력 카테고리
cur.execute("""
    SELECT cat.category_code, COUNT(*) AS cnt
    FROM customer_recommend_history h
    JOIN product_master p ON h.product_id=p.product_id
    JOIN category_master cat ON p.category_id=cat.category_id
    WHERE h.global_id=%s
    GROUP BY cat.category_code
""", (GID,))
hist_cats = {r['category_code'] for r in cur.fetchall()}
print(f'\n{GID} 추천 이력 카테고리: {hist_cats}')

# 3) 교차 가능한 rule (이력 base + BANK/HLT 상품 있는 target)
matched = [r for r in has_product if r['base_category'] in hist_cats]
print(f'실제 교차판매 가능 rule: {len(matched)}개')
for r in matched:
    print(f"  {r['base_category']} -> {r['target_category']}: {r['product_name']}")

conn.close()
