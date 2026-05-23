"""
analytics_segment_performance + analytics_demographic_information
기존 데이터 없을 때 오늘 날짜로 처음부터 시드.
"""
import boto3
from decimal import Decimal
from datetime import date

TODAY = date.today().isoformat()
REGION = 'ap-northeast-2'
ddb = boto3.resource('dynamodb', region_name=REGION)

# ── 1. analytics_segment_performance ──────────────────────────────────────────
seg_tbl = ddb.Table('analytics_segment_performance')

already = seg_tbl.query(
    KeyConditionExpression=boto3.dynamodb.conditions.Key('snapshot_date').eq(TODAY)
).get('Items', [])
print(f'[segment] existing for {TODAY}: {len(already)}')

if already:
    print('[segment] already seeded, skip')
else:
    SEGMENT_ROWS = [
        # age_band
        ('age_band#20s',  '20s',  1820, 346, 64,  19.0, 18.5),
        ('age_band#30s',  '30s',  3410, 716, 142, 21.0, 19.8),
        ('age_band#40s',  '40s',  3890, 740, 156, 19.0, 21.1),
        ('age_band#50s',  '50s',  2190, 372, 85,  17.0, 22.8),
        ('age_band#60s+', '60s+',  850, 119, 28,  14.0, 23.5),
        # gender
        ('gender#M', 'M', 6320, 1235, 258, 19.5, 20.9),
        ('gender#F', 'F', 5840, 1058, 217, 18.1, 20.5),
        # region
        ('region#Seoul',    'Seoul',    4260, 832, 175, 19.5, 21.0),
        ('region#Gyeonggi', 'Gyeonggi', 2680, 509, 104, 19.0, 20.4),
        ('region#Busan',    'Busan',    1460, 271,  55, 18.6, 20.3),
        ('region#Incheon',  'Incheon',   970, 181,  36, 18.7, 19.9),
        ('region#Daegu',    'Daegu',     850, 154,  30, 18.1, 19.5),
        ('region#Other',    'Other',    1940, 346,  75, 17.8, 21.7),
        # income
        ('income#high', 'high', 2840, 597, 148, 21.0, 24.8),
        ('income#mid',  'mid',  5620, 1042, 204, 18.5, 19.6),
        ('income#low',  'low',  3700,  654, 123, 17.7, 18.8),
        # asset
        ('asset#high', 'high', 3120, 672, 168, 21.5, 25.0),
        ('asset#mid',  'mid',  5180, 943, 186, 18.2, 19.7),
        ('asset#low',  'low',  3860, 678, 121, 17.6, 17.8),
    ]
    with seg_tbl.batch_writer() as batch:
        for sk, val, rec, clk, pur, ctr, cvr in SEGMENT_ROWS:
            batch.put_item(Item={
                'snapshot_date': TODAY,
                'segment_key':   sk,
                'value':         val,
                'recommended':   rec,
                'clicked':       clk,
                'purchased':     pur,
                'ctr':           Decimal(str(ctr)),
                'cvr':           Decimal(str(cvr)),
            })
    print(f'[segment] seeded {len(SEGMENT_ROWS)} rows for {TODAY}')

# ── 2. analytics_demographic_information ──────────────────────────────────────
demo_tbl = ddb.Table('analytics_demographic_information')

already_demo = demo_tbl.query(
    KeyConditionExpression=boto3.dynamodb.conditions.Key('snapshot_date').eq(TODAY)
).get('Items', [])
print(f'[demo] existing for {TODAY}: {len(already_demo)}')

if already_demo:
    print('[demo] already seeded, skip')
else:
    DEMO_ROWS = [
        # age_band — customer count + avg score
        ('age_band#20s',  '20s',  1820, Decimal('72.4'), Decimal('0.31')),
        ('age_band#30s',  '30s',  3410, Decimal('75.8'), Decimal('0.42')),
        ('age_band#40s',  '40s',  3890, Decimal('78.2'), Decimal('0.48')),
        ('age_band#50s',  '50s',  2190, Decimal('80.6'), Decimal('0.52')),
        ('age_band#60s+', '60s+',  850, Decimal('77.1'), Decimal('0.39')),
        # gender
        ('gender#M', 'M', 6320, Decimal('77.4'), Decimal('0.44')),
        ('gender#F', 'F', 5840, Decimal('76.9'), Decimal('0.43')),
        # income
        ('income#high', 'high', 2840, Decimal('85.3'), Decimal('0.62')),
        ('income#mid',  'mid',  5620, Decimal('76.1'), Decimal('0.41')),
        ('income#low',  'low',  3700, Decimal('69.4'), Decimal('0.28')),
        # asset
        ('asset#high', 'high', 3120, Decimal('86.2'), Decimal('0.65')),
        ('asset#mid',  'mid',  5180, Decimal('75.8'), Decimal('0.40')),
        ('asset#low',  'low',  3860, Decimal('68.7'), Decimal('0.26')),
    ]
    with demo_tbl.batch_writer() as batch:
        for dk, val, count, avg_score, vip_prob in DEMO_ROWS:
            batch.put_item(Item={
                'snapshot_date':   TODAY,
                'demographic_key': dk,
                'value':           val,
                'customer_count':  count,
                'avg_score':       avg_score,
                'avg_vip_prob':    vip_prob,
            })
    print(f'[demo] seeded {len(DEMO_ROWS)} rows for {TODAY}')

print('done')
