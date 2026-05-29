import sys, os, time
sys.path.insert(0, 'C:/admin-platform')
os.chdir('C:/admin-platform')
import app

print('=== Block 1: Aurora ===')
t1 = time.time()
try:
    with app.get_db() as db, db.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM customer_recommend_history "
            "WHERE recommended_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
        )
        row = cur.fetchone()
        print(f'Aurora result: {row}')
except Exception as e:
    print(f'Aurora err: {e}')
print(f'Block 1 elapsed: {time.time()-t1:.2f}s')

print('=== Block 2: DynamoDB scan Limit=1 ===')
t2 = time.time()
try:
    import boto3
    _ddb_r = boto3.resource('dynamodb', region_name=app.AWS_REGION)
    _resp = _ddb_r.Table('lifesync_customer_result').scan(ProjectionExpression='update_time', Limit=1)
    print(f'DDB scan result: {(_resp.get("Items") or [{}])[0].get("update_time", "")}')
except Exception as e:
    print(f'DDB scan err: {e}')
print(f'Block 2 elapsed: {time.time()-t2:.2f}s')

print('=== Block 3: describe_table ===')
t3 = time.time()
try:
    import boto3
    _ddb_c = boto3.client('dynamodb', region_name=app.AWS_REGION)
    cnt = _ddb_c.describe_table(TableName='lifesync_customer_result')['Table']['ItemCount']
    print(f'describe_table count: {cnt}')
except Exception as e:
    print(f'describe_table err: {e}')
print(f'Block 3 elapsed: {time.time()-t3:.2f}s')
