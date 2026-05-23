"""
analytics_segment_performance + analytics_demographic_information
2026-05-21 데이터를 2026-05-22 (오늘)로 복사.
추가로 customer_recommend_history 에 오늘 데이터 삽입
(7일 트렌드 차트가 오늘까지 8점으로 표시되므로 SVG 수용 범위 확인 후 생략)
"""
import boto3
import pymysql
from decimal import Decimal
from datetime import date

TODAY = date.today().isoformat()          # 2026-05-22
YESTERDAY = '2026-05-21'
REGION = 'ap-northeast-2'

ddb = boto3.resource('dynamodb', region_name=REGION)

# ── 1. analytics_segment_performance ──────────────────────────────
seg_tbl = ddb.Table('analytics_segment_performance')
resp = seg_tbl.scan()
items_05_21 = [i for i in resp['Items'] if i.get('snapshot_date') == YESTERDAY]
print(f'[segment] 05-21 items: {len(items_05_21)}')

already_today = seg_tbl.query(
    KeyConditionExpression=boto3.dynamodb.conditions.Key('snapshot_date').eq(TODAY)
).get('Items', [])
print(f'[segment] 05-22 existing: {len(already_today)}')

if not already_today:
    with seg_tbl.batch_writer() as batch:
        for item in items_05_21:
            new_item = dict(item, snapshot_date=TODAY)
            batch.put_item(Item=new_item)
    print(f'[segment] seeded {len(items_05_21)} items for {TODAY}')
else:
    print(f'[segment] already exists, skip')

# ── 2. analytics_demographic_information ──────────────────────────
try:
    demo_tbl = ddb.Table('analytics_demographic_information')
    resp2 = demo_tbl.scan()
    items_demo = [i for i in resp2['Items'] if i.get('snapshot_date') == YESTERDAY]
    print(f'[demo] 05-21 items: {len(items_demo)}')

    already_demo = demo_tbl.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('snapshot_date').eq(TODAY)
    ).get('Items', [])
    print(f'[demo] 05-22 existing: {len(already_demo)}')

    if not already_demo and items_demo:
        with demo_tbl.batch_writer() as batch:
            for item in items_demo:
                new_item = dict(item, snapshot_date=TODAY)
                batch.put_item(Item=new_item)
        print(f'[demo] seeded {len(items_demo)} items for {TODAY}')
    else:
        print(f'[demo] skip')
except Exception as e:
    print(f'[demo] error: {e}')

# ── 3. Aurora customer_recommend_history — 오늘 추천 데이터 10건 추가 ──
# (SVG viewBox 640px, bw=60, gap=18 기준 최대 8일 허용)
db = pymysql.connect(
    host='auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com',
    user='admin', password='ChangeMe123!', database='lifesync360',
    cursorclass=pymysql.cursors.DictCursor, charset='utf8mb4'
)
cur = db.cursor()

# 오늘 데이터 이미 있는지 확인
cur.execute("SELECT COUNT(*) AS cnt FROM customer_recommend_history WHERE DATE(recommended_at) = CURDATE()")
existing = cur.fetchone()['cnt']
print(f'[history] today existing: {existing}')

if existing == 0:
    cur.execute("SELECT DISTINCT global_id FROM customer_recommend_history LIMIT 5")
    gids = [r['global_id'] for r in cur.fetchall()]

    cur.execute("SELECT product_id FROM product_master WHERE active_flag='Y' LIMIT 10")
    pids = [r['product_id'] for r in cur.fetchall()]

    action_codes = ['RECOMMEND_AI', 'RECOMMEND_CROSS', 'RECOMMEND_VIP', 'RECOMMEND_PROFILE', 'RECOMMEND_CAMPAIGN']
    rows = []
    import random, string
    random.seed(42)
    for i in range(10):
        gid  = gids[i % len(gids)]
        pid  = pids[i % len(pids)]
        act  = action_codes[i % len(action_codes)]
        clk  = 'Y' if i % 3 != 2 else 'N'
        pur  = 'Y' if i % 5 == 0 else 'N'
        rows.append((gid, pid, act, f'CH{str(i).zfill(3)}', clk, pur))

    cur.executemany(
        "INSERT INTO customer_recommend_history "
        "(global_id, product_id, action_code, channel_code, clicked_flag, purchased_flag, recommended_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, NOW())",
        rows
    )
    db.commit()
    print(f'[history] inserted {len(rows)} rows for today')
else:
    print(f'[history] skip, already {existing} rows today')

cur.execute("SELECT COUNT(*) AS cnt FROM customer_recommend_history WHERE DATE(recommended_at) = CURDATE()")
print(f'[history] final today count: {cur.fetchone()["cnt"]}')
db.close()
print('done')
