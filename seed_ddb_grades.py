import boto3, os, random
from datetime import datetime, timezone, timedelta
from decimal import Decimal

AWS_REGION   = os.environ.get('AWS_REGION', 'ap-northeast-2')
DYNAMO_TABLE = os.environ.get('DYNAMO_TABLE', 'lifesync_customer_result')

ddb   = boto3.resource('dynamodb', region_name=AWS_REGION)
table = ddb.Table(DYNAMO_TABLE)

now          = datetime.now(timezone.utc)
batch_time   = (now - timedelta(days=1)).replace(hour=4, minute=30, second=0, microsecond=0)
update_time  = batch_time.strftime('%Y-%m-%d %H:%M:%S.%f UTC')
ttl_epoch    = int((now + timedelta(days=30)).timestamp())

GRADES = [
    ('VIP',    (90, 100), ['PB_CONTACT', 'VIP_INVITE', 'PRIVATE_BANKING_CONTACT'],          5, 800001),
    ('GOLD',   (80,  89), ['PREMIUM_UPSELL', 'GLOBAL_INV', 'PREMIUM_CARD_INVITE'],          10, 700001),
    ('SILVER', (70,  79), ['INSURANCE_UPSELL', 'HEALTH_INS', 'PENSION_RECOMMEND'],          14, 600001),
    ('BASIC',  (60,  69), ['SAVING_RECOMMEND', 'CARD_RECOMMEND', 'DIRECT_INS_RECOMMEND'],   10, 500001),
    ('CARE',   (10,  30), ['RETENTION', 'HEALTH_SERVICE', 'WELLNESS_GUIDE'],                 1, 400001),
]

with table.batch_writer() as batch:
    total = 0
    for grade, (smin, smax), nba_choices, count, gid_start in GRADES:
        for i in range(count):
            gid   = f"G{gid_start + i:09d}"
            score = round(random.uniform(smin, smax), 1)
            health = round(random.uniform(55, 95), 1)
            vip_base = {'VIP': 0.85, 'GOLD': 0.55, 'SILVER': 0.30, 'BASIC': 0.15, 'CARE': 0.04}[grade]
            vip_prob = round(random.uniform(max(0, vip_base - 0.05), min(1, vip_base + 0.10)), 4)
            batch.put_item(Item={
                'global_id'        : gid,
                'update_time'      : update_time,
                'dynamic_grade'    : grade,
                'dynamic_score'    : Decimal(str(score)),
                'health_score'     : Decimal(str(health)),
                'next_best_action' : random.choice(nba_choices),
                'rec_prob'         : random.choice([0, 1]),
                'signup_prob'      : random.choice([0, 1]),
                'source'           : 'GCP_lifesync',
                'ttl'              : ttl_epoch,
                'vip_prob'         : Decimal(str(vip_prob)),
            })
            total += 1

print(f"DDB seed done: {total} items written")

from collections import Counter
result = table.scan(ProjectionExpression='dynamic_grade')
grades = Counter(item.get('dynamic_grade') for item in result.get('Items', []))
for g, c in sorted(grades.items()):
    print(f"  {g}: {c}")
print(f"  TOTAL: {sum(grades.values())}")
